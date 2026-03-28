#!/usr/bin/env python3
"""
Thumbnail Generator — 100% FREE (No OpenAI / No paid API)
Uses Pillow + matplotlib to programmatically generate professional-looking
blog thumbnails that reflect actual market data (dynamic charts, real colors).

Output: 1200x628px WebP (standard OG image / blog header size)
WebP format reduces file size by ~30-50% vs PNG with no visible quality loss.
"""

import base64
import math
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import io

KST = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("thumbnails")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Color palette ────────────────────────────────────────
DARK_BG = "#0a0f1e"
NAVY    = "#1a2744"
GOLD    = "#FFD700"
CYAN    = "#00BFFF"
GREEN   = "#00C853"
RED     = "#FF3D3D"
WHITE   = "#FFFFFF"
GRAY    = "#8899aa"


def generate_thumbnail(prompt: str, filename: str, market_data: dict = None) -> str:
    """
    Generate a dynamic, data-driven thumbnail using matplotlib only.
    Saves as WebP for smaller file size and faster loading.

    Args:
        prompt:      Claude's description (used to infer market direction/tone)
        filename:    Output file basename (e.g. "morning_20250324")
        market_data: Real index data dict (optional — enables live values)

    Returns:
        Absolute path to saved WebP
    """
    direction, accent = _infer_direction(prompt, market_data)
    fig = _build_figure(filename, direction, accent, market_data)

    # ── PNG 버퍼에 먼저 렌더링 후 Pillow로 WebP 변환 ──────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=DARK_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf).convert("RGB")  # WebP는 RGB 권장
    output_path = OUTPUT_DIR / f"{filename}.webp"
    img.save(
        output_path,
        format="WEBP",
        quality=82,        # 82 = 시각적 무손실에 가까운 품질, PNG 대비 ~40% 절감
        method=4,          # 인코딩 속도/압축률 균형 (0=빠름, 6=최고압축)
        lossless=False,
    )

    original_kb = len(buf.getvalue()) / 1024
    webp_kb     = output_path.stat().st_size / 1024
    saving_pct  = (1 - webp_kb / original_kb) * 100 if original_kb else 0
    print(
        f"✅ Thumbnail (WebP) saved: {output_path}  "
        f"[PNG≈{original_kb:.0f}KB → WebP≈{webp_kb:.0f}KB, -{saving_pct:.0f}% 절감]"
    )
    return str(output_path)


# ─────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────

def _infer_direction(prompt: str, market_data: dict):
    """Determine market direction and accent color."""
    # 1) From actual index data
    if market_data and "indices" in market_data:
        chg = (market_data["indices"].get("S&P 500") or {}).get("change_pct", 0) or 0
        if chg > 0.3:
            return "up", GREEN
        if chg < -0.3:
            return "down", RED

    # 2) From prompt text
    p = (prompt or "").lower()
    up_kw   = ["surge", "rally", "gains", "rises", "record", "bull", "soars", "climbs", "jumps"]
    down_kw = ["tumbles", "falls", "drops", "decline", "slump", "bear", "plunges", "sinks"]
    if sum(1 for w in up_kw if w in p) > sum(1 for w in down_kw if w in p):
        return "up", GREEN
    if sum(1 for w in down_kw if w in p) > sum(1 for w in up_kw if w in p):
        return "down", RED
    return "neutral", CYAN


def _build_figure(filename, direction, accent, market_data):
    fig = plt.figure(figsize=(12, 6.28), facecolor=DARK_BG)

    # ── Full-canvas background layer ────────────────────────
    ax_bg = fig.add_axes([0, 0, 1, 1])
    ax_bg.set_facecolor(DARK_BG)
    ax_bg.axis("off")

    # Subtle grid
    for y in np.linspace(0.08, 0.92, 7):
        ax_bg.axhline(y, color="#1e3060", lw=0.4, alpha=0.45)
    for x in np.linspace(0.04, 0.96, 12):
        ax_bg.axvline(x, color="#1e3060", lw=0.4, alpha=0.45)

    # ── Left chart panel ─────────────────────────────────────
    ax_chart = fig.add_axes([0.03, 0.10, 0.44, 0.78])
    ax_chart.set_facecolor("none")
    ax_chart.axis("off")
    _draw_chart(ax_chart, direction, accent)

    # ── Vertical divider ─────────────────────────────────────
    ax_bg.axvline(0.50, color=accent, lw=0.8, alpha=0.35)

    # ── Right text panel ─────────────────────────────────────
    _draw_right_panel(ax_bg, filename, direction, accent, market_data)

    # ── Top-left badge ───────────────────────────────────────
    ax_badge = fig.add_axes([0.02, 0.90, 0.22, 0.075])
    ax_badge.set_facecolor(NAVY)
    ax_badge.text(0.5, 0.5, "Wall Street Daily Briefing",
                  ha="center", va="center", fontsize=7.5,
                  color=GOLD, fontweight="bold", transform=ax_badge.transAxes)
    ax_badge.axis("off")

    # ── Bottom accent bar ────────────────────────────────────
    ax_bar = fig.add_axes([0, 0, 1, 0.022])
    ax_bar.set_facecolor(accent)
    ax_bar.axis("off")

    return fig


