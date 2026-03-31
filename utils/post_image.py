#!/usr/bin/env python3
"""
utils/post_image.py
블로그 포스트용 이미지 조달 — Nano Banana 2 우선

우선순위:
  1. Nano Banana 2 (gemini-3.1-flash-image-preview)
  2. Nano Banana 1 (gemini-2.5-flash-image)
  3. Unsplash
  4. Pillow (최후 폴백)

핵심 개선사항:
  - Nano Banana 2 API 정식 연동
  - 본문 주요 키워드·수치를 이미지 내 텍스트로 삽입
  - 시장 상승/하락 시 분위기(색조·장면) 명시
  - 텔레그램: 원문 기사 이미지를 Nano Banana 2로 각색
"""

import os
import re
import base64
from pathlib import Path
from typing import Optional

import requests

OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

NANO_BANANA_2 = "gemini-3.1-flash-image-preview"
NANO_BANANA_1 = "gemini-2.5-flash-image"

GEMINI_IMG_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)

UNSPLASH_URL = "https://source.unsplash.com/1200x628/?{keywords}"

FINANCE_KEYWORD_MAP = {
    "hang seng":   "hongkong,finance,trading",
    "hsi":         "hongkong,skyline,finance",
    "stock market":"stock,market,trading,finance",
    "wall street": "wall-street,finance,trading",
    "s&p 500":     "stock,market,trading",
    "nasdaq":      "technology,stock,market",
    "fed":         "federal-reserve,economy,money",
    "interest rate":"economy,banking,finance",
    "inflation":   "inflation,economy,money",
    "nvidia":      "technology,semiconductor,chip",
    "apple":       "apple,technology,innovation",
    "tesla":       "tesla,electric,vehicle",
    "oil":         "oil,energy,petroleum",
    "gold":        "gold,precious-metal,finance",
    "crypto":      "cryptocurrency,bitcoin,blockchain",
    "default":     "finance,business,market,economy",
}

_SCENE_MAP: list = [
    (["hang seng","hsi","hong kong","hongkong","china","shanghai"],
     "Hong Kong skyline at dusk with Victoria Harbour and glowing financial district skyscrapers"),
    (["fed","federal reserve","fomc","powell","interest rate","rate hike","rate cut"],
     "The Federal Reserve building in Washington DC, American flags, classical stone architecture, dramatic sky"),
    (["inflation","cpi","pce","consumer price"],
     "Close-up of a shopping cart overflowing with groceries, selective focus, warm store lighting"),
    (["nvidia","semiconductor","chip","ai","artificial intelligence"],
     "Futuristic data center corridor with rows of glowing GPU server racks, blue and purple neon light"),
    (["nasdaq","tech","technology","software","microsoft","amazon","meta"],
     "Silicon Valley modern tech campus at golden hour, glass buildings reflecting warm sky"),
    (["bank","financial","jpmorgan","goldman","morgan stanley","financials"],
     "Glass skyscrapers of Manhattan financial district reflecting golden sunset light, cinematic wide-angle"),
    (["oil","energy","wti","crude","opec","exxon","chevron"],
     "Industrial oil refinery at dusk with glowing flames and dramatic sky, cinematic tone"),
    (["healthcare","pharma","drug","fda","biotech","eli lilly","medical"],
     "Modern hospital corridor, clean white environment, soft diffused light, medical professionals"),
    (["retail","consumer","walmart","costco","spending","sales"],
     "Busy modern shopping street at golden hour, pedestrians, vibrant store fronts"),
    (["housing","real estate","mortgage","home","construction","reit"],
     "Aerial view of suburban neighborhood with green lawns at sunrise, drone photography, warm light"),
    (["gold","treasury","bond","yield","safe haven","dollar","dxy"],
     "Gold bars and coins with soft studio lighting on dark background, macro photography, luxurious style"),
    (["tesla","ev","electric vehicle","autonomous"],
     "Sleek electric vehicle on empty highway at sunrise, automotive photography, dramatic sky"),
    (["crypto","bitcoin","blockchain"],
     "Digital blockchain network visualization, glowing nodes, dark background, futuristic atmosphere"),
    (["tariff","trade war","geopolitical","recession"],
     "World map projected on large screen in modern operations center, cool blue ambient lighting"),
    (["earnings","eps","revenue","quarterly results","profit"],
     "Corporate boardroom with executives around large conference table, professional business photography"),
]

