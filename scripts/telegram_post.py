#!/usr/bin/env python3
"""
scripts/telegram_post.py
변경사항:
  - 원문 출처 표기 영문으로 변경
  - 이미지: Unsplash 무료 API → Gemini Imagen → Pillow 폴백
  - Publishing cancelled 시 sys.exit(0) 으로 정상 종료
    → GitHub workflow 실패 처리 안 됨 → 실패 알림 메일 발송 안 됨
  - result 파일의 proceed 플래그로 게시 단계 자동 스킵
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.gemini_client   import generate_post, parse_json_response
from utils.fact_checker    import fact_check_with_search
from utils.article_fetcher import fetch_article
from utils.post_image      import get_post_image
from utils.blogger         import publish_to_blogger
from utils.formatting      import build_html_post
from utils.telegram_notify import TelegramNotifier

KST         = timezone(timedelta(hours=9))
RESULT_FILE = Path("fact_check_result.json")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",    required=True, choices=["fact_check", "publish"])
    p.add_argument("--url",     required=True)
    p.add_argument("--chat",    required=True)
    p.add_argument("--comment", default="")
    return p.parse_args()


# ─────────────────────────────────────────────────────────
# Mode 1: Fact Check
# ─────────────────────────────────────────────────────────

def run_fact_check(url: str, chat_id: str, comment: str, bot: TelegramNotifier):
    bot.send(chat_id,
        "📖 <b>[1/4] Reading article...</b>\n"
        f"🔗 {url[:60]}{'...' if len(url) > 60 else ''}"
    )

    article = fetch_article(url)

    if not article.get("text"):
        bot.send(chat_id,
            "❌ Could not retrieve article content.\n\n"
            "Possible reasons:\n"
            "• Paywall / subscription required\n"
            "• JavaScript-rendered site\n"
            "• Access blocked\n\n"
            "Please try a different article link."
        )
        # ✅ exit(0): 정상 종료 → GitHub 실패 메일 없음
        _save_cancelled()
        sys.exit(0)

    bot.send(chat_id,
        f"✅ Article loaded\n"
        f"📰 Title: <b>{article.get('title', 'N/A')[:80]}</b>\n"
        f"📝 Length: {len(article.get('text', ''))} chars\n\n"
        "🔍 <b>[2/4] AI fact-checking in progress...</b>"
    )

    fact_result = fact_check_with_search(article, comment)

    score        = fact_result.get("credibility_score", 0)
    verdict      = fact_result.get("verdict", "UNKNOWN")
    issues       = fact_result.get("issues", [])
    related_info = fact_result.get("related_information", "")
    proceed      = fact_result.get("proceed_to_publish", False)

    score_emoji   = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    grounding_tag = "🔍 실시간 검색 검증" if fact_result.get("grounding_used") else "📚 학습 데이터 검증"
    sources       = fact_result.get("search_sources", [])
    source_count  = len(sources)

    verdict_map = {
        "VERIFIED":    "✅ Verified",
        "MOSTLY_TRUE": "🟡 Mostly true",
        "MIXED":       "⚠️ Mixed",
        "UNVERIFIED":  "❓ Unverified",
        "FALSE":       "❌ False",
    }
    verdict_str = verdict_map.get(verdict, f"❓ {verdict}")
    issues_str  = ""
    if issues:
        issues_str = "\n\n⚠️ <b>지적 사항:</b>\n" + "\n".join(f"• {i}" for i in issues[:3])

    sources_str = ""
    if sources:
        sources_str = "\n\n🔗 <b>검증 출처:</b>\n" + "\n".join(
            f"• <a href=\"{s['url']}\">{s.get('title','') or s['url'][:50]}</a>"
            for s in sources[:3]
        )

    bot.send(chat_id,
        f"📊 <b>[Fact-check Result]</b>\n\n"
        f"{score_emoji} Credibility: <b>{score}/100</b>\n"
        f"Verdict: <b>{verdict_str}</b>\n"
        f"<i>{grounding_tag}</i> ({source_count}개 출처 확인)\n"
        f"{issues_str}\n\n"
        f"📌 <b>관련 최신 정보:</b>\n{related_info[:400]}"
        f"{sources_str}"
    )

    if not proceed:
        bot.send(chat_id,
            "🛑 <b>Publishing cancelled.</b>\n\n"
            "The article has low credibility or contains inaccurate information.\n"
            "Please try a different source."
        )
        # ✅ exit(0): 정상 종료 → GitHub 실패 메일 없음
        # proceed=false 저장 → 게시 단계가 조건문으로 자동 스킵
        RESULT_FILE.write_text(
            json.dumps({**fact_result, "article": article, "proceed": False},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        sys.exit(0)

    bot.send(chat_id,
        "✅ <b>Fact-check passed!</b>\n\n"
        "🖼️ <b>[3/4] Fetching image & writing post...</b>"
    )

    RESULT_FILE.write_text(
        json.dumps({**fact_result, "article": article, "proceed": True},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[Fact-check] Done — verdict={verdict}, score={score}, proceed={proceed}")


# ─────────────────────────────────────────────────────────
# Mode 2: Publish
# ─────────────────────────────────────────────────────────

def run_publish(url: str, chat_id: str, bot: TelegramNotifier):
    if not RESULT_FILE.exists():
        bot.send(chat_id, "❌ Fact-check result file not found.")
        sys.exit(0)

    data    = json.loads(RESULT_FILE.read_text(encoding="utf-8"))

    # proceed=False 면 게시 없이 정상 종료
    if not data.get("proceed", False):
        print("[Publish] proceed=False — 게시 스킵 (정상 종료)")
        sys.exit(0)

    article = data.get("article", {})

    # ── 포스트 생성 ───────────────────────────────────────
    post = generate_blog_post(data, article, url)

    # ── 이미지 조달 (Unsplash → Gemini Imagen → Pillow) ──
    filename   = f"telegram_{datetime.now(KST).strftime('%Y%m%d_%H%M')}"
    image_path = get_post_image(post_data=post, article=article, filename=filename)

    # ── 원문 출처 표기 (영문) ─────────────────────────────
    source_domain = article.get("source", "")
    source_label  = source_domain if source_domain else "Original Article"
    source_credit = (
        f'<p style="font-size:13px;color:#888;font-family:Arial,sans-serif;">'
        f'📌 Source: '
        f'<a href="{url}" target="_blank" rel="nofollow">{source_label}</a>'
        f'</p>\n'
    )

    # ── 이미지 출처 표기 (영문) ───────────────────────────
    image_credit = _build_image_credit_html(image_path)

    # ── HTML 빌드 ─────────────────────────────────────────
    full_html = build_html_post(
        content_html=source_credit + post["content_html"] + image_credit,
        thumbnail_path=image_path,
        market_data={},
        post_type="telegram",
    )

    # ── Blogger 게시 ──────────────────────────────────────
    result = publish_to_blogger(
        title=post["title"],
        content=full_html,
        labels=post["tags"],
        blog_id=os.environ["BLOGGER_BLOG_ID"],
    )

    post_url    = result.get("url", "")
    fact_score  = data.get("credibility_score", "N/A")
    verdict_map = {
        "VERIFIED":    "✅ Verified",
        "MOSTLY_TRUE": "🟡 Mostly true",
        "MIXED":       "⚠️ Mixed",
    }
    verdict_str = verdict_map.get(data.get("verdict", ""), data.get("verdict", ""))

    bot.send(chat_id,
        f"🎉 <b>[4/4] Published successfully!</b>\n\n"
        f"📰 <b>{post['title'][:80]}</b>\n\n"
        f"📊 Fact-check: {verdict_str} ({fact_score}/100)\n"
        f"🏷️ Tags: {', '.join(post['tags'][:3])}\n\n"
        f"🔗 <a href=\"{post_url}\">View on blog</a>"
    )

    print(f"[Published] {result.get('url')}")


def generate_blog_post(fact_data: dict, article: dict, source_url: str) -> dict:
    today = datetime.now(KST).strftime("%B %d, %Y")

    prompt = f"""You are a professional US stock market analyst writing an SEO-optimized blog post.

