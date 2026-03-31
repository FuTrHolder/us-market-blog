#!/usr/bin/env python3
"""
utils/thumbnail_prompt.py
블로그 글 내용을 분석해 Gemini Imagen용 고품질 이미지 프롬프트를 자동 생성.

전략:
  - 제목·태그·본문 키워드에서 핵심 시각적 주제 추출
  - 시장 방향(상승/하락/혼조)에 따라 분위기(톤) 결정
  - 이미지 생성에 특화된 포토리얼리스틱 프롬프트 구성
  - "NO text/charts" 지시어 포함 → Blogger 썸네일에 최적화
"""

import re
from typing import Optional


# ─────────────────────────────────────────────────────────
# 주제 감지 규칙 (키워드 → 시각적 장면 매핑)
# ─────────────────────────────────────────────────────────

SCENE_RULES: list[tuple[list[str], str]] = [
    # Fed / 금리 정책
    (["fed", "federal reserve", "interest rate", "fomc", "powell", "rate hike", "rate cut"],
     "The Federal Reserve building in Washington DC with American flags, "
     "classical architecture, dramatic natural lighting, professional editorial photography"),

    # 인플레이션 / CPI / PCE
    (["inflation", "cpi", "pce", "consumer price", "core inflation"],
     "Close-up of a shopping cart filled with groceries in a supermarket, "
     "selective focus, warm store lighting, photorealistic editorial style"),

    # 고용 / 실업률 / 노동시장
    (["jobs", "employment", "unemployment", "payroll", "labor market", "hiring", "layoffs"],
     "Busy modern office lobby with professionals walking, soft morning light, "
     "architectural photography, corporate environment, sharp focus"),

    # 기술주 / NASDAQ / 빅테크
    (["nvidia", "tech", "technology", "ai", "semiconductor", "chip", "nasdaq", "software"],
     "Modern data center with rows of glowing server racks in blue and purple light, "
     "long exposure photography, futuristic atmosphere, ultra-sharp detail"),

    # 금융주 / 은행 / 금리
    (["bank", "financial", "jpmorgan", "goldman", "morgan stanley", "financials", "banking"],
     "Glass skyscrapers of the financial district reflecting golden sunset light, "
     "wide angle architecture photography, Manhattan skyline, cinematic composition"),

    # 에너지 / 원유 / 오일
    (["oil", "energy", "wti", "crude", "brent", "opec", "exxon", "chevron"],
     "Industrial oil refinery at dusk with glowing flames and smoke stacks, "
     "dramatic sky, wide angle industrial photography, cinematic tone"),

    # 헬스케어 / 제약
    (["healthcare", "pharma", "drug", "fda", "biotech", "eli lilly", "unitedhealth", "medical"],
     "Modern hospital corridor with soft diffused lighting and medical professionals, "
     "clean minimalist environment, professional documentary photography"),

    # 소비재 / 리테일
    (["retail", "consumer", "walmart", "amazon", "costco", "spending", "sales"],
     "Busy modern shopping street with pedestrians and store fronts at golden hour, "
     "street photography style, shallow depth of field, vibrant colors"),

    # 부동산 / 주택
    (["housing", "real estate", "mortgage", "home sales", "construction", "reit"],
     "Aerial view of a suburban neighborhood with green lawns at sunrise, "
     "drone photography, warm golden light, wide angle landscape"),

    # 금 / 달러 / 안전자산
    (["gold", "dollar", "dxy", "safe haven", "treasury", "bond", "yield"],
     "Gold bars and coins with soft studio lighting on dark background, "
     "macro photography, high contrast, luxurious editorial style"),

    # 시장 급등 / 랠리
    (["surge", "rally", "soar", "gains", "bull", "record high", "all-time high", "climbs"],
     "Packed New York Stock Exchange trading floor with traders celebrating, "
     "dynamic action photography, warm energetic atmosphere, motion blur"),

    # 시장 급락 / 하락
    (["tumble", "fall", "plunge", "drop", "decline", "bear", "sell-off", "crash"],
     "Empty city streets at dawn with fog and reflection puddles, "
     "moody atmospheric photography, cool blue tones, cinematic wide angle"),

    # 실적 발표 / 어닝
    (["earnings", "eps", "revenue", "quarterly results", "profit", "beat", "miss"],
     "Corporate boardroom with executives around a large conference table, "
     "professional business photography, soft natural window light, sharp focus"),

    # 지정학 / 매크로
    (["geopolitical", "war", "tariff", "trade", "china", "global", "macro", "recession"],
     "World map projected on a large screen in a modern operations center, "
     "cool blue ambient lighting, professional documentary photography"),

    # 전기차 / Tesla
    (["tesla", "ev", "electric vehicle", "autonomous"],
     "Sleek electric vehicle on an empty highway at sunrise, "
     "automotive photography, dramatic sky, ultra-sharp detail, cinematic aspect"),
]

# 기본 폴백 — 모든 금융 뉴스에 어울리는 장면
DEFAULT_SCENE = (
    "Panoramic view of Wall Street with the New York Stock Exchange building, "
    "American flags, golden hour sunlight, dramatic clouds, "
    "wide angle architectural photography, cinematic composition"
)