def _draw_chart(ax, direction, accent):
    """Simulated market chart line with volume bars."""
    np.random.seed(7)
    n = 65

    if direction == "up":
        trend = np.linspace(0, 2.2, n)
    elif direction == "down":
        trend = np.linspace(0, -2.2, n)
    else:
        trend = np.sin(np.linspace(0, math.pi * 1.5, n)) * 0.7

    noise = np.random.normal(0, 0.18, n).cumsum() * 0.28
    raw   = 100 + trend * 14 + noise
    lo, hi = raw.min(), raw.max()
    prices = (raw - lo) / max(hi - lo, 1e-9) * 0.72 + 0.14

    x = np.linspace(0, 1, n)

    # Glow + fill
    ax.fill_between(x, 0.05, prices, color=accent, alpha=0.10)
    ax.plot(x, prices, color=accent, lw=8, alpha=0.07)      # glow
    ax.plot(x, prices, color=accent, lw=2.5, solid_capstyle="round")

    # Moving average
    w = 12
    ma = np.convolve(prices, np.ones(w) / w, mode="valid")
    ax.plot(x[w-1:], ma, color=WHITE, lw=1.0, alpha=0.35, linestyle="--")

    # End dot
    ax.scatter([x[-1]], [prices[-1]], color=accent, s=90, zorder=6)

    # Volume bars
    vols = np.abs(np.random.normal(0.5, 0.18, n)).clip(0.08, 1.0)
    bar_w = 0.011
    for i in range(n):
        clr = GREEN if (i == 0 or prices[i] >= prices[i-1]) else RED
        ax.bar(x[i], vols[i] * 0.075, width=bar_w, bottom=0.02,
               color=clr, alpha=0.45, linewidth=0)

    ax.set_xlim(-0.02, 1.03)
    ax.set_ylim(0, 1.08)


def _draw_right_panel(ax, filename, direction, accent, market_data):
    """Draw all text elements on the right half of the thumbnail."""
    is_morning = "morning" in filename
    date_str   = datetime.now(KST).strftime("%B %d, %Y")
    post_label = "MARKET CLOSE REVIEW" if is_morning else "PRE-MARKET PREVIEW"
    dir_badge  = {"up": "▲ MARKET GAINS", "down": "▼ MARKET LOSS", "neutral": "◆ MIXED SESSION"}[direction]

    kw = dict(transform=ax.transAxes, va="center")

    # Post type
    ax.text(0.535, 0.90, post_label,   fontsize=8.5,  color=GOLD,   fontweight="bold", **kw)
    # Date
    ax.text(0.535, 0.81, date_str,     fontsize=10,   color=GRAY,   **kw)
    # Direction badge
    ax.text(0.535, 0.71, dir_badge,    fontsize=13.5, color=accent, fontweight="bold", **kw)

    # Thin separator line
    ax.axhline(0.645, xmin=0.525, xmax=0.975, color=accent, lw=0.7, alpha=0.55)

    # Index rows
    _draw_index_rows(ax, market_data, is_morning)

    # Brand footer
    ax.text(0.97, 0.035, "fund-up.blogspot.com",
            fontsize=6.5, color=GRAY, alpha=0.45, ha="right",
            transform=ax.transAxes, va="center")


def _draw_index_rows(ax, market_data, is_morning):
    """Draw 4 index value rows on the right panel."""
    rows = [
        ("S&P 500",  "SPX",  0.575),
        ("NASDAQ",   "NDX",  0.475),
        ("Dow Jones","DJI",  0.375),
        ("VIX",      "VIX",  0.275),
    ]
    kw = dict(transform=ax.transAxes, va="center")

    for name, abbr, y in rows:
        val_str = "—"
        chg_str = ""
        chg_clr = WHITE

        if market_data and "indices" in market_data:
            d = market_data["indices"].get(name) or {}
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


def thumbnail_to_base64(path: str) -> str:
    """Return base64 data URI for HTML embedding."""
    suffix = Path(path).suffix.lower()
    mime   = "image/webp" if suffix == ".webp" else (
             "image/png"  if suffix == ".png"  else "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"