_DEFAULT_SCENE = (
    "Panoramic view of Wall Street with the New York Stock Exchange building, "
    "American flags, golden hour sunlight, dramatic clouds, wide-angle architecture"
)

_DIRECTION_TONE = {
    "strong_up":   "Triumphant atmosphere — vivid green tones, bright optimistic morning sunlight, celebration energy, upward diagonal composition",
    "up":          "Optimistic atmosphere — warm golden tones, bright natural daylight, upward momentum feel",
    "strong_down": "Crisis atmosphere — deep red tones, overcast dramatic sky, tense and urgent mood, downward diagonal composition",
    "down":        "Cautious atmosphere — cool desaturated tones, overcast sky, subdued sombre mood",
    "neutral":     "Balanced atmosphere — soft neutral daylight, calm professional tone",
}


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def get_post_image(
    post_data:   dict,
    article:     dict,
    filename:    str,
    post_type:   str  = "morning",
    market_data: dict = None,
) -> str:
    title        = post_data.get("title", "")  or article.get("title", "")
    tags         = post_data.get("tags",  [])
    content_html = post_data.get("content_html", "")
    summary      = post_data.get("summary_for_blog", "") or article.get("text", "")[:400]

    direction         = _detect_direction(title, content_html, market_data)
    headline_keywords = _extract_headline_keywords(title)

    # 텔레그램: 원문 이미지 각색 시도
    if post_type == "telegram":
        article_image_url = article.get("top_image", "")
        if article_image_url:
            print(f"[이미지] 텔레그램 — 원문 이미지 각색 시도: {article_image_url[:80]}")
            path = _adapt_article_image(
                image_url=article_image_url,
                title=title,
                direction=direction,
                headline_keywords=headline_keywords,
                filename=filename,
            )
            if path:
                print(f"[이미지] 원문 이미지 각색 성공: {path}")
                return path

    # 프롬프트 생성
    prompt = build_nano_banana_prompt(
        title=title,
        tags=tags,
        summary=summary,
        post_type=post_type,
        direction=direction,
        headline_keywords=headline_keywords,
        raw_prompt=post_data.get("thumbnail_prompt", ""),
    )
    print(f"[이미지] Nano Banana 2 시도...")
    print(f"[이미지] 프롬프트: {prompt[:160]}...")

    # 1순위: Nano Banana 2
    path = _generate_nano_banana(prompt, filename, model=NANO_BANANA_2)
    if path:
        print(f"[이미지] Nano Banana 2 성공: {path}")
        return path

    # 2순위: Nano Banana 1
    print("[이미지] Nano Banana 1 폴백...")
    path = _generate_nano_banana(prompt, filename, model=NANO_BANANA_1)
    if path:
        print(f"[이미지] Nano Banana 1 성공: {path}")
        return path

    # 3순위: Unsplash
    keywords = _extract_keywords(post_data, article)
    print(f"[이미지] Unsplash 폴백 (키워드: {keywords})")
    path = _fetch_unsplash(keywords, filename)
    if path:
        return path

    # 4순위: Pillow
    print("[이미지] Pillow 폴백")
    from utils.image_gen import generate_thumbnail
    return generate_thumbnail(
        prompt=prompt,
        filename=filename,
        market_data=market_data,
        title=title,
        tags=tags,
    )


# ─────────────────────────────────────────────────────────
# 프롬프트 빌더
# ─────────────────────────────────────────────────────────

