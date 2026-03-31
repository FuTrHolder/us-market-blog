#!/usr/bin/env python3
"""
utils/fact_checker.py
실시간 팩트체크 — 2단계 분리 방식

[문제 원인]
  Search Grounding 활성화 시 Gemini 응답 구조가 달라짐:
  - response.text 가 None 또는 검색 설명 텍스트 혼재 반환
  - response_mime_type="application/json" 을 Grounding과 동시에 사용 불가
  → JSON 파싱 실패로 "응답 파싱 오류" 발생

[해결: 2단계 분리]
  1단계 (Grounding 호출): Google 검색으로 관련 최신 정보 수집
                          → 순수 텍스트 응답, JSON 강제 안 함
  2단계 (JSON 호출):      수집된 검색 컨텍스트 + 기사 내용으로
                          structured JSON 팩트체크 결과 생성
                          → response_mime_type="application/json" 사용 가능

[무료 사용]
  - 기존 GEMINI_API_KEY 그대로 사용
  - Gemini 2.5 Flash-Lite: 무료 1,500 req/day
  - 기사당 API 호출 2회 (1단계 + 2단계)
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types

KST              = timezone(timedelta(hours=9))
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
    2단계 실시간 팩트체크.
    1단계: Google Search Grounding으로 관련 정보 수집
    2단계: 수집 결과 기반 JSON 팩트체크 생성

    Returns:
        {
          "verdict", "credibility_score", "key_claims",
          "issues"(한글), "related_information"(한글),
          "blog_angle", "proceed_to_publish", "summary_for_blog",
          "search_sources": [...],
          "grounding_used": bool,
        }
    """
    title = article.get("title", "")
    text  = article.get("text", "")[:3000]
    today = datetime.now(KST).strftime("%B %d, %Y")

    # ── 1단계: Search Grounding으로 컨텍스트 수집 ────────
    print("[팩트체크] 1단계: Google Search로 실시간 정보 수집 중...")
    search_context, search_sources, grounding_used = _collect_search_context(
        title, text, today
    )

    # ── 2단계: 수집된 컨텍스트로 JSON 팩트체크 생성 ──────
    print(f"[팩트체크] 2단계: 팩트체크 JSON 생성 중... "
          f"(검색 컨텍스트: {len(search_context)}자)")
    try:
        result = _generate_fact_check_json(
            title, text, today, comment, search_context
        )
        result["search_sources"]  = search_sources
        result["grounding_used"]  = grounding_used
        print(f"[팩트체크] 완료 — verdict={result.get('verdict')}, "
              f"score={result.get('credibility_score')}, "
              f"sources={len(search_sources)}")
        return result

    except Exception as e:
        print(f"[팩트체크] 2단계 실패: {e}")
        return _fallback_result(str(e))


# ─────────────────────────────────────────────────────────
# 1단계: Search Grounding으로 컨텍스트 수집
# ─────────────────────────────────────────────────────────

