#!/usr/bin/env python3
"""
utils/image_gen.py
썸네일 생성 — Gemini Imagen 우선, Pillow 폴백

우선순위:
  1. Gemini Imagen 3  — 무료 티어 (gemini-2.0-flash-preview-image-generation)
                         실제 AI 생성 이미지, 블로그 글 내용과 연관성 높음
  2. Pillow 폴백      — Imagen 실패 시 개선된 다크 테마 인포그래픽

출력: 1200x628 WebP (표준 OG 이미지 / 블로그 헤더)

변경 내역 (v2):
  - Gemini Imagen을 1순위로 배치 (기존: 3순위)
  - build_imagen_prompt() 통합 → 글 내용 기반 고품질 프롬프트
  - Pillow 폴백 디자인 개선: 모던 그라디언트 + 다이나믹 레이아웃
  - Unsplash 의존성 제거 (post_image.py에서만 사용)
"""

import base64
import math
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
import io

KST        = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Gemini Imagen 설정 ────────────────────────────────────
# gemini-2.0-flash-preview-image-generation: 무료 티어에서 이미지 생성 지원
IMAGEN_MODEL   = "gemini-2.0-flash-preview-image-generation"
IMAGEN_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{IMAGEN_MODEL}:generateContent"
)

# ── Pillow 색상 팔레트 ────────────────────────────────────
C_BG      = "#070d1a"   # 거의 블랙에 가까운 네이비
C_CARD    = "#0f1e38"   # 카드 배경
C_BORDER  = "#1e3a6e"   # 카드 테두리
C_GOLD    = "#F5C518"   # 황금색 (IMDb 느낌)
C_CYAN    = "#00D4FF"   # 밝은 시안
C_GREEN   = "#00E676"   # 머티리얼 그린
C_RED     = "#FF5252"   # 머티리얼 레드
C_WHITE   = "#F0F4FF"   # 따뜻한 화이트
C_MUTED   = "#6B80A0"   # 흐린 파랑
C_ACCENT  = "#2979FF"   # 브랜드 블루


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def generate_thumbnail(
    prompt: str,
    filename: str,
    market_data: Optional[dict] = None,
    post_data: Optional[dict] = None,
    post_type: str = "morning",
) -> str:
    """
    썸네일을 생성하고 저장된 WebP 경로를 반환합니다.

    우선순위:
      1. Gemini Imagen  (GEMINI_API_KEY 필요, 무료 티어)
      2. Pillow 인포그래픽 (항상 성공)

    Args:
        prompt:      기존 단순 설명 프롬프트 (폴백 방향 결정에 사용)
        filename:    저장 파일명 베이스 (확장자 제외)
        market_data: 시장 데이터 dict (방향·수치 표시용)
        post_data:   블로그 포스트 dict (title, tags, content_html)
        post_type:   "morning" | "evening" | "telegram"

    Returns:
        저장된 WebP 파일의 절대 경로 문자열
    """
    # ── 1순위: Gemini Imagen ──────────────────────────────
    imagen_prompt = _build_best_prompt(prompt, post_data, market_data, post_type)
    path = _generate_via_gemini_imagen(imagen_prompt, filename)
    if path:
        print(f"✅ [Gemini Imagen] 썸네일 생성 완료: {path}")
        return path

    # ── 2순위: 개선된 Pillow 인포그래픽 ──────────────────
    print("⚠️  Gemini Imagen 실패 → Pillow 폴백으로 전환")
    return _generate_pillow_fallback(prompt, filename, market_data, post_data, post_type)


# ─────────────────────────────────────────────────────────
# 1순위: Gemini Imagen
# ─────────────────────────────────────────────────────────