def build_nano_banana_prompt(
    title:             str,
    tags:              list,
    summary:           str,
    post_type:         str  = "morning",
    direction:         str  = "neutral",
    headline_keywords: list = None,
    raw_prompt:        str  = "",
) -> str:
    headline_keywords = headline_keywords or []

    search_text = " ".join([
        title.lower(),
        " ".join(t.lower() for t in tags),
        raw_prompt.lower(),
        summary.lower()[:300],
    ])

    # 장면 선택
    scene = _DEFAULT_SCENE
    for keywords, scene_desc in _SCENE_MAP:
        if any(kw in search_text for kw in keywords):
            scene = scene_desc
            break

    tone = _DIRECTION_TONE.get(direction, _DIRECTION_TONE["neutral"])

    # 이미지 내 텍스트 오버레이 (핵심 수치·키워드)
    text_overlay = ""
    if headline_keywords:
        numeric_kw = [k for k in headline_keywords if re.search(r'\d', k)]
        text_kw    = [k for k in headline_keywords if not re.search(r'\d', k)]
        chosen     = (numeric_kw[:2] + text_kw[:1])[:2]
        if chosen:
            kw_str = " | ".join(chosen)
            text_overlay = (
                f'In the lower-third of the image, place a dark semi-transparent banner '
                f'with bold white text: "{kw_str}". '
                f'The text must be clearly legible, large font, high contrast.'
            )

    type_hint = {
        "morning":   "This is a market close review thumbnail — convey end-of-trading-day energy.",
        "evening":   "This is a pre-market preview thumbnail — convey anticipation of market open, dawn atmosphere.",
        "afternoon": "This is a Hong Kong / Asia market session thumbnail — include Asian financial city atmosphere.",
        "telegram":  "This is a breaking news article thumbnail — convey urgency and timeliness.",
    }.get(post_type, "")

    prompt = (
        f"Professional financial news editorial photograph for a blog thumbnail. "
        f"Scene: {scene}. "
        f"{tone}. "
        f"{type_hint} "
        f"{text_overlay} "
        f"Shot on Canon 5D Mark IV, 35mm lens, f/2.8, natural dramatic lighting. "
        f"Photojournalistic style, sharp focus, rich colors, cinematic composition. "
        f"Wide landscape format 16:9, 1200x628 pixels. "
        f"Magazine quality, high dynamic range, ultra-sharp details."
    )
    return prompt.strip()


# ─────────────────────────────────────────────────────────
# 텔레그램 전용: 원문 이미지 각색
# ─────────────────────────────────────────────────────────

def _adapt_article_image(
    image_url:         str,
    title:             str,
    direction:         str,
    headline_keywords: list,
    filename:          str,
) -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    img_b64, img_mime = _download_image_b64(image_url)
    if not img_b64:
        return None

    kw_str = " | ".join(headline_keywords[:2]) if headline_keywords else title[:60]
    tone   = _DIRECTION_TONE.get(direction, _DIRECTION_TONE["neutral"])

    edit_prompt = (
        f"Edit this financial news image for a blog thumbnail. "
        f"1. Apply {tone} color grading to match the market sentiment. "
        f"2. Add a dark semi-transparent overlay strip at the bottom. "
        f'3. On that strip, place bold white text: "{kw_str}" — must be large and clearly legible. '
        f"4. Keep the main subject of the original image clearly visible. "
        f"5. Output 16:9 landscape, high quality. "
        f"Context: {title[:100]}"
    )

    try:
        resp = requests.post(
            GEMINI_IMG_URL.format(model=NANO_BANANA_2, api_key=api_key),
            json={
                "contents": [{
                    "parts": [
                        {"text": edit_prompt},
                        {"inline_data": {"mime_type": img_mime, "data": img_b64}},
                    ]
                }],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
            },
            headers={"Content-Type": "application/json"},
            timeout=90,
        )
        return _extract_image_from_response(resp, filename, suffix="_adapted")
    except Exception as e:
        print(f"[이미지 각색] 오류: {e}")
        return None


def _download_image_b64(url: str):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 BlogBot/1.0"})
        if resp.status_code != 200:
            return "", ""
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        mime = content_type.split(";")[0].strip()
        if "image" not in mime:
            return "", ""
        return base64.b64encode(resp.content).decode(), mime
    except Exception as e:
        print(f"[이미지 다운로드] 오류: {e}")
        return "", ""


# ─────────────────────────────────────────────────────────
# Nano Banana API
# ─────────────────────────────────────────────────────────

def _generate_nano_banana(prompt: str, filename: str, model: str) -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.post(
            GEMINI_IMG_URL.format(model=model, api_key=api_key),
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
            },
            headers={"Content-Type": "application/json"},
            timeout=90,
        )
        suffix = "_nb2" if "3.1" in model else "_nb1"
        return _extract_image_from_response(resp, filename, suffix=suffix)
    except Exception as e:
        print(f"[{model}] 오류: {e}")
        return None


