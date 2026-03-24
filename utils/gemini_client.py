#!/usr/bin/env python3
"""
Gemini API Client — 100% FREE
Google AI Studio 무료 티어:
  - gemini-2.0-flash  : 무료 (15 RPM, 1,500 req/day, 1M TPM)
  - gemini-1.5-flash  : 무료 (15 RPM, 1,500 req/day, 1M TPM)

API Key 발급: https://aistudio.google.com/app/apikey
  → Google 계정으로 로그인 → "Create API Key" → 복사
  → 신용카드 불필요, 완전 무료

환경변수: GEMINI_API_KEY
"""

import os
import json
import re
import time
from google import genai
from google.genai import types

# 무료 티어에서 사용할 모델
# gemini-2.0-flash: 가장 최신, 무료, 빠름
GEMINI_MODEL = "gemini-2.0-flash"


def get_client() -> genai.Client:
    """Gemini 클라이언트 생성."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "발급 방법: https://aistudio.google.com/app/apikey\n"
            "Google 계정으로 로그인 후 'Create API Key' 클릭 — 무료"
        )
    return genai.Client(api_key=api_key)


def generate_post(prompt: str, max_retries: int = 3) -> str:
    """
    Gemini로 블로그 포스트 JSON 생성.

    Args:
        prompt: 포스트 생성 프롬프트 (JSON 반환 요청 포함)
        max_retries: 실패 시 재시도 횟수

    Returns:
        Claude가 반환한 JSON 문자열
    """
    client = get_client()

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    # JSON 모드 강제: 항상 유효한 JSON만 반환
                    response_mime_type="application/json",
                    temperature=0.7,          # 창의성 적당히
                    max_output_tokens=4096,
                ),
            )
            return response.text

        except Exception as e:
            err = str(e)
            # 무료 티어 rate limit (15 RPM) 대응
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                wait = 60 * (attempt + 1)
                print(f"⏳ Rate limit hit — {wait}초 대기 후 재시도 ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                if attempt == max_retries - 1:
                    raise
                print(f"⚠️  Gemini 오류 (시도 {attempt+1}): {err[:100]} — 재시도...")
                time.sleep(5)

    raise RuntimeError(f"Gemini API {max_retries}회 재시도 모두 실패")


def parse_json_response(raw: str) -> dict:
    """
    Gemini 응답에서 JSON 파싱.
    response_mime_type='application/json' 설정 시 마크다운 없이 순수 JSON 반환.
    """
    raw = raw.strip()

    # 혹시 ```json 펜스가 있으면 제거
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 마지막 수단: JSON 블록 추출
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"JSON 파싱 실패:\n{raw[:300]}")
