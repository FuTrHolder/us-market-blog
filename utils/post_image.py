#!/usr/bin/env python3
"""
utils/post_image.py
블로그 포스트용 관련 이미지 조달 — 완전 무료

전략 (우선순위):
  1. Unsplash Source API  — 키 불필요, 상업적 무료, 키워드 기반
  2. Gemini Imagen 3      — GEMINI_API_KEY 재사용, 텍스트→이미지 생성
  3. Pillow 폴백          — 기존 generate_thumbnail() (항상 성공)

Unsplash Source API:
  https://source.unsplash.com/1200x628/?{keyword}
  - 무료, 로그인 불필요, 상업적 이용 가능
  - 키워드 기반으로 관련 사진 반환
  - 단순 GET 요청으로 이미지 다운로드
"""

import os
import re
import time
import base64
import hashlib
from pathlib import Path

import requests

OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

# Unsplash Source — 무료 API (키 불필요)
UNSPLASH_URL = "https://source.unsplash.com/1200x628/?{keywords}"

# 금융 관련 키워드 매핑 — 기사 태그/키워드에서 Unsplash 검색어로 변환
FINANCE_KEYWORD_MAP = {
    # 주식/시장
    "stock market":    "stock,market,trading,finance",
    "wall street":     "wall-street,finance,trading",
    "s&p 500":         "stock,market,trading,charts",
    "nasdaq":          "technology,stock,market",
    "dow jones":       "finance,trading,market",
    "trading":         "trading,finance,charts",
    "investing":       "investing,finance,growth",
    "investor":        "investing,finance,business",
    # 기업별
    "nvidia":          "technology,semiconductor,chip",
    "apple":           "apple,technology,innovation",
    "tesla":           "tesla,electric,vehicle",
    "microsoft":       "microsoft,technology,software",
    "amazon":          "amazon,ecommerce,technology",
    "google":          "google,technology,search",
    "meta":            "social-media,technology",
    # 거시경제
    "fed":             "federal-reserve,economy,money",
    "interest rate":   "economy,banking,finance",
    "inflation":       "inflation,economy,money",
    "recession":       "economy,finance,business",
    "gdp":             "economy,growth,business",
    "employment":      "employment,jobs,business",
    # 섹터
    "technology":      "technology,innovation,digital",
    "healthcare":      "healthcare,medical,hospital",
    "energy":          "energy,oil,power",
    "oil":             "oil,energy,petroleum",
    "gold":            "gold,precious-metal,finance",
    "crypto":          "cryptocurrency,bitcoin,blockchain",
    "bitcoin":         "bitcoin,cryptocurrency,digital",
    # 기본 폴백
    "default":         "finance,business,market,economy",
}


def get_post_image(
    post_data: dict,
    article: dict,
    filename: str,
) -> str:
    """
    포스트 내용과 연관된 이미지를 조달합니다.

    우선순위:
      1. Unsplash (무료, 키 불필요)
      2. Gemini Imagen 3 (GEMINI_API_KEY 재사용)
      3. Pillow 폴백

    Args:
        post_data:  generate_blog_post() 결과 dict (title, tags, thumbnail_prompt 포함)
        article:    fetch_article() 결과 dict
        filename:   저장 파일명 (확장자 제외)

    Returns:
        저장된 이미지 파일 경로 (str)
    """

    # 키워드 추출
    keywords = _extract_keywords(post_data, article)
    print(f"[이미지] 추출된 키워드: {keywords}")

    # ── 1순위: Unsplash ───────────────────────────────────
    path = _fetch_unsplash(keywords, filename)
    if path:
        print(f"[이미지] Unsplash 성공: {path}")
        return path

    # ── 2순위: Gemini Imagen ──────────────────────────────
    prompt = post_data.get("thumbnail_prompt", "")
    if not prompt:
        prompt = f"Professional financial news illustration about {', '.join(keywords[:3])}"

    path = _generate_gemini_imagen(prompt, filename)
    if path:
        print(f"[이미지] Gemini Imagen 성공: {path}")
        return path

    # ── 3순위: Pillow 폴백 ────────────────────────────────
    print("[이미지] 폴백: Pillow 썸네일 생성")
    from utils.image_gen import generate_thumbnail
    return generate_thumbnail(
        prompt=prompt,
        filename=filename,
        market_data=None,
        title=post_data.get("title", ""),
        tags=post_data.get("tags", []),
    )


# ─────────────────────────────────────────────────────────
# 1. Unsplash Source API
# ─────────────────────────────────────────────────────────

def _fetch_unsplash(keywords: list[str], filename: str) -> str | None:
    """
    Unsplash Source API로 관련 이미지 다운로드.
    키 불필요, 상업적 무료 (Unsplash License).
    """
    # 키워드를 Unsplash 검색어로 변환
    unsplash_kw = _keywords_to_unsplash(keywords)
    url = UNSPLASH_URL.format(keywords=unsplash_kw)

    try:
        resp = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 BlogBot/1.0"},
            stream=True,
        )

        if resp.status_code != 200:
            print(f"[Unsplash] HTTP {resp.status_code}")
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type:
            print(f"[Unsplash] 이미지 아님: {content_type}")
            return None

        # 확장자 결정
        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"

        output_path = OUTPUT_DIR / f"{filename}_unsplash{ext}"
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # 파일 크기 확인 (너무 작으면 실패)
        size_kb = output_path.stat().st_size / 1024
        if size_kb < 10:
            print(f"[Unsplash] 파일이 너무 작음: {size_kb:.1f}KB")
            output_path.unlink(missing_ok=True)
            return None

        print(f"[Unsplash] 다운로드 완료: {size_kb:.0f}KB")
        return str(output_path)

    except requests.RequestException as e:
        print(f"[Unsplash] 요청 실패: {e}")
        return None


