#!/usr/bin/env python3
"""
utils/post_image.py
블로그 포스트용 관련 이미지 조달

우선순위:
  1. Gemini Imagen 3  — 기사 내용 기반 AI 이미지 생성 (1순위)
  2. Unsplash         — 키워드 기반 무료 사진 (폴백)
  3. Pillow           — 텍스트 썸네일 (최후 폴백)

변경 사항:
  - Gemini Imagen을 1순위로 변경
  - 기사 제목/태그/본문 기반 고품질 프롬프트 자동 생성 추가
  - 프롬프트 품질 향상으로 기사 내용과 연관된 이미지 생성
"""

import os
import re
import base64
from pathlib import Path

import requests

OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

# Gemini Imagen 모델
IMAGEN_MODEL = "gemini-3-flash-image"

# Unsplash 폴백
UNSPLASH_URL = "https://source.unsplash.com/1200x628/?{keywords}"

FINANCE_KEYWORD_MAP = {
    "stock market":    "stock,market,trading,finance",
    "wall street":     "wall-street,finance,trading",
    "s&p 500":         "stock,market,trading",
    "nasdaq":          "technology,stock,market",
    "dow jones":       "finance,trading,market",
    "fed":             "federal-reserve,economy,money",
    "interest rate":   "economy,banking,finance",
    "inflation":       "inflation,economy,money",
    "nvidia":          "technology,semiconductor,chip",
    "apple":           "apple,technology,innovation",
    "tesla":           "tesla,electric,vehicle",
    "microsoft":       "microsoft,technology,software",
    "amazon":          "amazon,ecommerce,technology",
    "energy":          "energy,oil,power",
    "oil":             "oil,energy,petroleum",
    "gold":            "gold,precious-metal,finance",
    "crypto":          "cryptocurrency,bitcoin,blockchain",
    "default":         "finance,business,market,economy",
}


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def get_post_image(
    post_data: dict,
    article:   dict,
    filename:  str,
) -> str:
    """
    기사 내용 기반 이미지 조달.
    1순위: Gemini Imagen (AI 생성, 기사 내용 반영)
    2순위: Unsplash (키워드 검색)
    3순위: Pillow (텍스트 썸네일)
    """
    title   = post_data.get("title", "") or article.get("title", "")
    tags    = post_data.get("tags", [])
    summary = post_data.get("summary_for_blog", "") or article.get("text", "")[:300]

    # ── 1순위: Gemini Imagen ──────────────────────────────
    imagen_prompt = _build_imagen_prompt(
        title   = title,
        tags    = tags,
        summary = summary,
        raw_prompt = post_data.get("thumbnail_prompt", ""),
    )
    print(f"[이미지] Gemini Imagen 시도...")
    print(f"[이미지] 프롬프트: {imagen_prompt[:120]}...")

    path = _generate_gemini_imagen(imagen_prompt, filename)
    if path:
        print(f"[이미지] Gemini Imagen 성공: {path}")
        return path

    # ── 2순위: Unsplash ───────────────────────────────────
    keywords = _extract_keywords(post_data, article)
    print(f"[이미지] Unsplash 폴백 시도 (키워드: {keywords})")
    path = _fetch_unsplash(keywords, filename)
    if path:
        print(f"[이미지] Unsplash 성공: {path}")
        return path

    # ── 3순위: Pillow ─────────────────────────────────────
    print("[이미지] Pillow 폴백")
    from utils.image_gen import generate_thumbnail
    return generate_thumbnail(
        prompt     = imagen_prompt,
        filename   = filename,
        market_data= None,
        title      = title,
        tags       = tags,
    )


# ─────────────────────────────────────────────────────────
# 프롬프트 생성 (핵심 개선)
# ─────────────────────────────────────────────────────────

# 태그 → 시각적 장면 매핑
TAG_SCENE_MAP = {
    "iran":           "Middle East oil tankers in the Strait of Hormuz at sunset, tense atmosphere",
    "war":            "geopolitical tension, military ships in strategic waterway, dramatic sky",
    "oil":            "oil derricks and tankers at sea, industrial energy infrastructure",
    "fed":            "Federal Reserve building in Washington DC, serious financial atmosphere",
    "interest rate":  "Federal Reserve meeting room, economists at conference table",
    "inflation":      "shopping cart with rising price tags, consumer goods store",
    "recession":      "empty trading floor, worried traders, red financial screens",
    "earnings":       "corporate headquarters building, executives in boardroom",
    "nvidia":         "advanced GPU chips and AI server racks, blue tech lighting",
    "apple":          "Apple headquarters campus, modern glass architecture",
    "tesla":          "Tesla electric vehicles on highway, futuristic atmosphere",
    "microsoft":      "modern tech campus, software engineers, digital displays",
    "amazon":         "large warehouse fulfillment center, logistics robots",
    "crypto":         "digital blockchain network visualization, glowing nodes",
    "bitcoin":        "Bitcoin gold coin, digital currency concept, blue light",
    "bull market":    "bull statue on Wall Street, triumphant traders, green screens",
    "bear market":    "bear statue, anxious traders, red financial screens",
    "rally":          "stock exchange floor with traders celebrating, green ticker boards",
    "crash":          "traders watching plummeting stock screens, urgent atmosphere",
    "nasdaq":         "tech company headquarters, Silicon Valley modern architecture",
    "s&p 500":        "New York Stock Exchange trading floor, busy traders",
    "dow jones":      "Wall Street financial district, classic stone buildings",
    "gold":           "gold bars stacked in a vault, gleaming precious metals",
    "default":        "New York Stock Exchange trading floor, traders monitoring screens",
}

