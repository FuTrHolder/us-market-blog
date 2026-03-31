#!/usr/bin/env python3
"""
utils/fact_checker.py
실시간 팩트체크 — Gemini 2.5 Flash + Google Search Grounding

기존 Gemini 팩트체크의 한계:
  - 학습 데이터 컷오프 이후 실시간 정보 모름
  - 최신 주가, 실적 발표, 금리 결정 등 검증 불가

개선 방법:
  - google_search 툴을 활성화하여 팩트체크 시에만 실시간 웹 검색 수행
  - 기사 핵심 주장을 추출 → 각 주장을 검색으로 교차 검증
  - 검색 결과 출처(grounding chunks)를 신뢰도 점수에 반영

무료 사용:
  - 기존 GEMINI_API_KEY 그대로 사용 (추가 키 불필요)
  - Gemini 2.5 Flash-Lite: 무료 티어 1,500 req/day
  - Search Grounding: Gemini 2.5 이하 모델은 프롬프트당 과금
    → 단, 무료 티어(Free tier)에서는 무료로 사용 가능
  - 팩트체크는 기사당 1회 호출이므로 일일 한도 내 충분히 사용 가능

구조:
  1. 1단계: 기사에서 핵심 주장 추출 (Search Grounding 없이, 토큰 절약)
  2. 2단계: 핵심 주장을 Google Search Grounding으로 실시간 검증
  3. 3단계: 검증 결과 종합 → 신뢰도 점수 + 판정
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types

KST = timezone(timedelta(hours=9))

# ── 모델 설정 ──────────────────────────────────────────────
# Search Grounding은 gemini-2.5-flash-lite 에서 무료 티어 사용 가능
FACT_CHECK_MODEL = "gemini-2.5-flash-lite"


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def fact_check_with_search(article: dict, comment: str = "") -> dict:
    """
    Google Search Grounding을 활용한 실시간 팩트체크.

    Args:
        article: fetch_article() 결과 dict
        comment: 사용자 추가 코멘트

    Returns:
        {
          "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
          "credibility_score": 0-100,
          "key_claims": [...],
          "issues": [...],           # 한글
          "related_information": "", # 한글
          "blog_angle": "",
          "proceed_to_publish": bool,
          "summary_for_blog": "",
          "search_sources": [...],   # 검색에서 찾은 출처 URL 목록
          "grounding_used": bool,    # Search Grounding 사용 여부
        }
    """
    title = article.get("title", "")
    text  = article.get("text", "")[:3000]
    today = datetime.now(KST).strftime("%B %d, %Y")

    print("[팩트체크] Google Search Grounding으로 실시간 검증 시작...")

    # ── 1단계: Search Grounding으로 실시간 팩트체크 ─────────
    try:
        result = _run_grounded_fact_check(title, text, today, comment)
        result["grounding_used"] = True
        print(f"[팩트체크] Search Grounding 완료 — score={result.get('credibility_score')}, "
              f"sources={len(result.get('search_sources', []))}")
        return result

    except Exception as e:
        err = str(e)
        print(f"[팩트체크] Search Grounding 실패: {err[:150]}")
        print("[팩트체크] 폴백: 기존 Gemini 팩트체크로 전환...")

        # ── 폴백: Search Grounding 없이 기존 방식 ────────────
        try:
            result = _run_basic_fact_check(title, text, today, comment)
            result["grounding_used"] = False
            result["search_sources"] = []
            return result
        except Exception as e2:
            print(f"[팩트체크] 기본 팩트체크도 실패: {e2}")
            # 최소 결과 반환 (게시 중단)
            return {
                "verdict": "UNVERIFIED",
                "credibility_score": 0,
                "key_claims": [],
                "issues": ["팩트체크 API 오류로 검증 불가"],
                "related_information": "검증 중 오류가 발생했습니다.",
                "blog_angle": "",
                "proceed_to_publish": False,
                "summary_for_blog": "",
                "search_sources": [],
                "grounding_used": False,
            }


# ─────────────────────────────────────────────────────────
# 1단계: Google Search Grounding 팩트체크
# ─────────────────────────────────────────────────────────

def _run_grounded_fact_check(
    title: str,
    text: str,
    today: str,
    comment: str,
) -> dict:
    """
    google_search 툴을 활성화해서 실시간으로 팩트체크.
    Gemini가 필요하다고 판단할 때 자동으로 Google 검색을 수행.
    """
    client = get_client()

    prompt = f"""You are a professional real-time fact-checker for financial and market news.
Today's date: {today}

Article Title: {title}
Article Content:
{text}
{"User comment: " + comment if comment else ""}

