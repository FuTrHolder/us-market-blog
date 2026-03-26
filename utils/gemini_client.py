#!/usr/bin/env python3
"""
Gemini API Client — 100% FREE
Google AI Studio 무료 티어: gemini-2.5-flash-lite (1,500 req/day, 15 RPM)
API Key: https://aistudio.google.com/app/apikey

=== 에러 원인 분석 및 해결책 ===

[이번 에러] 404 NOT_FOUND — 잘못된 모델 ID
  - 사용한 ID: gemini-2.5-flash-lite-preview-06-17 (존재하지 않음)
  - 올바른 ID: gemini-2.5-flash-lite (stable, 2025년 7월 GA 출시)
  - 추가 문제: 404를 Rate limit으로 오인 → 65초×3회 불필요한 대기 발생
  → 해결: 모델 ID 수정 + 에러 유형별 분기 처리 강화

[원인 1] 토큰 초과(TPM) → Rate limit
  - 무료 티어: 250,000 TPM / 15 RPM
  - 방대한 시장 데이터가 프롬프트 토큰을 과소비
  → 해결: MAX_DATA_CHARS=1500 (추가 축소), 섹터 top3/bottom3, 기업 필터

[원인 2] max_output_tokens=4096 → TPM 추가 소비
  → 해결: max_output_tokens=2048로 축소

[원인 3] 재시도 대기가 TPM 1분 윈도우와 불일치
  → 해결: Rate limit만 65초 고정 대기, 그 외 에러는 즉시 재시도

[원인 4] 기간 데이터 방대 (yfinance 기본 1~5년치)
  → 해결: _filter_recent() — 최대 5건만 추출

[원인 5] 기업 데이터 과다 (S&P500 전체 등)
  → 해결: MAJOR_TICKERS (시총 상위 20개) 우선, 합계 5개 이하
"""

import os
import json
import re
import time
from google import genai
from google.genai import types

# ✅ 수정: 올바른 모델 ID (stable GA 버전, 2025년 7월 출시)
GEMINI_MODEL = "gemini-2.5-flash-lite"

# ── 토큰 절약 설정 ──────────────────────────────────────────
MAX_DATA_CHARS    = 1500  # 시장 데이터 최대 문자 수 (추가 축소: 2000→1500)
MAX_OUTPUT_TOKENS = 2048  # 응답 최대 토큰 (4096→2048 절반 축소)
RETRY_WAIT_RATE   = 65    # Rate limit 재시도 대기(초) — 1분 TPM 윈도우 초기화
RETRY_WAIT_OTHER  = 10    # 기타 오류 재시도 대기(초)