def _build_imagen_prompt(
    title:      str,
    tags:       list,
    summary:    str,
    raw_prompt: str,
) -> str:
    """
    기사 제목 + 태그 + 본문 요약으로 Imagen용 고품질 프롬프트 생성.

    전략:
    1. 태그에서 핵심 주제 감지 → 구체적 시각적 장면 선택
    2. 제목에서 키워드 추출 → 장면에 반영
    3. Imagen 품질 향상 지시어 추가
    """
    # 태그 + 제목 + raw_prompt 합쳐서 키워드 탐색
    all_text = " ".join([
        title.lower(),
        " ".join(t.lower() for t in tags),
        raw_prompt.lower(),
        summary.lower()[:200],
    ])

    # 태그 맵에서 가장 잘 맞는 장면 선택
    scene = ""
    for keyword, scene_desc in TAG_SCENE_MAP.items():
        if keyword in all_text:
            scene = scene_desc
            break

    if not scene:
        scene = TAG_SCENE_MAP["default"]

    # 제목에서 핵심 숫자/% 추출 (예: 1%+, 7.4%, $500B)
    numbers = re.findall(r'\d+\.?\d*%|\$\d+[BMK]?', title)
    number_hint = f" showing {', '.join(numbers[:2])} movement" if numbers else ""

    # 최종 프롬프트 조합
    prompt = (
        f"Professional financial news editorial photograph: {scene}{number_hint}. "
        f"Shot on Canon 5D Mark IV, 35mm lens, f/2.8, natural dramatic lighting. "
        f"Photojournalistic style, sharp focus, rich colors, cinematic composition. "
        f"Wide landscape format 1200x628. No text, no watermarks, no charts. "
        f"High resolution, magazine quality."
    )

    return prompt


# ─────────────────────────────────────────────────────────
# Gemini Imagen 3 생성
# ─────────────────────────────────────────────────────────

def _generate_gemini_imagen(prompt: str, filename: str) -> str | None:
    """Gemini Imagen 3으로 이미지 생성"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Gemini Imagen] GEMINI_API_KEY 없음")
        return None

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{IMAGEN_MODEL}:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            },
            timeout=90,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code != 200:
            print(f"[Gemini Imagen] HTTP {resp.status_code}: {resp.text[:300]}")
            return None

        data  = resp.json()
        parts = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
        )

        for part in parts:
            if "inlineData" not in part:
                continue
            inline   = part["inlineData"]
            mime     = inline.get("mimeType", "image/png")
            b64_data = inline.get("data", "")
            if not b64_data:
                continue

            ext = ".jpg" if "jpeg" in mime or "jpg" in mime else (
                  ".webp" if "webp" in mime else ".png"
            )
            output_path = OUTPUT_DIR / f"{filename}_imagen{ext}"
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(b64_data))

            size_kb = output_path.stat().st_size / 1024
            print(f"[Gemini Imagen] 생성 완료: {size_kb:.0f}KB ({ext})")
            return str(output_path)

        print("[Gemini Imagen] 이미지 파트 없음 (응답은 정상이나 이미지 미포함)")
        return None

    except Exception as e:
        print(f"[Gemini Imagen] 오류: {e}")
        return None


# ─────────────────────────────────────────────────────────
# Unsplash 폴백
# ─────────────────────────────────────────────────────────

def _fetch_unsplash(keywords: list[str], filename: str) -> str | None:
    unsplash_kw = _keywords_to_unsplash(keywords)
    url = UNSPLASH_URL.format(keywords=unsplash_kw)
    try:
        resp = requests.get(
            url, timeout=15, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 BlogBot/1.0"},
            stream=True,
        )
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type:
            return None

        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"

        output_path = OUTPUT_DIR / f"{filename}_unsplash{ext}"
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = output_path.stat().st_size / 1024
        if size_kb < 10:
            output_path.unlink(missing_ok=True)
            return None

        print(f"[Unsplash] {size_kb:.0f}KB")
        return str(output_path)
    except Exception as e:
        print(f"[Unsplash] 오류: {e}")
        return None


def _keywords_to_unsplash(keywords: list[str]) -> str:
    kw_lower = [k.lower() for k in keywords]
    for kw in kw_lower:
        for key, terms in FINANCE_KEYWORD_MAP.items():
            if key in kw or kw in key:
                return terms
    safe_kw = [re.sub(r'[^a-zA-Z0-9]', '-', k) for k in keywords[:3]]
    result  = ",".join(filter(None, safe_kw))
    return result if result else FINANCE_KEYWORD_MAP["default"]


def _extract_keywords(post_data: dict, article: dict) -> list[str]:
    keywords = []
    for tag in post_data.get("tags", [])[:5]:
        kw = tag.strip().lower()
        if kw not in {"market analysis", "investing", "wall street",
                      "stock market", "us stock market"}:
            keywords.append(kw)
    title = post_data.get("title", "") or article.get("title", "")
    if title:
        words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b|\b[A-Z]{2,}\b', title)
        keywords.extend([w.lower() for w in words[:3]])
    seen, result = set(), []
    for k in keywords:
        if k and k not in seen:
            seen.add(k)
            result.append(k)
    return result[:5] or ["finance", "market", "investing"]