# 공통 품질 지시어 (모든 프롬프트에 추가)
QUALITY_SUFFIX = (
    ". No text, no charts, no graphs, no overlaid graphics. "
    "Photorealistic, editorial photography style. "
    "Landscape orientation 16:9 aspect ratio. "
    "Professional blog thumbnail. High dynamic range. Ultra-sharp."
)


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def build_imagen_prompt(
    post_data: dict,
    market_data: Optional[dict] = None,
    post_type: str = "morning",
) -> str:
    """
    블로그 포스트 데이터에서 Gemini Imagen용 프롬프트를 생성합니다.

    Args:
        post_data:   generate_post()가 반환한 dict
                     (title, tags, content_html, thumbnail_prompt 포함)
        market_data: 시장 데이터 (방향 감지용, optional)
        post_type:   "morning" | "evening" | "telegram"

    Returns:
        Gemini Imagen에 전달할 최종 프롬프트 문자열
    """
    title        = post_data.get("title", "")
    tags         = post_data.get("tags", [])
    thumb_hint   = post_data.get("thumbnail_prompt", "")
    content_html = post_data.get("content_html", "")

    # 1. 검색 텍스트 풀 구성
    search_text = " ".join([
        title.lower(),
        " ".join(t.lower() for t in tags),
        thumb_hint.lower(),
        _strip_html(content_html)[:500].lower(),
    ])

    # 2. 시장 방향 감지
    direction = _detect_direction(title, market_data)

    # 3. 장면 선택
    scene = _match_scene(search_text)

    # 4. 방향 기반 분위기 수정
    scene = _apply_direction_tone(scene, direction)

    # 5. 품질 접미사 추가
    return scene + QUALITY_SUFFIX


def build_gemini_prompt_via_ai(
    post_data: dict,
    market_data: Optional[dict] = None,
) -> str:
    """
    Gemini Flash Lite를 사용해 블로그 내용에서
    Imagen용 프롬프트를 동적으로 생성 (추가 API 호출 1회).

    더 정교한 프롬프트가 필요할 때 사용.
    """
    from utils.gemini_client import generate_post, parse_json_response

    title   = post_data.get("title", "")
    tags    = ", ".join(post_data.get("tags", []))
    snippet = _strip_html(post_data.get("content_html", ""))[:400]

    meta_prompt = f"""You are a professional photo director for a financial news blog.

Blog post title: {title}
Tags: {tags}
Content snippet: {snippet}

Create ONE photorealistic image prompt for a blog thumbnail.

Rules:
- Real-world scene only (NO charts, graphs, text, screens with data)
- Photojournalism / editorial photography style
- 16:9 landscape orientation
- Specific location or object (e.g. "NYSE trading floor", "Federal Reserve building")
- Include lighting description (golden hour, dramatic sky, etc.)
- Maximum 40 words
- End with: "No text overlays. Photorealistic."

Output ONLY the prompt text, nothing else."""

    try:
        raw = generate_post(meta_prompt)
        # 따옴표나 JSON wrapper 제거
        raw = raw.strip().strip('"').strip("'")
        raw = raw.replace("```", "").strip()
        if len(raw) > 20:
            return raw + QUALITY_SUFFIX
    except Exception as e:
        print(f"[thumbnail_prompt] AI 프롬프트 생성 실패, 규칙 기반으로 폴백: {e}")

    return build_imagen_prompt(post_data, market_data)


# ─────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────

def _match_scene(search_text: str) -> str:
    """검색 텍스트와 가장 잘 맞는 시각적 장면 반환."""
    best_scene  = DEFAULT_SCENE
    best_score  = 0

    for keywords, scene in SCENE_RULES:
        score = sum(1 for kw in keywords if kw in search_text)
        if score > best_score:
            best_score = score
            best_scene = scene

    return best_scene


def _detect_direction(title: str, market_data: Optional[dict]) -> str:
    """시장 방향: 'up' | 'down' | 'neutral'"""
    # 실제 데이터 우선
    if market_data and "indices" in market_data:
        sp = (market_data["indices"].get("S&P 500") or {}).get("change_pct", 0) or 0
        if sp > 0.3:
            return "up"
        if sp < -0.3:
            return "down"

    # 제목 키워드
    t = title.lower()
    up_kw   = ["surge", "rally", "gains", "rises", "record", "bull", "soars", "climbs", "jumps", "higher"]
    down_kw = ["tumbles", "falls", "drops", "decline", "slump", "bear", "plunges", "sinks", "lower", "sell"]
    up_cnt  = sum(1 for w in up_kw   if w in t)
    dn_cnt  = sum(1 for w in down_kw if w in t)

    if up_cnt > dn_cnt:
        return "up"
    if dn_cnt > up_cnt:
        return "down"
    return "neutral"


def _apply_direction_tone(scene: str, direction: str) -> str:
    """방향에 따라 장면에 분위기 힌트 추가."""
    tone_map = {
        "up":      ", bright optimistic morning light, warm golden tones",
        "down":    ", overcast dramatic sky, cool desaturated tones",
        "neutral": ", soft natural daylight, balanced neutral tones",
    }
    return scene + tone_map.get(direction, "")


def _strip_html(html: str) -> str:
    """HTML 태그 제거."""
    return re.sub(r'<[^>]+>', ' ', html).strip()
