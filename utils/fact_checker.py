#!/usr/bin/env python3
"""
utils/fact_checker.py
실시간 팩트체크 — 2단계 분리 방식

[수정 사항]
1. 모델 ID: gemini-2.5-flash-lite (stable GA) 사용
   - gemini-2.5-flash-lite-preview-09-2025 는 2026-03-31 종료됨

2. Search Grounding 강제 실행:
   - Gemini가 검색 여부를 스스로 판단할 경우 최신 기사임에도 건너뜀
   - dynamic_retrieval_config threshold=0.0 으로 항상 검색 실행 강제

3. 지적 사항 + 관련 정보 한글 강제:
   - 2단계 프롬프트에 시스템 레벨 한글 지시 추가

4. 2단계 분리 구조 유지:
   - 1단계: Grounding 전용 (자유 텍스트, 파싱 오류 없음)
   - 2단계: JSON 전용 (response_mime_type=application/json)
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types

KST              = timezone(timedelta(hours=9))
FACT_CHECK_MODEL = "gemini-2.5-flash-lite"   # stable GA 버전


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
    1단계: Search Grounding으로 실시간 정보 수집 (강제 실행)
    2단계: 수집된 컨텍스트 + JSON 응답 생성
    """
    title = article.get("title", "")
    text  = article.get("text", "")[:3000]
    today = datetime.now(KST).strftime("%B %d, %Y")

    print("[팩트체크] 1단계: Google Search 실시간 정보 수집 중...")
    search_context, search_sources, grounding_used = _collect_search_context(
        title, text, today
    )

    print(f"[팩트체크] 2단계: JSON 팩트체크 생성 중 "
          f"(컨텍스트 {len(search_context)}자, 출처 {len(search_sources)}개)...")
    try:
        result = _generate_fact_check_json(
            title, text, today, comment, search_context
        )
        result["search_sources"] = search_sources
        result["grounding_used"] = grounding_used
        print(f"[팩트체크] 완료 — verdict={result.get('verdict')}, "
              f"score={result.get('credibility_score')}")
        return result

    except Exception as e:
        print(f"[팩트체크] 2단계 실패: {e}")
        return _fallback_result(str(e))


# ─────────────────────────────────────────────────────────
# 1단계: Search Grounding (항상 검색 강제)
# ─────────────────────────────────────────────────────────

def _collect_search_context(
    title: str,
    text: str,
    today: str,
) -> tuple[str, list, bool]:
    """
    dynamic_retrieval_config threshold=0.0 으로 검색을 항상 강제 실행.
    Gemini 판단에 맡기면 "이미 알고 있다"고 검색을 건너뛰는 경우 방지.
    """
    client = get_client()

    # 검색 쿼리로 쓸 핵심 키워드만 추출 (토큰 절약)
    keywords = _extract_search_keywords(title, text)
    prompt = (
        f"Today is {today}. Search Google for the latest information about:\n"
        f"{keywords}\n\n"
        f"Summarize what you find about:\n"
        f"1. Current status of companies/events mentioned\n"
        f"2. Recent market data or economic figures cited\n"
        f"3. Any contradicting reports from today\n\n"
        f"Be concise. 4-6 sentences maximum."
    )

    try:
        # ── threshold=0.0 → 검색 항상 강제 실행 ─────────────
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch(
                dynamic_retrieval_config=types.DynamicRetrievalConfig(
                    mode=types.DynamicRetrievalConfigMode.MODE_DYNAMIC,
                    dynamic_threshold=0.0,   # 0.0 = 항상 검색
                )
            )
        )

        response = client.models.generate_content(
            model=FACT_CHECK_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.1,
                max_output_tokens=512,
            ),
        )

        context_text = _safe_extract_text(response)
        sources      = _extract_grounding_sources(response)

        print(f"[1단계] 완료 — 컨텍스트 {len(context_text)}자, 출처 {len(sources)}개")
        return context_text, sources, (len(sources) > 0)

    except Exception as e:
        err = str(e)
        print(f"[1단계] Grounding 실패: {err[:120]}")

        # DynamicRetrievalConfig 미지원 시 기본 Grounding으로 재시도
        if "dynamic" in err.lower() or "DynamicRetrievalConfig" in err:
            print("[1단계] DynamicRetrievalConfig 미지원 → 기본 Grounding 재시도...")
            return _collect_search_context_basic(title, text, today)

        return "", [], False


def _collect_search_context_basic(
    title: str,
    text: str,
    today: str,
) -> tuple[str, list, bool]:
    """DynamicRetrievalConfig 없는 기본 Grounding 폴백"""
    client   = get_client()
    keywords = _extract_search_keywords(title, text)

    prompt = (
        f"Today is {today}. "
        f"Search for the latest news and market data about: {keywords}. "
        f"Summarize key facts in 4-5 sentences."
    )
    try:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        response = client.models.generate_content(
            model=FACT_CHECK_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.1,
                max_output_tokens=512,
            ),
        )
        context_text = _safe_extract_text(response)
        sources      = _extract_grounding_sources(response)
        print(f"[1단계-기본] 완료 — 컨텍스트 {len(context_text)}자, 출처 {len(sources)}개")
        return context_text, sources, (len(sources) > 0)
    except Exception as e2:
        print(f"[1단계-기본] 실패: {e2}")
        return "", [], False


