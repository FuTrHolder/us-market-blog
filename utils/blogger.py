#!/usr/bin/env python3
"""
Google Blogger API v3 Publisher
인증 방식: OAuth 2.0 Refresh Token (본인 Google 계정 직접 인증)

서비스 계정(Service Account) 방식 대신 사용하는 이유:
  - 서비스 계정 이메일은 Gmail이 아니라 Blogger 작성자 초대 불가
  - Refresh Token 방식은 본인 계정으로 직접 인증하므로 초대 불필요
  - 최초 1회 get_refresh_token.py 실행으로 영구 토큰 발급

필요한 GitHub Secrets (4개):
  GOOGLE_CLIENT_ID       Google Cloud OAuth 클라이언트 ID
  GOOGLE_CLIENT_SECRET   Google Cloud OAuth 클라이언트 Secret
  BLOGGER_REFRESH_TOKEN  get_refresh_token.py로 발급한 Refresh Token
  BLOGGER_BLOG_ID        Blogger 블로그 숫자 ID
"""

import os
import json
import requests

BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
TOKEN_URL        = "https://oauth2.googleapis.com/token"


def _get_access_token() -> str:
    """
    Refresh Token으로 단기 Access Token 발급.
    Refresh Token은 만료되지 않으므로 한 번만 발급하면 됩니다.
    """
    client_id     = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("BLOGGER_REFRESH_TOKEN", "")

    missing = [k for k, v in {
        "GOOGLE_CLIENT_ID":     client_id,
        "GOOGLE_CLIENT_SECRET": client_secret,
        "BLOGGER_REFRESH_TOKEN":refresh_token,
    }.items() if not v]

    if missing:
        raise ValueError(
            f"다음 환경변수가 설정되지 않았습니다: {', '.join(missing)}\n"
            "get_refresh_token.py를 실행해서 Refresh Token을 발급받으세요."
        )

    r = requests.post(TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=15)

    if r.status_code == 400:
        err = r.json().get("error_description", "")
        raise PermissionError(
            f"Access Token 발급 실패: {err}\n"
            "BLOGGER_REFRESH_TOKEN이 만료됐거나 잘못됐습니다.\n"
            "get_refresh_token.py를 다시 실행해서 새 토큰을 발급받으세요."
        )

    r.raise_for_status()
    return r.json()["access_token"]


def publish_to_blogger(
    title: str,
    content: str,
    labels: list,
    blog_id: str,
    publish: bool = True,
) -> dict:
    """
    Blogger에 포스트 게시.

    Args:
        title:   포스트 제목
        content: HTML 본문
        labels:  태그 리스트
        blog_id: Blogger 블로그 숫자 ID
        publish: True=즉시 발행, False=임시저장

    Returns:
        {'id', 'url', 'title', 'published', 'status'}
    """
    token   = _get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    post_body = {
        "kind":    "blogger#post",
        "title":   title,
        "content": content,
        "labels":  labels,
    }

    # Blogger API v3: isDraft는 URL 파라미터가 아닌 쿼리 파라미터로 전달
    # 즉시 발행: /posts/ (기본값이 LIVE)
    # 임시저장:  /posts/?isDraft=true
    endpoint = f"{BLOGGER_API_BASE}/blogs/{blog_id}/posts/"
    if not publish:
        endpoint += "?isDraft=true"

    r = requests.post(endpoint, headers=headers, json=post_body, timeout=30)

    if r.status_code == 400:
        try:
            err_detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            err_detail = r.text[:200]
        raise ValueError(
            f"Blogger API 400 오류 — 잘못된 요청.\n"
            f"상세: {err_detail}\n"
            "확인 사항:\n"
            "  (1) BLOGGER_BLOG_ID가 숫자만 있는지 확인 (URL 아님)\n"
            "  (2) content HTML에 잘못된 문자 포함 여부 확인"
        )

    if r.status_code == 401:
        raise PermissionError(
            "Blogger API 401 오류.\n"
            "확인 사항:\n"
            "  (1) Google Cloud Console에서 Blogger API v3 활성화 여부\n"
            "  (2) BLOGGER_BLOG_ID가 올바른 숫자인지 확인\n"
            "  (3) Refresh Token이 블로그 관리자 계정으로 발급됐는지 확인"
        )

    if r.status_code == 403:
        raise PermissionError(
            "Blogger API 403 오류 — 권한 없음.\n"
            "OAuth 동의 화면에서 blogger scope가 승인됐는지 확인하세요."
        )

    r.raise_for_status()
    data = r.json()

    return {
        "id":        data.get("id"),
        "url":       data.get("url"),
        "title":     data.get("title"),
        "published": data.get("published"),
        "status":    "published" if publish else "draft",
    }


def update_post(post_id: str, blog_id: str,
                title: str = None, content: str = None) -> dict:
    """기존 포스트 업데이트."""
    token   = _get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    patch = {}
    if title:   patch["title"]   = title
    if content: patch["content"] = content

    r = requests.patch(
        f"{BLOGGER_API_BASE}/blogs/{blog_id}/posts/{post_id}",
        headers=headers, json=patch, timeout=30,
    )
    r.raise_for_status()
    return r.json()
