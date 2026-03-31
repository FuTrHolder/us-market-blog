#!/usr/bin/env python3
"""
utils/image_gen.py
썸네일 생성기 — 100% FREE (No OpenAI / No paid API)

두 가지 모드:
  1. generate_thumbnail()     — 기사 제목 기반 텍스트 오버레이 썸네일 (telegram용)
  2. generate_chart_thumbnail() — 시장 데이터 차트 썸네일 (morning/evening 자동 포스팅용)

Output: 1200x628px WebP
"""

import base64
import math
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io

KST        = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Color palette ────────────────────────────────────────
DARK_BG  = "#0a0f1e"
NAVY     = "#1a2744"
NAVY2    = "#0d1a35"
GOLD     = "#FFD700"
CYAN     = "#00BFFF"
GREEN    = "#00C853"
RED      = "#FF3D3D"
WHITE    = "#FFFFFF"
GRAY     = "#8899aa"
ACCENT   = "#3a7bd5"


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def generate_thumbnail(
    prompt: str,
    filename: str,
    market_data: dict = None,
    title: str = "",
    tags: list = None,
) -> str:
    """
    기사 제목 기반 텍스트 오버레이 썸네일 생성 (telegram 포스트용).
    market_data 가 충분히 있으면 지수값도 함께 표시.

    Args:
        prompt:      Gemini가 생성한 thumbnail_prompt (분위기/방향 파악용)
        filename:    저장 파일명 (확장자 제외)
        market_data: 시장 데이터 dict (없으면 None)
        title:       블로그 포스트 제목 (썸네일 메인 텍스트로 사용)
        tags:        태그 리스트 (카테고리 뱃지로 표시)

    Returns:
        저장된 WebP 파일 경로
    """
    direction, accent = _infer_direction(prompt, market_data)
    tags = tags or []

    fig = _build_article_thumbnail(
        title=title or _title_from_prompt(prompt),
        direction=direction,
        accent=accent,
        market_data=market_data,
        tags=tags,
        filename=filename,
    )

    return _save_webp(fig, filename)


def generate_chart_thumbnail(
    prompt: str,
    filename: str,
    market_data: dict = None,
) -> str:
    """
    시장 차트 기반 썸네일 (morning/evening 자동 포스팅용).
    기존 로직 유지.
    """
    direction, accent = _infer_direction(prompt, market_data)
    fig = _build_chart_figure(filename, direction, accent, market_data)
    return _save_webp(fig, filename)


# ─────────────────────────────────────────────────────────
# 기사 제목 기반 썸네일 (신규)
# ─────────────────────────────────────────────────────────

