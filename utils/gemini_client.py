#!/usr/bin/env python3
"""
Gemini API Client — 100% FREE
Google AI Studio 무료 티어: gemini-2.5-flash-lite (1,500 req/day, 15 RPM)
API Key: https://aistudio.google.com/app/apikey

=== Rate Limit 근본 원인 & 해결책 ===

[원인 1] 프롬프트 토큰 초과 → TPM(Tokens Per Minute) 한도 소진
  - 무료 티어 gemini-2.5-flash-lite: 250,000 TPM 제한
  - 시장 데이터(yfinance)가 방대할 경우 프롬프트 자체가 수만 토큰 → 즉시 소진
  → 해결: 데이터를 엄격하게 압축 (MAX_DATA_CHARS 3000→2000 축소 + 기간/기업 필터링)

[원인 2] max_output_tokens=4096 → 응답 토큰도 TPM에 포함
  - 입력 + 출력 합산이 TPM 한도 적용
  → 해결: max_output_tokens를 2048로 축소 (블로그 포스트에 충분)

[원인 3] 재시도 로직이 RPM/TPM 윈도우를 고려하지 않음
  - 90초 지수 대기는 TPM 1분 윈도우 초기화와 맞지 않음
  → 해결: 65초 고정 대기 (1분 슬라이딩 윈도우 완전 초기화 보장)

[원인 4] 기간 데이터가 방대한 경우 (yfinance 기본값: 1년~5년)
  → 해결: _filter_recent()로 최근 항목만 추출 (최대 5건)

[원인 5] 기업 데이터가 너무 많은 경우 (S&P 500 전체 등)
  → 해결: MAJOR_TICKERS (시총 상위 20개)만 우선 표시
"""

import os
import json
import re
import time
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash-lite-preview-06-17"

# ── 토큰 절약 설정 ──────────────────────────────────────────
MAX_DATA_CHARS    = 2000  # 시장 데이터 최대 문자 수 (3000 → 2000 축소)
MAX_OUTPUT_TOKENS = 2048  # 응답 최대 토큰 (4096 → 2048 축소)
RETRY_WAIT_BASE   = 65    # Rate limit 재시도 대기(초) — 1분 TPM 윈도우 초기화

# ── 주요 기업 필터 (시총 상위 20개) ─────────────────────────
# 기업 데이터가 너무 많을 때 이 목록만 우선 표시
MAJOR_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META",
    "TSLA", "BRK-B", "LLY", "JPM", "V", "UNH", "XOM", "MA",
    "AVGO", "HD", "PG", "JNJ", "COST",
}


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "발급: https://aistudio.google.com/app/apikey (무료)"
        )
    return genai.Client(api_key=api_key)


def _filter_recent(data: list, max_items: int = 5) -> list:
    """
    리스트 데이터에서 최근 항목만 반환.
    기간 데이터가 방대한 경우(yfinance 기본 1~5년치) 최근 항목만 추출.
    Gemini 프롬프트용 요약에는 최대 max_items개만 사용.
    """
    if not data:
        return []
    return data[-max_items:] if len(data) > max_items else data


def _filter_major_companies(movers: dict) -> dict:
    """
    기업 데이터가 너무 많은 경우 주요 기업(시총 상위 20개)만 필터링.
    - 주요 기업: 최대 3개
    - 기타 기업: 최대 2개
    합계 5개 이하로 제한.
    """
    result = {}
    for key in ("gainers", "losers"):
        items = movers.get(key, [])
        if not items:
            result[key] = []
            continue
        major  = [i for i in items if i.get("symbol", "") in MAJOR_TICKERS]
        others = [i for i in items if i.get("symbol", "") not in MAJOR_TICKERS]
        result[key] = (major[:3] + others[:2])[:5]
    return result