IMPORTANT: Use Google Search to verify the following:
1. Search for the article's KEY CLAIMS (company names, stock prices, earnings figures, economic data, Fed decisions)
2. Cross-reference with multiple recent sources
3. Check if numbers/statistics match what's reported elsewhere TODAY
4. Identify any claims that contradict current real-world data

After searching, provide your fact-check result.

OUTPUT — ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
  "credibility_score": <integer 0-100>,
  "key_claims": [
    {{"claim": "exact claim from article", "status": "VERIFIED|FALSE|UNVERIFIABLE", "search_note": "what search found"}}
  ],
  "issues": ["지적사항1 (한글로 작성)", "지적사항2 (한글로 작성)"],
  "related_information": "검색으로 확인된 관련 최신 시장 동향 2-3문장 (한글로 작성)",
  "blog_angle": "Suggested angle/hook for the blog post in English",
  "proceed_to_publish": <true if credibility_score >= 60 and verdict != "FALSE">,
  "summary_for_blog": "3-4 sentence summary of verified facts in English for blog writing"
}}"""

    # ── Search Grounding 활성화 ───────────────────────────
    grounding_tool = types.Tool(google_search=types.GoogleSearch())

    response = client.models.generate_content(
        model=FACT_CHECK_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=0.1,          # 팩트체크는 낮은 temperature 권장
            max_output_tokens=2048,
        ),
    )

    raw_text = response.text or ""

    # ── 검색 출처 추출 ────────────────────────────────────
    search_sources = _extract_grounding_sources(response)

    # ── JSON 파싱 ─────────────────────────────────────────
    result = _parse_fact_check_json(raw_text)
    result["search_sources"] = search_sources

    return result


def _extract_grounding_sources(response) -> list:
    """
    Gemini grounding 메타데이터에서 검색 출처 URL 목록 추출.
    """
    sources = []
    try:
        metadata = (
            response.candidates[0]
            .grounding_metadata
            if response.candidates else None
        )
        if not metadata:
            return sources

        chunks = getattr(metadata, "grounding_chunks", []) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web:
                uri   = getattr(web, "uri",   "")
                title = getattr(web, "title", "")
                if uri:
                    sources.append({"url": uri, "title": title})
    except Exception as e:
        print(f"[출처 추출] 오류: {e}")

    return sources[:5]  # 최대 5개


# ─────────────────────────────────────────────────────────
# 폴백: 기존 방식 (Search Grounding 없음)
# ─────────────────────────────────────────────────────────

def _run_basic_fact_check(
    title: str,
    text: str,
    today: str,
    comment: str,
) -> dict:
    """Search Grounding 없이 Gemini 지식만으로 팩트체크 (폴백)"""
    from utils.gemini_client import generate_post, parse_json_response

    prompt = f"""You are a professional fact-checker for financial and market news.

Today: {today}
Article Title: {title}
Article Content (first 3000 chars):
{text}

{"User comment: " + comment if comment else ""}

TASK: Analyze this article based on your training knowledge.
Note: You cannot access real-time data in this mode.

OUTPUT — ONLY valid JSON:
{{
  "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
  "credibility_score": <integer 0-100>,
  "key_claims": [
    {{"claim": "...", "status": "VERIFIED|FALSE|UNVERIFIABLE", "search_note": "based on training data only"}}
  ],
  "issues": ["지적사항1 (한글로 작성)", "지적사항2 (한글로 작성)"],
  "related_information": "관련 시장 동향 2-3문장 (한글로 작성, 실시간 검색 미사용)",
  "blog_angle": "Suggested angle/hook for the blog post",
  "proceed_to_publish": <true if credibility_score >= 60 and verdict != "FALSE">,
  "summary_for_blog": "3-4 sentence summary of verified facts for blog writing"
}}"""

    raw    = generate_post(prompt)
    result = parse_json_response(raw)
    return result


# ─────────────────────────────────────────────────────────
# JSON 파싱
# ─────────────────────────────────────────────────────────

def _parse_fact_check_json(raw: str) -> dict:
    """Gemini 응답에서 JSON 파싱 (마크다운 코드블록 처리 포함)"""
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$',    '', raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass

    # 파싱 실패 시 기본값 반환
    print(f"[팩트체크] JSON 파싱 실패, 기본값 반환. 원본: {raw[:200]}")
    return {
        "verdict": "UNVERIFIED",
        "credibility_score": 50,
        "key_claims": [],
        "issues": ["응답 파싱 오류"],
        "related_information": "파싱 오류로 정보를 가져오지 못했습니다.",
        "blog_angle": "",
        "proceed_to_publish": False,
        "summary_for_blog": "",
    }