# ── 주요 기업 필터 (시총 상위 20개) ─────────────────────────
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
    기간 데이터가 방대한 경우 최근 항목만 반환.
    yfinance 기본값(1~5년치 데이터)에서 Gemini 프롬프트용 요약은
    최근 max_items개만 사용해 토큰 낭비를 방지.
    """
    if not data:
        return []
    return data[-max_items:] if len(data) > max_items else data


def _filter_major_companies(movers: dict) -> dict:
    """
    기업 데이터가 너무 많은 경우 주요 기업(시총 상위 20개)만 필터링.
    - 주요 기업(MAJOR_TICKERS): 최대 3개 우선
    - 기타 기업: 최대 2개 추가
    - 합계 5개 이하로 제한
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

    적용된 최적화:
    - 지수: 전체 표시 (4~5개, 핵심 데이터)
    - 섹터: 상위 3개 + 하위 3개만 (11개 → 최대 6개)
    - Top movers: 주요 기업 우선, 합계 5개 이하
    - 선물/아시아유럽: 전체 표시 (보통 5~8개)
    - 실적: 주요 기업 우선 + 최대 5건
    - 경제지표: 최근 5건만 (기간 데이터 필터)
    - 전체: MAX_DATA_CHARS(1500자) 초과 시 강제 절단
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

    # ── 섹터: 상위 3 + 하위 3만 (11개→최대 6개) ─────────────
    if "sectors" in market_data:
        sectors = market_data["sectors"]
        if isinstance(sectors, dict):
            valid    = [(k, v) for k, v in sectors.items()
                        if isinstance(v, dict) and "change_pct" in v]
            sorted_s = sorted(valid, key=lambda x: x[1].get("change_pct", 0), reverse=True)
            shown, added = set(), []
            for name, d in sorted_s[:3] + sorted_s[-3:]:
                if name not in shown:
                    chg  = d.get("change_pct", 0)
                    sign = "+" if chg >= 0 else ""
                    added.append(f"  {name}: {sign}{chg:.2f}%")
                    shown.add(name)
            if added:
                lines.append("[Sectors top/bottom]")
                lines.extend(added)

    # ── Top movers: 주요 기업 우선 ──────────────────────────
    if "movers" in market_data:
        filtered = _filter_major_companies(market_data["movers"])
        if filtered.get("gainers"):
            lines.append("[Gainers]")
            for g in filtered["gainers"]:
                lines.append(
                    f"  {g['symbol']}: +{g.get('change_pct', 0):.2f}%"
                    f" @${g.get('price', 0)}"
                )
        if filtered.get("losers"):
            lines.append("[Losers]")
            for g in filtered["losers"]:
                lines.append(
                    f"  {g['symbol']}: {g.get('change_pct', 0):.2f}%"
                    f" @${g.get('price', 0)}"
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
        lines.append("[Earnings]")
        for e in shown_e:
            lines.append(
                f"  {e.get('symbol')} ({e.get('name', '')[:15]}): "
                f"EPS={e.get('eps_estimate', 'N/A')}"
            )

    # ── 경제지표: 최근 5건만 (기간 데이터 필터 적용) ────────
    if "economic_calendar" in market_data and market_data["economic_calendar"]:
        econ = _filter_recent(market_data["economic_calendar"], max_items=5)
        lines.append("[Economic]")
        for e in econ:
            lines.append(
                f"  {e.get('event','')[:20]}: "
                f"act={e.get('actual')}, prev={e.get('previous')}, "
                f"impact={e.get('impact')}"
            )

    result = "\n".join(lines)

    # ── 최대 문자 수 초과 시 강제 절단 ──────────────────────
    if len(result) > MAX_DATA_CHARS:
        result = result[:MAX_DATA_CHARS] + "\n  ...(truncated)"

    return result


def _classify_error(err: str) -> str:
    """
    에러 문자열을 분류해서 처리 방법을 결정.
    반환값: "rate_limit" | "not_found" | "other"
    """
    if any(k in err for k in ["429", "RESOURCE_EXHAUSTED", "quota", "TPM", "RPM",
                               "rate", "exhausted", "tokens per minute"]):
        return "rate_limit"
    if any(k in err for k in ["404", "NOT_FOUND", "not found", "not supported"]):
        return "not_found"
    return "other"


def generate_post(prompt: str, max_retries: int = 3) -> str:
    """
    Gemini로 블로그 포스트 JSON 생성.

    에러 분류별 처리:
    - rate_limit: 65초 대기 후 재시도 (1분 TPM 윈도우 초기화)
    - not_found:  즉시 RuntimeError (재시도 불필요, 설정 문제)
    - other:      10초 대기 후 재시도
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
            err      = str(e)
            err_type = _classify_error(err)

            # 404는 재시도해도 의미 없음 → 즉시 실패
            if err_type == "not_found":
                raise RuntimeError(
                    f"[모델 미존재] GEMINI_MODEL='{GEMINI_MODEL}' 을 확인하세요.\n"
                    f"유효한 모델 ID: https://ai.google.dev/gemini-api/docs/models\n"
                    f"오류: {err[:200]}"
                )

            # 마지막 시도도 실패
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Gemini API {max_retries}회 재시도 모두 실패.\n"
                    f"마지막 오류: {err[:200]}"
                )

            if err_type == "rate_limit":
                print(
                    f"⏳ Rate limit (TPM/RPM 초과) — "
                    f"{RETRY_WAIT_RATE}초 대기 후 재시도 "
                    f"({attempt + 1}/{max_retries})..."
                )
                time.sleep(RETRY_WAIT_RATE)
            else:
                print(
                    f"⚠️  Gemini 오류 (시도 {attempt + 1}): "
                    f"{err[:120]} — {RETRY_WAIT_OTHER}초 후 재시도..."
                )
                time.sleep(RETRY_WAIT_OTHER)

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