def _extract_search_keywords(title: str, text: str) -> str:
    """기사 제목/본문에서 검색 핵심 키워드 추출"""
    # 제목에서 따옴표 안 키워드, 대문자 단어, 티커, 숫자% 패턴 추출
    keywords = []
    # 제목 전체
    if title:
        keywords.append(title[:120])
    # 본문에서 회사명/수치 패턴
    patterns = re.findall(
        r'\b[A-Z][A-Za-z]{2,}\b|\b\d+\.?\d*%|\$\d+[BbMmKk]?\b',
        text[:500]
    )
    if patterns:
        keywords.extend(patterns[:5])
    return ", ".join(keywords[:3]) if keywords else title[:100]


# ─────────────────────────────────────────────────────────
# 2단계: JSON 팩트체크 생성
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
    response_mime_type="application/json" 사용 → 파싱 안전.
    """
    client = get_client()

    if search_context:
        context_block = (
            f"\n=== Real-time Google Search Results ({today}) ===\n"
            f"{search_context}\n"
            f"=== End of Search Results ===\n"
        )
        context_note = "Use the search results above as primary evidence for verification."
    else:
        context_block = ""
        context_note  = "No real-time search available. Use training knowledge only."

    prompt = f"""You are a professional fact-checker for financial and market news.
Today: {today}
{context_block}
Article Title: {title}
Article Content:
{text[:2500]}
{"User comment: " + comment if comment else ""}

{context_note}

CRITICAL LANGUAGE RULES:
- "issues" field: MUST be written in Korean (한글)
- "related_information" field: MUST be written in Korean (한글)
- All other fields: English

Scoring guide:
- 80-100: Claims verified by search results
- 60-79:  Mostly verifiable, minor uncertainties
- 40-59:  Mixed — some claims unverifiable or contradicted
- 0-39:   Major claims contradicted or unverifiable

OUTPUT — ONLY valid JSON:
{{
  "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
  "credibility_score": <integer 0-100>,
  "key_claims": [
    {{"claim": "specific claim from article", "status": "VERIFIED|FALSE|UNVERIFIABLE", "note": "evidence from search or knowledge"}}
  ],
  "issues": ["한글로 작성된 지적사항1", "한글로 작성된 지적사항2"],
  "related_information": "검색 결과 기반 관련 최신 시장 동향 2-3문장. 반드시 한글로 작성.",
  "blog_angle": "Suggested angle for the blog post in English",
  "proceed_to_publish": <true if credibility_score >= 60 and verdict != "FALSE">,
  "summary_for_blog": "3-4 sentence factual summary in English for blog writing"
}}"""

    response = client.models.generate_content(
        model=FACT_CHECK_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    raw = _safe_extract_text(response)
    if not raw:
        raise ValueError("2단계 응답이 비어 있습니다.")

    return _parse_json_safe(raw)


# ─────────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────────

def _safe_extract_text(response) -> str:
    """response.text 가 None 일 때 parts에서 안전하게 추출"""
    try:
        if response.text:
            return response.text
    except Exception:
        pass
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
    """grounding_metadata에서 출처 URL 추출"""
    sources = []
    try:
        candidate = (response.candidates or [None])[0]
        if not candidate:
            return sources
        metadata = getattr(candidate, "grounding_metadata", None)
        if not metadata:
            return sources
        for chunk in (getattr(metadata, "grounding_chunks", []) or []):
            web = getattr(chunk, "web", None)
            if web:
                uri   = getattr(web, "uri",   "")
                title = getattr(web, "title", "")
                if uri:
                    sources.append({"url": uri, "title": title})
    except Exception as e:
        print(f"[출처 추출] 오류: {e}")
    return sources[:5]


def _parse_json_safe(raw: str) -> dict:
    """JSON 파싱 — 코드블록 제거 후 파싱, 실패 시 예외 발생"""
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^```\s*',     '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$',     '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    print(f"[JSON 파싱] 실패. 원본: {raw[:300]}")
    raise ValueError(f"JSON 파싱 불가: {raw[:100]}")


def _fallback_result(error_msg: str = "") -> dict:
    """모든 시도 실패 시 게시 중단 결과 반환"""
    return {
        "verdict":             "UNVERIFIED",
        "credibility_score":   0,
        "key_claims":          [],
        "issues":              [f"팩트체크 오류: {error_msg[:80]}"],
        "related_information": "팩트체크 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "blog_angle":          "",
        "proceed_to_publish":  False,
        "summary_for_blog":    "",
        "search_sources":      [],
        "grounding_used":      False,
    }