Today (KST): {today}
Original Article Title: {article.get('title', '')}
Source URL: {source_url}
Fact-Check Verdict: {fact_data.get('verdict')} (Score: {fact_data.get('credibility_score')}/100)
Verified Summary: {fact_data.get('summary_for_blog', '')}
Blog Angle: {fact_data.get('blog_angle', '')}
Related Information: {fact_data.get('related_information', '')}

Write a comprehensive SEO-optimized English blog post based on the VERIFIED facts above.

TITLE: Hook-driven, high-CTR headline with specific numbers/impact.
META DESCRIPTION: 150-160 chars, SEO-optimized.

CONTENT (HTML, 700-900 words):
<h2>What Happened</h2>
<h2>Market Impact Analysis</h2>
<h2>Context & Background</h2>
<h2>Key Takeaways for Investors</h2>
<h2>What to Watch Next</h2>

SEO keywords: "stock market", "investor analysis", relevant tickers/sectors.
Use hedging language. Mark AI analysis with "[Analysis]" prefix.

THUMBNAIL PROMPT: Real-world photo scene, NO charts/graphs/text overlays.
  Good: "Traders on a busy stock exchange floor watching screens"
  Bad: "Financial chart with upward trend"
Max 20 words.

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-slug",
  "tags": ["Market Analysis", "Investing", "Wall Street", "Stock Market", "...relevant tag"],
  "content_html": "<h2>What Happened</h2><p>...</p>...",
  "thumbnail_prompt": "..."
}}"""

    raw = generate_post(prompt)
    return parse_json_response(raw)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _save_cancelled():
    """게시 취소 시 proceed=False 파일 저장"""
    RESULT_FILE.write_text(
        json.dumps({"proceed": False, "article": {}}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _build_image_credit_html(image_path: str) -> str:
    """이미지 출처 표기 — 영문"""
    if not image_path:
        return ""
    path_lower = image_path.lower()
    if "_unsplash" in path_lower:
        return (
            '\n<p style="font-size:11px;color:#aaa;text-align:right;'
            'font-family:Arial,sans-serif;margin-top:4px;">'
            'Photo via <a href="https://unsplash.com" target="_blank" '
            'rel="nofollow" style="color:#aaa;">Unsplash</a></p>\n'
        )
    elif "_imagen" in path_lower:
        return (
            '\n<p style="font-size:11px;color:#aaa;text-align:right;'
            'font-family:Arial,sans-serif;margin-top:4px;">'
            'Image generated by AI (Google Gemini Imagen)</p>\n'
        )
    return ""


def main():
    args = parse_args()
    bot  = TelegramNotifier(token=os.environ.get("TELEGRAM_BOT_TOKEN", ""))

    if args.mode == "fact_check":
        run_fact_check(args.url, args.chat, args.comment, bot)
    elif args.mode == "publish":
        run_publish(args.url, args.chat, bot)


if __name__ == "__main__":
    main()