def _extract_image_from_response(resp, filename: str, suffix: str = "") -> Optional[str]:
    if resp.status_code != 200:
        print(f"[Gemini 이미지] HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    parts = (
        resp.json().get("candidates", [{}])[0]
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
              ".webp" if "webp" in mime else ".png")
        output_path = OUTPUT_DIR / f"{filename}{suffix}{ext}"
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(b64_data))
        size_kb = output_path.stat().st_size / 1024
        print(f"[Gemini 이미지] 저장: {output_path} ({size_kb:.0f}KB)")
        return str(output_path)

    print("[Gemini 이미지] 이미지 파트 없음")
    return None


# ─────────────────────────────────────────────────────────
# 방향 감지 / 키워드 추출
# ─────────────────────────────────────────────────────────

def _detect_direction(title: str, content_html: str, market_data: Optional[dict]) -> str:
    if market_data:
        for key in ("indices", "futures"):
            idx = market_data.get(key, {})
            sp  = (idx.get("S&P 500") or idx.get("S&P 500 Futures") or {}).get("change_pct", 0) or 0
            hsi = (idx.get("Hang Seng (HK)") or {}).get("change_pct", 0) or 0
            chg = sp if sp != 0 else hsi
            if chg > 1.5:  return "strong_up"
            if chg > 0.3:  return "up"
            if chg < -1.5: return "strong_down"
            if chg < -0.3: return "down"

    text = (title + " " + _strip_html(content_html)[:300]).lower()
    sup  = sum(1 for w in ["surge","soar","record high","all-time high","rally","skyrocket"] if w in text)
    sdn  = sum(1 for w in ["crash","plunge","tumble","collapse","sell-off","rout","meltdown"] if w in text)
    up   = sum(1 for w in ["gains","rises","climbs","jumps","bull","higher","positive","advance"] if w in text)
    dn   = sum(1 for w in ["falls","drops","decline","slump","bear","lower","negative","retreat"] if w in text)

    if sup > 0 and sup >= sdn: return "strong_up"
    if sdn > 0 and sdn > sup:  return "strong_down"
    if up + sup > dn + sdn:    return "up"
    if dn + sdn > up + sup:    return "down"
    return "neutral"


def _extract_headline_keywords(title: str) -> list:
    pct_matches    = re.findall(r'[+\-]?\d+\.?\d*%', title)
    dollar_matches = re.findall(r'\$\d+\.?\d*[TBMKtbmk]?', title)
    cap_words      = re.findall(
        r'\b(S&P\s*500|NASDAQ|Hang Seng|HSI|Dow|VIX|KOSPI|Nikkei|NVIDIA|Apple|Tesla|Meta|Amazon|Google|Fed|CPI|GDP|PCE)\b',
        title, re.IGNORECASE
    )
    combined = []
    if pct_matches or dollar_matches:
        index_name = cap_words[0].upper() if cap_words else ""
        pct_str    = pct_matches[0] if pct_matches else dollar_matches[0] if dollar_matches else ""
        if index_name and pct_str:
            combined.append(f"{index_name} {pct_str}")
        elif pct_str:
            combined.append(pct_str)
    if cap_words:
        for w in cap_words[:2]:
            if w.upper() not in " ".join(combined).upper():
                combined.append(w.upper())
    return combined[:3]


def _fetch_unsplash(keywords: list, filename: str) -> Optional[str]:
    unsplash_kw = _keywords_to_unsplash(keywords)
    try:
        resp = requests.get(
            UNSPLASH_URL.format(keywords=unsplash_kw),
            timeout=15, allow_redirects=True, stream=True,
            headers={"User-Agent": "Mozilla/5.0 BlogBot/1.0"},
        )
        if resp.status_code != 200: return None
        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type: return None
        ext = ".jpg"
        if "png"  in content_type: ext = ".png"
        if "webp" in content_type: ext = ".webp"
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


def _keywords_to_unsplash(keywords: list) -> str:
    kw_lower = [k.lower() for k in keywords]
    for kw in kw_lower:
        for key, terms in FINANCE_KEYWORD_MAP.items():
            if key in kw or kw in key:
                return terms
    safe_kw = [re.sub(r'[^a-zA-Z0-9]', '-', k) for k in keywords[:3]]
    result  = ",".join(filter(None, safe_kw))
    return result if result else FINANCE_KEYWORD_MAP["default"]


def _extract_keywords(post_data: dict, article: dict) -> list:
    keywords = []
    for tag in post_data.get("tags", [])[:5]:
        kw = tag.strip().lower()
        if kw not in {"market analysis","investing","wall street","stock market","us stock market"}:
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


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', ' ', html).strip()