def _collect_search_context(
    title: str,
    text: str,
    today: str,
) -> tuple[str, list, bool]:
    """
    Google Search Grounding으로 기사 관련 최신 정보를 텍스트로 수집.
    JSON 강제 없이 자유로운 텍스트 응답 → 파싱 오류 없음.

    Returns:
        (search_context_text, sources_list, grounding_used)
    """
    client = get_client()

    prompt = (
        f"Today is {today}.\n\n"
        f"I need to fact-check this financial news article:\n"
        f"Title: {title}\n\n"
        f"Please search Google for:\n"
        f"1. Current status of the main claims in this article\n"
        f"2. Recent news about the companies/events mentioned\n"
        f"3. Any contradicting or supporting information published today\n\n"
        f"Summarize what you find in 3-5 sentences. "
        f"Focus on factual information only."
    )

    try:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())

        response = get_client().models.generate_content(
            model=FACT_CHECK_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        # ── 응답 텍스트 안전하게 추출 ────────────────────
        context_text = _safe_extract_text(response)

        # ── 출처 추출 ─────────────────────────────────────
        sources = _extract_grounding_sources(response)

        print(f"[1단계] 검색 완료 — 컨텍스트 {len(context_text)}자, "
              f"출처 {len(sources)}개")
        return context_text, sources, True

    except Exception as e:
        print(f"[1단계] Search Grounding 실패 ({e}), 컨텍스트 없이 진행")
        return "", [], False


def _safe_extract_text(response) -> str:
    """
    Gemini 응답에서 텍스트를 안전하게 추출.
    response.text 가 None 인 경우 parts에서 직접 수집.
    """
    # 방법 1: response.text 직접 접근
    try:
        if response.text:
            return response.text
    except Exception:
        pass

    # 방법 2: candidates → content → parts 순회
    try:
        parts_text = []
        for candidate in (response.candidates or []):
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in (getattr(content, "parts", []) or []):
                t = getattr(part, "text", None)
                if t:
                    parts_text.append(t)
        return " ".join(parts_text)
    except Exception as e:
        print(f"[텍스트 추출] 오류: {e}")
        return ""


def _extract_grounding_sources(response) -> list:
    """Gemini grounding 메타데이터에서 출처 URL 추출"""
    sources = []
    try:
        candidate = (response.candidates or [None])[0]
        if not candidate:
            return sources

        metadata = getattr(candidate, "grounding_metadata", None)
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

    return sources[:5]


# ─────────────────────────────────────────────────────────
# 2단계: 수집된 컨텍스트로 JSON 팩트체크 생성
# ─────────────────────────────────────────────────────────

def _generate_fact_check_json(
    title: str,
    text: str,
    today: str,
    comment: str,
    search_context: str,
) -> dict:
    """
    Search Grounding 없이 순수 JSON 생성.
    response_mime_type="application/json" 사용 가능 → 파싱 오류 없음.
    1단계에서 수집한 검색 컨텍스트를 프롬프트에 포함.
    """
    client = get_client()

    # 검색 컨텍스트가 있으면 포함, 없으면 학습 데이터 기반임을 명시
    if search_context:
        context_block = (
            f"\n[Real-time Search Results from Google - {today}]\n"
            f"{search_context}\n"
        )
    else:
        context_block = (
            "\n[Note: Real-time search unavailable. "
            "Analysis based on training data only.]\n"
        )

    prompt = f"""You are a professional fact-checker for financial and market news.
Today: {today}
{context_block}
Article Title: {title}
Article Content:
{text[:2500]}
{"User comment: " + comment if comment else ""}

Based on the search results above (if available) and your knowledge, fact-check this article.

OUTPUT — ONLY valid JSON:
{{
  "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
  "credibility_score": <integer 0-100>,
  "key_claims": [
    {{"claim": "claim from article", "status": "VERIFIED|FALSE|UNVERIFIABLE", "note": "evidence"}}
  ],
  "issues": ["지적사항1 (한글로 작성)", "지적사항2 (한글로 작성)"],
  "related_information": "검색으로 확인된 관련 최신 시장 동향 2-3문장 (한글로 작성)",
  "blog_angle": "Suggested angle/hook for the blog post in English",
  "proceed_to_publish": <true if credibility_score >= 60 and verdict != "FALSE">,
  "summary_for_blog": "3-4 sentence summary of verified facts in English"
}}"""

    response = client.models.generate_content(
        model=FACT_CHECK_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",   # JSON 전용 → 파싱 안전
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    raw = _safe_extract_text(response)
    if not raw:
        raise ValueError("2단계 응답이 비어 있습니다.")

    return _parse_json_safe(raw)


# ─────────────────────────────────────────────────────────
# JSON 파싱 + 폴백
# ─────────────────────────────────────────────────────────

def _parse_json_safe(raw: str) -> dict:
    """JSON 파싱 — 마크다운 코드블록, 앞뒤 텍스트 제거 후 파싱"""
    raw = raw.strip()
    # ```json ... ``` 코드블록 제거
    raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^```\s*',     '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$',     '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    # 직접 파싱 시도
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # JSON 블록만 추출 후 재시도
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    print(f"[JSON 파싱] 실패. 원본 앞 300자: {raw[:300]}")
    raise ValueError(f"JSON 파싱 불가: {raw[:100]}")


def _fallback_result(error_msg: str = "") -> dict:
    """모든 시도 실패 시 반환하는 기본 결과 (게시 중단)"""
    return {
        "verdict":            "UNVERIFIED",
        "credibility_score":  0,
        "key_claims":         [],
        "issues":             [f"팩트체크 오류: {error_msg[:80]}"],
        "related_information": "팩트체크 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "blog_angle":         "",
        "proceed_to_publish": False,
        "summary_for_blog":   "",
        "search_sources":     [],
        "grounding_used":     False,
    }
