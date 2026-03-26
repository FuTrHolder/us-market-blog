#!/usr/bin/env python3
"""
[최초 1회만 실행] Google OAuth Refresh Token 발급 스크립트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
서비스 계정(Service Account) 대신 본인 Google 계정으로 직접 인증합니다.
서비스 계정 이메일은 Gmail이 아니라 Blogger 초대가 불가능한 문제를 해결합니다.

[사전 준비] Google Cloud Console에서 OAuth 2.0 클라이언트 ID 생성:
  1. console.cloud.google.com 접속
  2. APIs & Services → Credentials → Create Credentials → OAuth client ID
  3. Application type: "Desktop app" 선택
  4. 생성된 Client ID, Client Secret 복사
  5. OAuth 동의 화면(Consent Screen) → 테스트 사용자에 본인 이메일 추가

[실행]
  python get_refresh_token.py

[결과]
  BLOGGER_REFRESH_TOKEN 값이 출력됩니다 → GitHub Secret에 등록하세요.
"""

import os
import sys
import json
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ── 여기에 Google Cloud Console에서 받은 값을 입력하세요 ──
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")      # 또는 직접 입력
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")  # 또는 직접 입력
# ──────────────────────────────────────────────────────────

REDIRECT_URI  = "http://localhost:8080"
SCOPE         = "https://www.googleapis.com/auth/blogger"
AUTH_URL      = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL     = "https://oauth2.googleapis.com/token"

auth_code_holder = {"code": None}


class CallbackHandler(BaseHTTPRequestHandler):
    """로컬 서버로 Google 리다이렉트를 받아 인증 코드 캡처."""
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        auth_code_holder["code"] = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write("<h2>Auth complete! Close this tab.</h2>".encode())

    def log_message(self, *args):
        pass  # 로그 출력 억제


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("=" * 60)
        print("오류: CLIENT_ID와 CLIENT_SECRET을 설정해주세요.")
        print()
        print("Google Cloud Console에서 발급 방법:")
        print("  1. console.cloud.google.com 접속")
        print("  2. APIs & Services → Credentials")
        print("  3. Create Credentials → OAuth client ID")
        print("  4. Application type: 'Desktop app'")
        print("  5. 생성된 값을 이 파일 상단 CLIENT_ID / CLIENT_SECRET에 입력")
        print("=" * 60)
        sys.exit(1)

    # 1. 인증 URL 생성 및 브라우저 열기
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",   # refresh_token 발급을 위해 필수
        "prompt":        "consent",   # 항상 refresh_token 재발급
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("브라우저에서 Google 로그인 페이지가 열립니다...")
    print(f"자동으로 열리지 않으면 아래 URL을 직접 복사하세요:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # 2. 로컬 서버로 콜백 대기
    print("Google 로그인 후 자동으로 인증 코드를 받습니다...")
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()  # 한 번만 처리

    code = auth_code_holder["code"]
    if not code:
        print("❌ 인증 코드를 받지 못했습니다. 다시 시도해주세요.")
        sys.exit(1)

    # 3. 인증 코드 → Refresh Token 교환
    r = requests.post(TOKEN_URL, data={
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }, timeout=15)
    r.raise_for_status()
    tokens = r.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("❌ refresh_token을 받지 못했습니다.")
        print("   → Google Cloud Console에서 OAuth 동의 화면 테스트 사용자에 본인 이메일이 등록됐는지 확인하세요.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("✅ Refresh Token 발급 성공!")
    print()
    print("아래 값을 GitHub Secret에 등록하세요:")
    print()
    print(f"  Secret 이름: BLOGGER_REFRESH_TOKEN")
    print(f"  Secret 값:   {refresh_token}")
    print()
    print("그리고 아래 두 값도 GitHub Secrets에 추가하세요:")
    print(f"  GOOGLE_CLIENT_ID     = {CLIENT_ID}")
    print(f"  GOOGLE_CLIENT_SECRET = {CLIENT_SECRET}")
    print("=" * 60)


if __name__ == "__main__":
    main()