def _build_article_thumbnail(
    title: str,
    direction: str,
    accent: str,
    market_data: dict,
    tags: list,
    filename: str,
) -> plt.Figure:
    """
    기사 제목을 큼직하게 보여주는 뉴스카드형 썸네일.
    레이아웃:
      - 상단: 카테고리 뱃지 + 날짜
      - 중앙: 제목 텍스트 (2~3줄)
      - 하단: 방향 인디케이터 + 브랜드
      - 우측 세로선 + 악센트 컬러 포인트
    """
    W, H = 12, 6.28  # 1200x628 비율
    fig = plt.figure(figsize=(W, H), facecolor=DARK_BG)

    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(DARK_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ── 배경 그라데이션 효과 (좌→우 오버레이) ───────────
    grad = np.linspace(0, 1, 100).reshape(1, -1)
    ax.imshow(
        grad, aspect="auto", extent=[0, 1, 0, 1],
        cmap=plt.cm.colors.LinearSegmentedColormap.from_list(
            "bg", [NAVY2, DARK_BG]
        ),
        alpha=0.6, zorder=1,
    )

    # ── 좌측 악센트 바 ───────────────────────────────────
    ax.add_patch(plt.Rectangle((0, 0), 0.006, 1,
                               facecolor=accent, zorder=3))

    # ── 대각선 장식선 ────────────────────────────────────
    for i, alpha in enumerate([0.04, 0.025, 0.015]):
        offset = 0.18 * (i + 1)
        ax.plot([offset, offset + 0.6], [1.1, -0.1],
                color=accent, alpha=alpha, lw=60, zorder=2)

    # ── 미세 그리드 ──────────────────────────────────────
    for y in np.linspace(0.1, 0.9, 5):
        ax.axhline(y, color="#1e3060", lw=0.3, alpha=0.4, zorder=2)

    # ── 날짜 + 브랜드 (상단) ─────────────────────────────
    date_str = datetime.now(KST).strftime("%B %d, %Y")
    ax.text(0.05, 0.91, "WALL STREET DAILY BRIEFING",
            color=GOLD, fontsize=9, fontweight="bold",
            va="center", transform=ax.transAxes, zorder=5)
    ax.text(0.95, 0.91, date_str,
            color=GRAY, fontsize=8,
            va="center", ha="right", transform=ax.transAxes, zorder=5)

    # ── 구분선 ───────────────────────────────────────────
    ax.axhline(0.84, xmin=0.04, xmax=0.96,
               color=accent, lw=0.6, alpha=0.5, zorder=4)

    # ── 카테고리 뱃지 ────────────────────────────────────
    badge_x = 0.05
    for tag in tags[:3]:
        short = tag[:18]
        bbox = dict(boxstyle="round,pad=0.3", facecolor=NAVY,
                    edgecolor=accent, linewidth=0.8, alpha=0.9)
        t = ax.text(badge_x, 0.76, short,
                    color=accent, fontsize=7.5, fontweight="bold",
                    va="center", transform=ax.transAxes,
                    bbox=bbox, zorder=5)
        badge_x += len(short) * 0.012 + 0.04

    # ── 메인 제목 (핵심) ─────────────────────────────────
    title_clean = title.strip()
    # 제목 길이에 따라 폰트 크기 자동 조절
    if len(title_clean) <= 50:
        fsize, wrap_w = 22, 42
    elif len(title_clean) <= 80:
        fsize, wrap_w = 18, 52
    else:
        fsize, wrap_w = 15, 62

    wrapped = "\n".join(textwrap.wrap(title_clean, width=wrap_w))
    lines   = wrapped.count("\n") + 1
    title_y = 0.57 if lines == 1 else (0.61 if lines == 2 else 0.65)

    ax.text(0.05, title_y, wrapped,
            color=WHITE, fontsize=fsize, fontweight="bold",
            va="center", transform=ax.transAxes,
            linespacing=1.4, zorder=5,
            wrap=False)

    # ── 방향 인디케이터 ──────────────────────────────────
    dir_map = {
        "up":      (f"▲  MARKET BULLISH", GREEN),
        "down":    (f"▼  MARKET BEARISH", RED),
        "neutral": (f"◆  MARKET WATCH",   CYAN),
    }
    dir_text, dir_color = dir_map.get(direction, dir_map["neutral"])
    ax.text(0.05, 0.22, dir_text,
            color=dir_color, fontsize=11, fontweight="bold",
            va="center", transform=ax.transAxes, zorder=5)

    # ── 지수값 (market_data 있을 때) ─────────────────────
    if market_data and "indices" in market_data:
        _draw_index_pills(ax, market_data["indices"])

    # ── 하단 구분선 + 브랜드 ─────────────────────────────
    ax.axhline(0.14, xmin=0.04, xmax=0.96,
               color=accent, lw=0.6, alpha=0.4, zorder=4)
    ax.text(0.95, 0.07, "fund-up.blogspot.com",
            color=GRAY, fontsize=7, alpha=0.6,
            ha="right", va="center", transform=ax.transAxes, zorder=5)

    # ── 하단 악센트 바 ───────────────────────────────────
    ax.add_patch(plt.Rectangle((0, 0), 1, 0.025,
                               facecolor=accent, alpha=0.8, zorder=3))

    return fig


def _draw_index_pills(ax, indices: dict):
    """시장 지수값을 하단에 pill 형태로 표시"""
    targets = [
        ("S&P 500",   "SPX"),
        ("NASDAQ",    "NDX"),
        ("Dow Jones", "DJI"),
        ("VIX",       "VIX"),
    ]
    x = 0.05
    for name, abbr in targets:
        d = indices.get(name) or {}
        close   = d.get("close")
        chg_pct = d.get("change_pct")
        if close is None:
            continue

        sign     = "+" if (chg_pct or 0) >= 0 else ""
        clr      = GREEN if (chg_pct or 0) >= 0 else RED
        chg_str  = f" {sign}{chg_pct:.2f}%" if chg_pct is not None else ""
        val_str  = f"{abbr}  {close:,.0f}{chg_str}"

        bbox = dict(boxstyle="round,pad=0.35", facecolor=NAVY,
                    edgecolor=clr, linewidth=0.7, alpha=0.85)
        ax.text(x, 0.08, val_str,
                color=WHITE, fontsize=7.5,
                va="center", transform=ax.transAxes,
                bbox=bbox, zorder=5)
        x += len(val_str) * 0.011 + 0.04
        if x > 0.85:
            break


# ─────────────────────────────────────────────────────────
# 차트 기반 썸네일 (기존 — morning/evening용)
# ─────────────────────────────────────────────────────────

def _build_chart_figure(filename, direction, accent, market_data):
    fig = plt.figure(figsize=(12, 6.28), facecolor=DARK_BG)

    ax_bg = fig.add_axes([0, 0, 1, 1])
    ax_bg.set_facecolor(DARK_BG)
    ax_bg.axis("off")

    for y in np.linspace(0.08, 0.92, 7):
        ax_bg.axhline(y, color="#1e3060", lw=0.4, alpha=0.45)
    for x in np.linspace(0.04, 0.96, 12):
        ax_bg.axvline(x, color="#1e3060", lw=0.4, alpha=0.45)

    ax_chart = fig.add_axes([0.03, 0.10, 0.44, 0.78])
    ax_chart.set_facecolor("none")
    ax_chart.axis("off")
    _draw_chart(ax_chart, direction, accent)

    ax_bg.axvline(0.50, color=accent, lw=0.8, alpha=0.35)
    _draw_right_panel(ax_bg, filename, direction, accent, market_data)

    ax_badge = fig.add_axes([0.02, 0.90, 0.22, 0.075])
    ax_badge.set_facecolor(NAVY)
    ax_badge.text(0.5, 0.5, "Wall Street Daily Briefing",
                  ha="center", va="center", fontsize=7.5,
                  color=GOLD, fontweight="bold", transform=ax_badge.transAxes)
    ax_badge.axis("off")

    ax_bar = fig.add_axes([0, 0, 1, 0.022])
    ax_bar.set_facecolor(accent)
    ax_bar.axis("off")

    return fig


def _draw_chart(ax, direction, accent):
    np.random.seed(7)
    n = 65

    if direction == "up":
        trend = np.linspace(0, 2.2, n)
    elif direction == "down":
        trend = np.linspace(0, -2.2, n)
    else:
        trend = np.sin(np.linspace(0, math.pi * 1.5, n)) * 0.7

    noise  = np.random.normal(0, 0.18, n).cumsum() * 0.28
    raw    = 100 + trend * 14 + noise
    lo, hi = raw.min(), raw.max()
    prices = (raw - lo) / max(hi - lo, 1e-9) * 0.72 + 0.14
    x      = np.linspace(0, 1, n)

    ax.fill_between(x, 0.05, prices, color=accent, alpha=0.10)
    ax.plot(x, prices, color=accent, lw=8, alpha=0.07)
    ax.plot(x, prices, color=accent, lw=2.5, solid_capstyle="round")

    w  = 12
    ma = np.convolve(prices, np.ones(w) / w, mode="valid")
    ax.plot(x[w-1:], ma, color=WHITE, lw=1.0, alpha=0.35, linestyle="--")
    ax.scatter([x[-1]], [prices[-1]], color=accent, s=90, zorder=6)

    vols  = np.abs(np.random.normal(0.5, 0.18, n)).clip(0.08, 1.0)
    bar_w = 0.011
    for i in range(n):
        clr = GREEN if (i == 0 or prices[i] >= prices[i-1]) else RED
        ax.bar(x[i], vols[i] * 0.075, width=bar_w, bottom=0.02,
               color=clr, alpha=0.45, linewidth=0)

    ax.set_xlim(-0.02, 1.03)
    ax.set_ylim(0, 1.08)


def _draw_right_panel(ax, filename, direction, accent, market_data):
    is_morning = "morning" in filename
    date_str   = datetime.now(KST).strftime("%B %d, %Y")
    post_label = "MARKET CLOSE REVIEW" if is_morning else "PRE-MARKET PREVIEW"
    dir_badge  = {
        "up":      "▲ MARKET GAINS",
        "down":    "▼ MARKET LOSS",
        "neutral": "◆ MIXED SESSION",
    }[direction]

    kw = dict(transform=ax.transAxes, va="center")
    ax.text(0.535, 0.90, post_label,   fontsize=8.5,  color=GOLD,   fontweight="bold", **kw)
    ax.text(0.535, 0.81, date_str,     fontsize=10,   color=GRAY,   **kw)
    ax.text(0.535, 0.71, dir_badge,    fontsize=13.5, color=accent, fontweight="bold", **kw)
    ax.axhline(0.645, xmin=0.525, xmax=0.975, color=accent, lw=0.7, alpha=0.55)
    _draw_index_rows(ax, market_data, is_morning)
    ax.text(0.97, 0.035, "fund-up.blogspot.com",
            fontsize=6.5, color=GRAY, alpha=0.45, ha="right",
            transform=ax.transAxes, va="center")


def _draw_index_rows(ax, market_data, is_morning):
    rows = [
        ("S&P 500",   "SPX", 0.575),
        ("NASDAQ",    "NDX", 0.475),
        ("Dow Jones", "DJI", 0.375),
        ("VIX",       "VIX", 0.275),
    ]
    kw = dict(transform=ax.transAxes, va="center")

    for name, abbr, y in rows:
        val_str = "—"
        chg_str = ""
        chg_clr = WHITE

        if market_data and "indices" in market_data:
            d       = market_data["indices"].get(name) or {}
            close   = d.get("close")
            chg_pct = d.get("change_pct")
            if close is not None:
                val_str = f"{close:,.2f}"
            if chg_pct is not None:
                sign    = "+" if chg_pct >= 0 else ""
                chg_str = f"  {sign}{chg_pct:.2f}%"
                chg_clr = GREEN if chg_pct >= 0 else RED

        ax.text(0.535, y + 0.038, abbr,    fontsize=7.5,  color=GRAY,   fontweight="bold", **kw)
        ax.text(0.535, y - 0.005, val_str, fontsize=11.5, color=WHITE,  fontweight="bold", **kw)
        ax.text(0.700, y - 0.005, chg_str, fontsize=10.5, color=chg_clr, **kw)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _infer_direction(prompt: str, market_data: dict):
    if market_data and "indices" in market_data:
        chg = (market_data["indices"].get("S&P 500") or {}).get("change_pct", 0) or 0
        if chg > 0.3:
            return "up", GREEN
        if chg < -0.3:
            return "down", RED

    p      = (prompt or "").lower()
    up_kw  = ["surge", "rally", "gains", "rises", "record", "bull", "soars",
               "climbs", "jumps", "bullish", "crash fears", "could rally"]
    dn_kw  = ["tumbles", "falls", "drops", "decline", "slump", "bear",
               "plunges", "sinks", "bearish", "crash", "recession"]
    up_cnt = sum(1 for w in up_kw if w in p)
    dn_cnt = sum(1 for w in dn_kw if w in p)

    if up_cnt > dn_cnt:
        return "up", GREEN
    if dn_cnt > up_cnt:
        return "down", RED
    return "neutral", CYAN


def _title_from_prompt(prompt: str) -> str:
    """thumbnail_prompt에서 제목 힌트 추출 (title 없을 때 폴백)"""
    if not prompt:
        return "US Market Analysis"
    words = prompt.strip().split()
    return " ".join(words[:10]) if len(words) > 10 else prompt.strip()


def _save_webp(fig: plt.Figure, filename: str) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=DARK_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf).convert("RGB")
    output_path = OUTPUT_DIR / f"{filename}.webp"
    img.save(output_path, format="WEBP", quality=85, method=4, lossless=False)

    original_kb = len(buf.getvalue()) / 1024
    webp_kb     = output_path.stat().st_size / 1024
    saving_pct  = (1 - webp_kb / original_kb) * 100 if original_kb else 0
    print(f"✅ Thumbnail saved: {output_path} "
          f"[PNG≈{original_kb:.0f}KB → WebP≈{webp_kb:.0f}KB, -{saving_pct:.0f}%]")
    return str(output_path)


def thumbnail_to_base64(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mime   = ("image/webp" if suffix == ".webp" else
              "image/png"  if suffix == ".png"  else "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"