def compress_market_data(market_data: dict) -> str:
    """
    시장 데이터를 Gemini 토큰 한도 내로 압축.
    - 기간 데이터: 최근 항목만 사용 (_filter_recent)
    - 기업 데이터: 주요 기업만 필터링 (_filter_major_companies)
    - 섹터: 상위 3개 + 하위 3개만 표시 (11개 → 6개)
    - 전체: MAX_DATA_CHARS(2000자) 이하로 강제 절단
    """
    lines = []

    # ── 지수 ─────────────────────────────────────────────────
    if "indices" in market_data:
        lines.append("[Indices]")
        for name, d in market_data["indices"].items():
            if isinstance(d, dict) and "close" in d:
                chg  = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg:.2f}%)")

    # ── 섹터: 상위 3 + 하위 3만 ─────────────────────────────
    if "sectors" in market_data:
        lines.append("[Sectors top3/bottom3]")
        sectors = market_data["sectors"]
        if isinstance(sectors, dict):
            valid = [
                (k, v) for k, v in sectors.items()
                if isinstance(v, dict) and "change_pct" in v
            ]
            sorted_s = sorted(valid, key=lambda x: x[1].get("change_pct", 0), reverse=True)
            shown    = set()
            for name, d in sorted_s[:3] + sorted_s[-3:]:
                if name not in shown:
                    chg  = d.get("change_pct", 0)
                    sign = "+" if chg >= 0 else ""
                    lines.append(f"  {name}: {sign}{chg:.2f}%")
                    shown.add(name)

    # ── Top movers: 주요 기업 우선 ──────────────────────────
    if "movers" in market_data:
        filtered = _filter_major_companies(market_data["movers"])
        if filtered.get("gainers"):
            lines.append("[Top Gainers]")
            for g in filtered["gainers"]:
                lines.append(
                    f"  {g['symbol']}: +{g.get('change_pct', 0):.2f}%"
                    f" @ ${g.get('price', 0)}"
                )
        if filtered.get("losers"):
            lines.append("[Top Losers]")
            for g in filtered["losers"]:
                lines.append(
                    f"  {g['symbol']}: {g.get('change_pct', 0):.2f}%"
                    f" @ ${g.get('price', 0)}"
                )

    # ── 선물 ─────────────────────────────────────────────────
    if "futures" in market_data:
        lines.append("[Futures]")
        for name, d in market_data["futures"].items():
            if isinstance(d, dict) and "close" in d:
                chg  = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg:.2f}%)")

    # ── 아시아/유럽 ──────────────────────────────────────────
    if "premarket" in market_data:
        lines.append("[Asia/Europe]")
        for name, d in market_data["premarket"].items():
            if isinstance(d, dict) and "close" in d:
                chg  = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg:.2f}%)")

    # ── 실적: 주요 기업 우선 + 최대 5건 ────────────────────
    if "earnings_calendar" in market_data and market_data["earnings_calendar"]:
        earnings = market_data["earnings_calendar"]
        major_e  = [e for e in earnings if e.get("symbol", "") in MAJOR_TICKERS]
        other_e  = [e for e in earnings if e.get("symbol", "") not in MAJOR_TICKERS]
        shown_e  = (major_e + other_e[:3])[:5]
        lines.append("[Earnings Today]")
        for e in shown_e:
            lines.append(
                f"  {e.get('symbol')} ({e.get('name', '')}): "
                f"EPS est={e.get('eps_estimate', 'N/A')}"
            )

    # ── 경제 지표: 최근 5건만 (기간 데이터 필터) ────────────
    if "economic_calendar" in market_data and market_data["economic_calendar"]:
        econ_recent = _filter_recent(market_data["economic_calendar"], max_items=5)
        lines.append("[Economic Data]")
        for e in econ_recent:
            lines.append(
                f"  {e.get('event')}: actual={e.get('actual')}, "
                f"prev={e.get('previous')}, impact={e.get('impact')}"
            )

    result = "\n".join(lines)

    # ── 최대 문자 수 초과 시 강제 절단 ──────────────────────
    if len(result) > MAX_DATA_CHARS:
        result = result[:MAX_DATA_CHARS] + "\n  ...(truncated)"

    return result


def generate_post(prompt: str, max_retries: int = 3) -> str:
    """
    Gemini로 블로그 포스트 JSON 생성.

    Rate Limit 해결:
    - max_output_tokens=2048: 입력+출력 TPM 소비를 절반으로 감소
    - 재시도 대기 65초 고정: 1분 TPM 슬라이딩 윈도우 완전 초기화 후 재시도
    """
    client = get_client()

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                    max_output_tokens=MAX_OUTPUT_TOKENS,  # 2048
                ),
            )
            return response.text

        except Exception as e:
            err = str(e)
            is_rate_limit = any(k in err for k in [
                "429", "quota", "rate", "RESOURCE_EXHAUSTED", "exhausted",
                "TPM", "RPM", "tokens per minute",
            ])

            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Gemini API {max_retries}회 재시도 모두 실패.\n"
                    f"마지막 오류: {err[:200]}"
                )

            if is_rate_limit:
                # 65초 고정 대기 — 1분 TPM 윈도우 리셋 보장
                print(
                    f"⏳ Rate limit (TPM/RPM 초과) — "
                    f"{RETRY_WAIT_BASE}초 대기 후 재시도 "
                    f"({attempt + 1}/{max_retries})...\n"
                    f"   오류: {err[:120]}"
                )
                time.sleep(RETRY_WAIT_BASE)
            else:
                print(
                    f"⚠️  Gemini 오류 (시도 {attempt + 1}): "
                    f"{err[:120]} — 10초 후 재시도..."
                )
                time.sleep(10)

    raise RuntimeError(f"Gemini API {max_retries}회 재시도 모두 실패")


def parse_json_response(raw: str) -> dict:
    """Gemini 응답에서 JSON 파싱."""
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$',    '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"JSON 파싱 실패:\n{raw[:300]}")
