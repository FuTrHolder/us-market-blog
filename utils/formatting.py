#!/usr/bin/env python3
"""
HTML Formatting Utility
Builds the final HTML for blog posts including:
- Responsive thumbnail
- Earnings comparison tables
- Economic indicator tables
- SEO meta structure
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import base64
import os

KST = timezone(timedelta(hours=9))


def build_html_post(
    content_html: str,
    thumbnail_path: str,
    market_data: dict,
    post_type: str = "morning",
    earnings_table_html: str = "",
    economic_table_html: str = ""
) -> str:
    """
    Assemble the final HTML post with thumbnail, content, and optional tables.
    Blogger strips <head> so we only return the body content.
    """
    
    thumbnail_html = _build_thumbnail_html(thumbnail_path)
    
    # Inject tables into content if present
    final_content = content_html
    
    if earnings_table_html:
        # Insert after the Earnings section heading
        final_content = final_content.replace(
            '<h2>Earnings in the Spotlight</h2>',
            f'<h2>Earnings in the Spotlight</h2>\n{earnings_table_html}'
        )
        # Fallback: append at end if section not found
        if earnings_table_html not in final_content:
            final_content += f"\n<h2>Earnings Comparison</h2>\n{earnings_table_html}"

    if economic_table_html:
        final_content = final_content.replace(
            '<h2>Economic Data Releases</h2>',
            f'<h2>Economic Data Releases</h2>\n{economic_table_html}'
        )
        if economic_table_html not in final_content:
            final_content += f"\n<h2>Economic Data</h2>\n{economic_table_html}"

    # Market summary bar (for morning posts)
    market_bar_html = ""
    if post_type == "morning" and "indices" in market_data:
        market_bar_html = _build_market_summary_bar(market_data["indices"])

    post_date = datetime.now(KST).strftime("%B %d, %Y · %I:%M %p KST")

    html = f"""
<div class="wsdb-post" style="font-family: 'Georgia', 'Times New Roman', serif; max-width: 860px; margin: 0 auto; color: #1a1a2e; line-height: 1.8;">

  <!-- Thumbnail -->
  {thumbnail_html}

  <!-- Byline -->
  <p style="color: #888; font-size: 13px; margin: 8px 0 20px; font-family: Arial, sans-serif;">
    📅 {post_date} &nbsp;|&nbsp; Wall Street Daily Briefing
  </p>

  <!-- Market Summary Bar (morning only) -->
  {market_bar_html}

  <!-- Post Content -->
  <div class="wsdb-content" style="margin-top: 24px;">
    {final_content}
  </div>

  <!-- Disclaimer -->
  <div style="margin-top: 40px; padding: 16px 20px; background: #f8f8f8; border-left: 4px solid #ccc; border-radius: 4px; font-size: 13px; color: #666; font-family: Arial, sans-serif;">
    <strong>Disclaimer:</strong> This post is for informational and educational purposes only. 
    Nothing here constitutes financial advice. Always do your own research before making investment decisions.
  </div>

</div>