def _keywords_to_unsplash(keywords: list[str]) -> str:
    """키워드 리스트를 Unsplash URL 파라미터로 변환"""
    kw_lower = [k.lower() for k in keywords]

    # 매핑 테이블에서 가장 잘 맞는 검색어 찾기
    for kw in kw_lower:
        for key, unsplash_terms in FINANCE_KEYWORD_MAP.items():
            if key in kw or kw in key:
                return unsplash_terms

    # 직접 키워드 사용 (매핑 없을 때)
    safe_kw = [re.sub(r'[^a-zA-Z0-9]', '-', k) for k in keywords[:3]]
    result  = ",".join(filter(None, safe_kw))
    return result if result else FINANCE_KEYWORD_MAP["default"]


# ─────────────────────────────────────────────────────────
# 2. Gemini Imagen 3
# ─────────────────────────────────────────────────────────

def _generate_gemini_imagen(prompt: str, filename: str) -> str | None:
    """
    Gemini Imagen 3으로 이미지 생성.
    GEMINI_API_KEY 환경변수 재사용 (추가 비용 없음 — 무료 티어 포함).

    Imagen 3 무료 티어:
      - gemini-2.0-flash-preview-image-generation 모델 사용
      - 기존 GEMINI_API_KEY 그대로 사용
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Gemini Imagen] GEMINI_API_KEY 없음, 건너뜀")
        return None

    # 이미지 생성에 적합한 프롬프트로 보강
    enhanced_prompt = _enhance_image_prompt(prompt)
    print(f"[Gemini Imagen] 프롬프트: {enhanced_prompt[:100]}...")

    try:
        # Gemini 2.0 Flash multimodal (이미지 생성 지원)
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash-preview-image-generation:generateContent"
            f"?key={api_key}",
            json={
                "contents": [{
                    "parts": [{"text": enhanced_prompt}]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                }
            },
            timeout=60,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code != 200:
            print(f"[Gemini Imagen] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        parts = (data.get("candidates", [{}])[0]
                     .get("content", {})
                     .get("parts", []))

        for part in parts:
            if "inlineData" in part:
                inline   = part["inlineData"]
                mime     = inline.get("mimeType", "image/png")
                b64_data = inline.get("data", "")

                if not b64_data:
                    continue

                ext = ".png"
                if "jpeg" in mime or "jpg" in mime:
                    ext = ".jpg"
                elif "webp" in mime:
                    ext = ".webp"

                output_path = OUTPUT_DIR / f"{filename}_imagen{ext}"
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))

                size_kb = output_path.stat().st_size / 1024
                print(f"[Gemini Imagen] 생성 완료: {size_kb:.0f}KB")
                return str(output_path)

        print("[Gemini Imagen] 이미지 파트 없음")
        return None

    except Exception as e:
        print(f"[Gemini Imagen] 오류: {e}")
        return None


def _enhance_image_prompt(prompt: str) -> str:
    """
    Imagen 품질을 높이는 프롬프트 보강.
    블로그 썸네일에 적합한 스타일 지시어 추가.
    """
    base = prompt.strip().rstrip(".")

    return (
        f"{base}. "
        "Professional financial blog thumbnail style. "
        "Clean, modern composition. "
        "No text or typography in the image. "
        "High quality, editorial photography style. "
        "1200x628 aspect ratio landscape orientation."
    )


# ─────────────────────────────────────────────────────────
# 키워드 추출
# ─────────────────────────────────────────────────────────

def _extract_keywords(post_data: dict, article: dict) -> list[str]:
    """
    포스트 데이터에서 이미지 검색용 키워드 추출.
    우선순위: tags → title → thumbnail_prompt → article title
    """
    keywords = []

    # 1. 태그에서 추출 (가장 신뢰도 높음)
    tags = post_data.get("tags", [])
    for tag in tags[:5]:
        kw = tag.strip().lower()
        # 일반적인 태그는 제외 (너무 광범위)
        if kw not in {"market analysis", "investing", "wall street", "stock market", "us stock market"}:
            keywords.append(kw)

    # 2. 제목에서 주요 단어 추출
    title = post_data.get("title", "") or article.get("title", "")
    if title:
        # 금융 관련 명사 추출 (대문자로 시작하는 단어, 숫자 포함 단어)
        title_words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b|\b[A-Z]{2,}\b', title)
        keywords.extend([w.lower() for w in title_words[:3]])

    # 3. thumbnail_prompt에서 추출
    thumb_prompt = post_data.get("thumbnail_prompt", "")
    if thumb_prompt:
        # 명사구 추출
        nouns = re.findall(r'\b[a-zA-Z]{4,}\b', thumb_prompt)
        keywords.extend([n.lower() for n in nouns[:3]])

    # 중복 제거 + 빈 문자열 제거
    seen = set()
    result = []
    for k in keywords:
        if k and k not in seen:
            seen.add(k)
            result.append(k)

    # 키워드 없으면 기본값
    if not result:
        result = ["finance", "market", "investing"]

    return result[:5]