def _build_best_prompt(
    raw_prompt: str,
    post_data: Optional[dict],
    market_data: Optional[dict],
    post_type: str,
) -> str:
    """
    가장 품질 높은 Imagen 프롬프트를 결정.
    post_data가 있으면 thumbnail_prompt.py의 규칙 기반 프롬프트,
    없으면 raw_prompt를 보강해서 사용.
    """
    if post_data:
        try:
            from utils.thumbnail_prompt import build_imagen_prompt
            return build_imagen_prompt(post_data, market_data, post_type)
        except Exception as e:
            print(f"[thumbnail_prompt] 프롬프트 빌드 실패: {e}")

    # raw_prompt 보강
    base = (raw_prompt or "Wall Street financial district").strip().rstrip(".")
    return (
        f"{base}. "
        "Photorealistic editorial photography. "
        "Professional financial blog thumbnail. "
        "No text, no charts, no graphs. "
        "16:9 landscape orientation. "
        "Dramatic lighting. Ultra-sharp detail."
    )


def _generate_via_gemini_imagen(prompt: str, filename: str) -> Optional[str]:
    """
    Gemini 2.0 Flash (이미지 생성) API 호출.
    무료 티어에서 사용 가능한 gemini-2.0-flash-preview-image-generation 모델 사용.

    성공 시 저장 경로, 실패 시 None 반환.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Gemini Imagen] GEMINI_API_KEY 없음, 건너뜀")
        return None

    print(f"[Gemini Imagen] 프롬프트: {prompt[:120]}...")

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
        },
    }

    for attempt in range(2):
        try:
            resp = requests.post(
                f"{IMAGEN_API_URL}?key={api_key}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=90,
            )

            if resp.status_code == 429:
                wait = 30 if attempt == 0 else 0
                if wait:
                    print(f"[Gemini Imagen] Rate limit — {wait}초 대기 후 재시도...")
                    time.sleep(wait)
                    continue
                return None

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
                inline = part.get("inlineData", {})
                if not inline:
                    continue
                mime     = inline.get("mimeType", "image/png")
                b64_data = inline.get("data", "")
                if not b64_data:
                    continue

                # PNG/JPEG → WebP 변환 (파일 크기 절감)
                raw_bytes  = base64.b64decode(b64_data)
                img        = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

                # 1200×628 으로 리사이즈 (비율 유지 + 크롭)
                img = _resize_crop(img, 1200, 628)

                out_path = OUTPUT_DIR / f"{filename}_imagen.webp"
                img.save(out_path, format="WEBP", quality=85, method=4, lossless=False)

                size_kb = out_path.stat().st_size / 1024
                print(f"[Gemini Imagen] 저장: {out_path}  ({size_kb:.0f}KB)")
                return str(out_path)

            print("[Gemini Imagen] 이미지 파트 없음 (안전 필터 등)")
            return None

        except requests.Timeout:
            print(f"[Gemini Imagen] 타임아웃 (시도 {attempt+1}/2)")
        except Exception as e:
            print(f"[Gemini Imagen] 오류: {e}")
            return None

    return None


def _resize_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """비율 유지 후 중앙 크롭으로 정확히 w×h 출력."""
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img   = img.resize((new_w, new_h), Image.LANCZOS)
    left  = (new_w - w) // 2
    top   = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


# ─────────────────────────────────────────────────────────
# 2순위: 개선된 Pillow 인포그래픽 폴백
# ─────────────────────────────────────────────────────────

def _generate_pillow_fallback(
    prompt: str,
    filename: str,
    market_data: Optional[dict],
    post_data: Optional[dict],
    post_type: str,
) -> str:
    """
    개선된 Pillow 기반 인포그래픽 썸네일.
    - 다크 그라디언트 배경
    - 실제 시장 데이터 수치 표시
    - 방향에 따른 동적 색상 테마
    - 볼드한 타이포그래피 레이아웃
    """
    direction, accent = _infer_direction(prompt, market_data)
    title_text = ""
    if post_data:
        title_text = post_data.get("title", "")[:80]

    fig = _build_improved_figure(
        filename, direction, accent, market_data, title_text, post_type
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf).convert("RGB")
    out_path = OUTPUT_DIR / f"{filename}.webp"
    img.save(out_path, format="WEBP", quality=85, method=4, lossless=False)

    size_kb = out_path.stat().st_size / 1024
    print(f"✅ [Pillow] 썸네일 저장: {out_path}  ({size_kb:.0f}KB)")
    return str(out_path)


def _infer_direction(prompt: str, market_data: Optional[dict]):
    if market_data and "indices" in market_data:
        chg = (market_data["indices"].get("S&P 500") or {}).get("change_pct", 0) or 0
        if chg > 0.3:
            return "up", C_GREEN
        if chg < -0.3:
            return "down", C_RED
    p = (prompt or "").lower()
    up_kw   = ["surge", "rally", "gains", "rises", "record", "bull", "soars", "climbs", "jumps"]
    down_kw = ["tumbles", "falls", "drops", "decline", "slump", "bear", "plunges", "sinks"]
    if sum(1 for w in up_kw if w in p) > sum(1 for w in down_kw if w in p):
        return "up", C_GREEN
    if sum(1 for w in down_kw if w in p) > sum(1 for w in up_kw if w in p):
        return "down", C_RED
    return "neutral", C_CYAN


def _build_improved_figure(filename, direction, accent, market_data, title_text, post_type):
    """개선된 Pillow 인포그래픽: 3-컬럼 레이아웃 + 그라디언트 배경."""
    fig = plt.figure(figsize=(12, 6.28), facecolor=C_BG)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 628)
    ax.axis("off")

    _draw_gradient_bg(ax, accent)
    _draw_accent_lines(ax, accent)
    _draw_header_band(ax, post_type, direction)
    _draw_chart_area(ax, direction, accent)
    _draw_index_panel(ax, market_data, accent)
    _draw_title_area(ax, title_text, accent)
    _draw_footer(ax)

    return fig


def _draw_gradient_bg(ax, accent):
    """미묘한 사이드 그라디언트 배경."""
    # 왼쪽 글로우 힌트
    glow = LinearSegmentedColormap.from_list("glow", ["#070d1a", "#0a1525", "#070d1a"])
    gradient = np.linspace(0, 1, 200).reshape(1, -1)
    ax.imshow(gradient, aspect="auto", extent=[0, 1200, 0, 628],
              cmap=glow, alpha=0.6, zorder=0)

    # 그리드 라인 (매우 미묘하게)
    for x in range(0, 1201, 100):
        ax.plot([x, x], [0, 628], color="#1a2d50", lw=0.5, alpha=0.3, zorder=1)
    for y in range(0, 629, 80):
        ax.plot([0, 1200], [y, y], color="#1a2d50", lw=0.5, alpha=0.3, zorder=1)


def _draw_accent_lines(ax, accent):
    """왼쪽 + 하단 액센트 선."""
    # 왼쪽 수직 강조선
    ax.add_patch(patches.FancyArrow(
        4, 0, 0, 628, width=8, head_width=0, head_length=0,
        color=accent, alpha=0.9, zorder=3
    ))
    # 하단 바
    ax.add_patch(patches.Rectangle((0, 0), 1200, 12, color=accent, alpha=0.85, zorder=3))
    # 상단 바 (얇게)
    ax.add_patch(patches.Rectangle((0, 616), 1200, 12, color="#0f1e38", alpha=1, zorder=3))


def _draw_header_band(ax, post_type, direction):
    """상단 헤더 밴드 — 포스트 타입 + 방향."""
    label = "MARKET CLOSE REVIEW" if post_type == "morning" else (
            "PRE-MARKET PREVIEW"  if post_type == "evening" else "MARKET ANALYSIS")
    dir_map = {"up": "▲ MARKET GAINS", "down": "▼ MARKET LOSS", "neutral": "◆ MIXED SESSION"}
    dir_label = dir_map[direction]
    dir_color = C_GREEN if direction == "up" else (C_RED if direction == "down" else C_CYAN)

    date_str = datetime.now(KST).strftime("%B %d, %Y")

    # 포스트 타입 태그
    ax.add_patch(patches.FancyBboxPatch(
        (20, 580), 260, 28,
        boxstyle="round,pad=3", linewidth=0,
        facecolor="#0f1e38", zorder=4
    ))
    ax.text(150, 596, label, ha="center", va="center",
            fontsize=9, color=C_GOLD, fontweight="bold",
            fontfamily="monospace", zorder=5)

    # 날짜
    ax.text(1180, 596, date_str, ha="right", va="center",
            fontsize=9, color=C_MUTED, zorder=5)

    # 방향 레이블 (하단 왼쪽)
    ax.text(20, 38, dir_label, ha="left", va="center",
            fontsize=11, color=dir_color, fontweight="bold", zorder=5)

    # 브랜드
    ax.text(1180, 38, "Wall Street Daily Briefing", ha="right", va="center",
            fontsize=8, color=C_MUTED, alpha=0.7, zorder=5)


def _draw_chart_area(ax, direction, accent):
    """왼쪽 패널: 개선된 미니 차트."""
    np.random.seed(42)
    n = 60

    if direction == "up":
        trend = np.linspace(-1, 2.5, n)
    elif direction == "down":
        trend = np.linspace(1, -2.5, n)
    else:
        trend = np.sin(np.linspace(0, 2 * math.pi, n)) * 0.9

    noise  = np.cumsum(np.random.normal(0, 0.15, n))
    raw    = trend + noise * 0.3
    lo, hi = raw.min(), raw.max()
    prices = (raw - lo) / max(hi - lo, 1e-9) * 0.55 + 0.20

    chart_x0, chart_x1 = 20, 480
    chart_y0, chart_y1 = 60, 560
    cw = chart_x1 - chart_x0
    ch = chart_y1 - chart_y0

    xs = chart_x0 + np.linspace(0, cw, n)
    ys = chart_y0 + prices * ch

    # Fill under curve
    poly_x = np.concatenate([[xs[0]], xs, [xs[-1]]])
    poly_y = np.concatenate([[chart_y0], ys, [chart_y0]])
    ax.fill(poly_x, poly_y, color=accent, alpha=0.08, zorder=2)

    # 글로우 효과 (두꺼운 반투명 선)
    ax.plot(xs, ys, color=accent, lw=10, alpha=0.06, zorder=2)
    ax.plot(xs, ys, color=accent, lw=5,  alpha=0.12, zorder=2)
    # 실제 선
    ax.plot(xs, ys, color=accent, lw=2.5, zorder=3, solid_capstyle="round")

    # 이동평균
    w = 10
    ma = np.convolve(ys, np.ones(w) / w, mode="valid")
    ax.plot(xs[w-1:], ma, color=C_WHITE, lw=1, alpha=0.25, linestyle="--", zorder=3)

    # 마지막 포인트
    ax.scatter([xs[-1]], [ys[-1]], color=accent, s=80, zorder=5, edgecolors=C_BG, linewidths=2)

    # 볼륨 바 (하단)
    vol_h = 35
    vols  = np.abs(np.random.normal(0.5, 0.2, n)).clip(0.1, 1.0)
    for i in range(n):
        bar_color = C_GREEN if (i == 0 or prices[i] >= prices[i-1]) else C_RED
        bw = cw / n * 0.65
        bh = vols[i] * vol_h
        ax.add_patch(patches.Rectangle(
            (xs[i] - bw/2, chart_y0),
            bw, bh,
            color=bar_color, alpha=0.35, zorder=2, linewidth=0
        ))

    # 차트 테두리 라인
    ax.plot([chart_x0, chart_x0], [chart_y0, chart_y1], color=C_BORDER, lw=1, alpha=0.5, zorder=2)
    ax.plot([chart_x0, chart_x1], [chart_y0, chart_y0], color=C_BORDER, lw=1, alpha=0.5, zorder=2)


def _draw_index_panel(ax, market_data, accent):
    """오른쪽 패널: 지수 데이터 카드."""
    indices_cfg = [
        ("S&P 500",   "SPX",  500, 500),
        ("NASDAQ",    "NDX",  500, 370),
        ("Dow Jones", "DJI",  500, 240),
        ("VIX",       "VIX",  500, 110),
    ]

    card_w, card_h = 320, 100
    card_x0 = 850

    for name, abbr, _, card_y0 in indices_cfg:
        # 카드 배경
        ax.add_patch(patches.FancyBboxPatch(
            (card_x0, card_y0), card_w, card_h,
            boxstyle="round,pad=5",
            facecolor=C_CARD,
            edgecolor=C_BORDER,
            linewidth=0.8,
            zorder=3,
        ))

        val_str = "—"
        chg_str = ""
        chg_clr = C_WHITE

        if market_data and "indices" in market_data:
            d = market_data["indices"].get(name) or {}
            close   = d.get("close")
            chg_pct = d.get("change_pct")
            if close is not None:
                val_str = f"{close:,.2f}"
            if chg_pct is not None:
                sign    = "+" if chg_pct >= 0 else ""
                chg_str = f"{sign}{chg_pct:.2f}%"
                chg_clr = C_GREEN if chg_pct >= 0 else C_RED

                # 미니 방향 바
                bar_color = C_GREEN if chg_pct >= 0 else C_RED
                bar_len   = min(abs(chg_pct) * 20, card_w - 20)
                ax.add_patch(patches.Rectangle(
                    (card_x0 + 10, card_y0 + 8), bar_len, 3,
                    color=bar_color, alpha=0.6, zorder=4, linewidth=0
                ))

        # Abbr
        ax.text(card_x0 + 15, card_y0 + 80, abbr,
                fontsize=9, color=C_MUTED, fontweight="bold",
                fontfamily="monospace", zorder=4, va="center")
        # Full name
        ax.text(card_x0 + card_w - 15, card_y0 + 80, name,
                fontsize=8, color=C_MUTED, alpha=0.6,
                ha="right", va="center", zorder=4)
        # Value
        ax.text(card_x0 + 15, card_y0 + 48, val_str,
                fontsize=18, color=C_WHITE, fontweight="bold",
                zorder=4, va="center")
        # Change
        if chg_str:
            ax.text(card_x0 + card_w - 15, card_y0 + 48, chg_str,
                    fontsize=14, color=chg_clr, fontweight="bold",
                    ha="right", va="center", zorder=4)


def _draw_title_area(ax, title_text, accent):
    """중앙 패널: 포스트 제목 (있는 경우)."""
    if not title_text:
        return

    # 구분선
    ax.plot([495, 835], [400, 400], color=C_BORDER, lw=1, alpha=0.5, zorder=3)

    # 제목 (긴 경우 두 줄로)
    words  = title_text.split()
    line1, line2 = "", ""
    for i, word in enumerate(words):
        if len(line1 + " " + word) <= 38:
            line1 = (line1 + " " + word).strip()
        else:
            line2 = " ".join(words[i:])
            break

    # 라인1 — 큰 폰트
    ax.text(665, 490, line1, ha="center", va="center",
            fontsize=13.5, color=C_WHITE, fontweight="bold",
            zorder=4, wrap=True)

    # 라인2 — 약간 작게
    if line2:
        display_line2 = line2[:50] + ("…" if len(line2) > 50 else "")
        ax.text(665, 452, display_line2, ha="center", va="center",
                fontsize=11, color="#b0c0d8",
                zorder=4)

    # 액센트 밑줄
    ax.plot([530, 800], [430, 430], color=accent, lw=2, alpha=0.7, zorder=4)

    # 중간 구분선 (좌우 패널 경계)
    ax.plot([490, 490], [60, 570], color=C_BORDER, lw=1, alpha=0.4, zorder=3)
    ax.plot([840, 840], [60, 570], color=C_BORDER, lw=1, alpha=0.4, zorder=3)

    # 하단 설명 텍스트 (post_type 구분 없이 공통)
    ax.text(665, 120, "fund-up.blogspot.com",
            ha="center", va="center",
            fontsize=8.5, color=C_MUTED, alpha=0.5, zorder=4)


def _draw_footer(ax):
    """하단 면책 텍스트."""
    ax.text(600, 24, "For informational purposes only — Not financial advice",
            ha="center", va="center",
            fontsize=7.5, color=C_MUTED, alpha=0.6, zorder=5)


# ─────────────────────────────────────────────────────────
# Helper: Base64 변환 (Blogger 임베드용)
# ─────────────────────────────────────────────────────────

def thumbnail_to_base64(path: str) -> str:
    """WebP/PNG/JPEG → base64 data URI."""
    suffix = Path(path).suffix.lower()
    mime   = {"webp": "image/webp", "png": "image/png",
               "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix[1:], "image/png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"