<style>
  .wsdb-post h2 {{
    font-size: 22px;
    font-weight: bold;
    color: #0a0f1e;
    border-bottom: 2px solid #e8e8e8;
    padding-bottom: 6px;
    margin-top: 36px;
  }}
  .wsdb-post h3 {{
    font-size: 18px;
    color: #1a2744;
    margin-top: 24px;
  }}
  .wsdb-post table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    font-family: Arial, sans-serif;
    font-size: 14px;
  }}
  .wsdb-post th {{
    background: #1a2744;
    color: #FFD700;
    padding: 10px 12px;
    text-align: left;
  }}
  .wsdb-post td {{
    padding: 9px 12px;
    border-bottom: 1px solid #e8e8e8;
  }}
  .wsdb-post tr:nth-child(even) td {{
    background: #f5f7fa;
  }}
  .wsdb-post .positive {{ color: #16a34a; font-weight: bold; }}
  .wsdb-post .negative {{ color: #dc2626; font-weight: bold; }}
  .wsdb-post .neutral  {{ color: #6b7280; }}
</style>
"""
    return html


def _build_thumbnail_html(thumbnail_path: str) -> str:
    """Return an <img> or <object> tag for the thumbnail."""
    if not thumbnail_path or not Path(thumbnail_path).exists():
        return ""

    suffix = Path(thumbnail_path).suffix.lower()

    if suffix == ".svg":
        # Inline SVG as base64 data URI
        with open(thumbnail_path, "r") as f:
            svg_data = f.read()
        b64 = base64.b64encode(svg_data.encode()).decode()
        src = f"data:image/svg+xml;base64,{b64}"
    else:
        # JPEG/PNG as base64
        with open(thumbnail_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        mime = "image/jpeg" if suffix in [".jpg", ".jpeg"] else "image/png"
        src = f"data:{mime};base64,{b64}"

    return f'<img src="{src}" alt="US Stock Market Analysis" style="width:100%; border-radius:8px; margin-bottom:16px;" loading="lazy"/>'


def _build_market_summary_bar(indices: dict) -> str:
    """Build a visual market summary ticker bar."""
    if not indices:
        return ""

    items_html = ""
    key_indices = ["S&P 500", "NASDAQ", "Dow Jones", "VIX"]
    
    for name in key_indices:
        data = indices.get(name, {})
        if "error" in data or not data:
            continue
        
        close = data.get("close", "—")
        chg = data.get("change_pct", 0)
        arrow = "▲" if chg >= 0 else "▼"
        css_class = "positive" if chg >= 0 else "negative"
        
        items_html += f"""
        <div style="background: #1a2744; padding: 10px 18px; border-radius: 6px; min-width: 140px; text-align: center;">
          <div style="color: #aaa; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">{name}</div>
          <div style="color: white; font-size: 18px; font-weight: bold; margin: 2px 0;">{close:,}</div>
          <div style="font-size: 13px;" class="{css_class}">{arrow} {abs(chg):.2f}%</div>
        </div>
        """

    if not items_html:
        return ""

    return f"""
    <div style="display: flex; gap: 10px; flex-wrap: wrap; margin: 20px 0; font-family: Arial, sans-serif;">
      {items_html}
    </div>
    """


def build_earnings_table(earnings: list) -> str:
    """
    Build an HTML earnings comparison table.
    Shows: Company | Quarter | EPS Estimate | EPS Actual | Surprise | Rev Estimate | Rev Actual
    Plus historical EPS per company.
    """
    if not earnings:
        return ""

    rows_html = ""
    for e in earnings:
        symbol = e.get("symbol", "")
        name = e.get("name", symbol)
        quarter = e.get("fiscal_quarter", "")[:7]  # e.g. 2024-Q3
        eps_est = _fmt_eps(e.get("eps_estimate"))
        eps_act = _fmt_eps(e.get("eps_actual"))
        rev_est = _fmt_revenue(e.get("revenue_estimate"))
        rev_act = _fmt_revenue(e.get("revenue_actual"))
        time_tag = e.get("time", "")
        
        # EPS surprise
        surprise_html = "—"
        if e.get("eps_estimate") and e.get("eps_actual"):
            surprise = e["eps_actual"] - e["eps_estimate"]
            pct = (surprise / abs(e["eps_estimate"])) * 100 if e["eps_estimate"] != 0 else 0
            css = "positive" if surprise >= 0 else "negative"
            sign = "+" if surprise >= 0 else ""
            surprise_html = f'<span class="{css}">{sign}{pct:.1f}%</span>'

        rows_html += f"""
        <tr>
          <td><strong>{symbol}</strong><br/><span style="font-size:12px;color:#666">{name}</span></td>
          <td>{quarter}<br/><span style="font-size:11px;color:#888">{time_tag}</span></td>
          <td>{eps_est}</td>
          <td>{eps_act}</td>
          <td style="text-align:center">{surprise_html}</td>
          <td>{rev_est}</td>
          <td>{rev_act}</td>
        </tr>
        """
        
        # Historical EPS sub-rows
        history = e.get("eps_history", [])
        if history:
            history_cells = ""
            for h in history[:4]:
                q = h.get("quarter", "")[:7]
                act = _fmt_eps(h.get("eps_actual"))
                est = _fmt_eps(h.get("eps_estimate"))
                surp = h.get("surprise_pct")
                surp_str = f'<span class="{"positive" if (surp or 0) >= 0 else "negative"}">{("+" if (surp or 0) >= 0 else "")}{surp:.1f}%</span>' if surp is not None else "—"
                history_cells += f'<td style="border-right:1px solid #e0e0e0; padding:6px 10px; font-size:12px"><strong>{q}</strong><br/>A: {act} / E: {est}<br/>{surp_str}</td>'
            
            rows_html += f"""
            <tr style="background:#f9fafb">
              <td colspan="2" style="font-size:12px;color:#888;padding-left:24px">↳ Historical EPS</td>
              {history_cells}
              <td></td>
            </tr>
            """

    return f"""
    <div style="overflow-x:auto; margin: 20px 0;">
      <table style="width:100%; border-collapse:collapse; font-family:Arial,sans-serif; font-size:14px;">
        <thead>
          <tr style="background:#1a2744; color:#FFD700;">
            <th style="padding:10px 12px; text-align:left">Company</th>
            <th style="padding:10px 12px">Quarter</th>
            <th style="padding:10px 12px">EPS Est.</th>
            <th style="padding:10px 12px">EPS Actual</th>
            <th style="padding:10px 12px; text-align:center">Surprise</th>
            <th style="padding:10px 12px">Rev Est.</th>
            <th style="padding:10px 12px">Rev Actual</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    """


def build_economic_table(events: list) -> str:
    """
    Build an HTML economic indicator comparison table.
    Shows: Indicator | Time | Previous | Forecast | Actual | Impact
    """
    if not events:
        return ""

    rows_html = ""
    for e in events:
        event_name = e.get("event", "")
        time_str = str(e.get("date", ""))[-5:] if e.get("date") else ""  # HH:MM
        prev = _fmt_indicator(e.get("previous"))
        forecast = _fmt_indicator(e.get("estimate"))
        actual = _fmt_indicator(e.get("actual"))
        impact = e.get("impact", "")
        
        # Color for impact level
        impact_color = {"High": "#dc2626", "Medium": "#d97706", "Low": "#6b7280"}.get(impact, "#6b7280")
        
        # Beat/miss indicator
        beat_html = "—"
        if e.get("actual") is not None and e.get("estimate") is not None:
            diff = float(e["actual"]) - float(e["estimate"])
            beat_html = f'<span class="positive">Beat ▲</span>' if diff > 0 else f'<span class="negative">Miss ▼</span>'

        rows_html += f"""
        <tr>
          <td style="font-weight:bold">{event_name}</td>
          <td style="color:#666;font-size:13px">{time_str} ET</td>
          <td>{prev}</td>
          <td style="font-weight:bold">{forecast}</td>
          <td style="font-weight:bold">{actual}</td>
          <td style="text-align:center">{beat_html}</td>
          <td style="text-align:center"><span style="color:{impact_color};font-weight:bold;font-size:12px">{impact}</span></td>
        </tr>
        """

    return f"""
    <div style="overflow-x:auto; margin: 20px 0;">
      <table style="width:100%; border-collapse:collapse; font-family:Arial,sans-serif; font-size:14px;">
        <thead>
          <tr style="background:#1a2744; color:#FFD700;">
            <th style="padding:10px 12px; text-align:left">Indicator</th>
            <th style="padding:10px 12px">Time (ET)</th>
            <th style="padding:10px 12px">Previous</th>
            <th style="padding:10px 12px">Forecast</th>
            <th style="padding:10px 12px">Actual</th>
            <th style="padding:10px 12px; text-align:center">Result</th>
            <th style="padding:10px 12px; text-align:center">Impact</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    """


# ─── Helpers ───────────────────────────────────

def _fmt_eps(value) -> str:
    if value is None:
        return "—"
    return f"${float(value):.2f}"


def _fmt_revenue(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    elif abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"


def _fmt_indicator(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):g}"
    except Exception:
        return str(value)
