#!/usr/bin/env python3
"""
Gemini API Client — 100% FREE
Google AI Studio 무료 티어: gemini-2.0-flash (1,500 req/day, 15 RPM)
API Key: https://aistudio.google.com/app/apikey
"""

import os
import json
import re
import time
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.0-flash"

# ✅ 수정 2: 프롬프트 전송 전 토큰 크기 제한을 위해 데이터 압축 함수 추가
MAX_DATA_CHARS = 3000  # 프롬프트에 포함할 시장 데이터 최대 문자 수


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "발급: https://aistudio.google.com/app/apikey (무료)"
        )
    return genai.Client(api_key=api_key)


def compress_market_data(market_data: dict) -> str:
    """
    ✅ 수정 2: 시장 데이터를 Gemini 토큰 한도 내로 압축.
    전체 JSON 대신 핵심 수치만 추출해서 간결한 텍스트로 변환.
    Rate Limit / 토큰 초과 오류의 근본 원인 해결.
    """
    lines = []

    # 지수 데이터
    if "indices" in market_data:
        lines.append("[Indices]")
        for name, d in market_data["indices"].items():
            if isinstance(d, dict) and "close" in d:
                chg = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg}%)")

    # 섹터 데이터
    if "sectors" in market_data:
        lines.append("[Sectors]")
        for name, d in market_data["sectors"].items():
            if isinstance(d, dict) and "change_pct" in d:
                chg = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {sign}{chg}%")

    # Top movers
    if "movers" in market_data:
        mv = market_data["movers"]
        if "gainers" in mv and mv["gainers"]:
            lines.append("[Top Gainers]")
            for g in mv["gainers"][:3]:
                lines.append(f"  {g['symbol']}: +{g['change_pct']}% @ ${g['price']}")
        if "losers" in mv and mv["losers"]:
            lines.append("[Top Losers]")
            for g in mv["losers"][:3]:
                lines.append(f"  {g['symbol']}: {g['change_pct']}% @ ${g['price']}")

    # 선물 데이터
    if "futures" in market_data:
        lines.append("[Futures]")
        for name, d in market_data["futures"].items():
            if isinstance(d, dict) and "close" in d:
                chg = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg}%)")

    # 프리마켓 (아시아/유럽)
    if "premarket" in market_data:
        lines.append("[Asia/Europe Markets]")
        for name, d in market_data["premarket"].items():
            if isinstance(d, dict) and "close" in d:
                chg = d.get("change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  {name}: {d['close']} ({sign}{chg}%)")

    # 실적 캘린더
    if "earnings_calendar" in market_data and market_data["earnings_calendar"]:
        lines.append("[Earnings Today]")
        for e in market_data["earnings_calendar"][:5]:
            eps = e.get("eps_estimate")
            lines.append(f"  {e.get('symbol')} ({e.get('name')}): EPS est={eps}")

    # 경제 지표
    if "economic_calendar" in market_data and market_data["economic_calendar"]:
        lines.append("[Economic Data Released]")
        for e in market_data["economic_calendar"][:5]:
            lines.append(
                f"  {e.get('event')}: actual={e.get('actual')}, "
                f"prev={e.get('previous')}, impact={e.get('impact')}"
            )

    result = "\n".join(lines)

    # 최대 길이 초과 시 뒤쪽 잘라내기
    if len(result) > MAX_DATA_CHARS:
        result = result[:MAX_DATA_CHARS] + "\n  ...(truncated)"

    return result


def generate_post(prompt: str, max_retries: int = 3) -> str:
    """
    Gemini로 블로그 포스트 JSON 생성.
    ✅ 수정 3: Rate limit 시 재시도 간격 증가 + RESOURCE_EXHAUSTED 처리 추가
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
                    max_output_tokens=4096,
                ),
            )
            return response.text

        except Exception as e:
            err = str(e)
            is_rate_limit = any(k in err for k in [
                "429", "quota", "rate", "RESOURCE_EXHAUSTED", "exhausted"
            ])

            if is_rate_limit:
                # ✅ 수정 3: 재시도 대기 시간을 더 길게 (60→90초 간격)
                wait = 90 * (attempt + 1)
                print(f"⏳ Rate limit — {wait}초 대기 후 재시도 ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                if attempt == max_retries - 1:
                    raise
                print(f"⚠️  Gemini 오류 (시도 {attempt+1}): {err[:120]} — 재시도...")
                time.sleep(10)

    raise RuntimeError(f"Gemini API {max_retries}회 재시도 모두 실패")


def parse_json_response(raw: str) -> dict:
    """Gemini 응답에서 JSON 파싱."""
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"JSON 파싱 실패:\n{raw[:300]}")
