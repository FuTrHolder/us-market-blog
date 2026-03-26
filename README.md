# 📈 US Market Blog — 자동화 세팅 가이드

매일 **한국시간 오전 8시 / 저녁 10시 30분**에 미국 증시 블로그 포스트를 자동 생성·게시합니다.

---

## 💸 비용: 완전 무료

| 구성 요소 | 서비스 | 비용 |
|----------|--------|------|
| AI 글 작성 | Google Gemini 1.5 Flash 8B | **$0** (1,000 req/day 무료) |
| 시장 데이터 | yfinance (Yahoo Finance) | **$0** |
| 경제 지표 | FRED 공개 CSV (미국 연준) | **$0** |
| 썸네일 | matplotlib + Pillow (Python) | **$0** |
| 블로그 플랫폼 | Google Blogger | **$0** |
| 자동화 실행 | GitHub Actions + cron-job.org | **$0** |
| **합계** | | **$0 / 월** |

---

## 📁 파일 구조

```
us-market-blog/
├── .github/
│   └── workflows/
│       ├── blog_post.yml        ← 메인 자동화 (cron-job.org가 트리거)
│       ├── get_token.yml        ← Refresh Token 발급 Step 1 (최초 1회)
│       └── get_token2.yml       ← Refresh Token 발급 Step 2 (최초 1회)
│
├── scripts/
│   ├── __init__.py
│   ├── morning_post.py          ← 오전 8:00 KST 포스팅 (증시 마감 리뷰)
│   └── evening_post.py          ← 오후 10:30 KST 포스팅 (프리마켓 프리뷰)
│
├── utils/
│   ├── __init__.py
│   ├── gemini_client.py         ← Gemini AI 클라이언트 + 데이터 압축
│   ├── market_data.py           ← yfinance + FRED 데이터 수집
│   ├── image_gen.py             ← matplotlib 썸네일 자동 생성
│   ├── formatting.py            ← HTML 조립 + 실적/지표 비교표
│   └── blogger.py               ← Blogger API 게시 (OAuth Refresh Token)
│
├── .env.example                 ← 로컬 테스트용 환경변수 샘플
├── .gitignore
├── README.md
└── requirements.txt
```

---

## 🔑 GitHub Secrets 등록 (5개)

**GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret**

| Secret 이름 | 설명 | 발급처 |
|------------|------|--------|
| `GEMINI_API_KEY` | Gemini AI API 키 | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `GOOGLE_CLIENT_ID` | OAuth 클라이언트 ID | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth 클라이언트 Secret | Google Cloud Console |
| `BLOGGER_REFRESH_TOKEN` | Blogger 인증 토큰 | get_token.yml 실행 결과 |
| `BLOGGER_BLOG_ID` | Blogger 블로그 숫자 ID | Blogger 대시보드 → 설정 |

---

## 🚀 최초 세팅 순서

### Step 1 — Gemini API Key 발급 (2분)

1. [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) 접속
2. Google 계정 로그인 (신용카드 불필요)
3. **Create API Key** 클릭
4. 생성된 `AIzaSy...` 키 복사
5. GitHub Secret `GEMINI_API_KEY`에 등록

---

### Step 2 — Google Cloud 설정 (5분)

**A. 프로젝트 생성 및 Blogger API 활성화**
1. [console.cloud.google.com](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 (예: `market-blog`)
3. **APIs & Services → API 라이브러리 → Blogger API v3** 검색 → 사용 설정

**B. OAuth 동의 화면 구성**
1. **APIs & Services → OAuth 동의 화면**
2. User Type: **외부** 선택 → 만들기
3. 앱 이름: `Market Blog` / 이메일: 본인 이메일 입력 → 저장
4. **범위 추가**: `https://www.googleapis.com/auth/blogger` 검색 후 추가
5. **테스트 사용자**: 본인 Gmail 주소 추가

**C. OAuth 클라이언트 ID 생성**
1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. 애플리케이션 유형: **데스크톱 앱** 선택
3. 생성 후 **Client ID**, **Client Secret** 복사
4. GitHub Secrets `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`에 각각 등록

---

### Step 3 — Blogger Refresh Token 발급 (3분)

GitHub Actions에서 직접 발급합니다. (Python 설치 불필요)

**Step 3-1: 인증 URL 생성**
1. GitHub 레포 → **Actions 탭**
2. 좌측 **"🔑 Step 1 - Blogger Refresh Token 발급"** 클릭
3. **Run workflow** → `GOOGLE_CLIENT_ID` 값 입력 → 실행
4. 완료 후 로그 클릭 → 출력된 **긴 URL 복사**
5. 브라우저 새 탭에 URL 붙여넣기 → 본인 Google 계정 로그인
6. 화면에 표시된 **인증 코드** 복사

**Step 3-2: Refresh Token 완성**
1. 좌측 **"🔑 Step 2 - Refresh Token 완성"** 클릭
2. **Run workflow** → 복사한 인증 코드 + Client ID + Client Secret 입력 → 실행

> ⚠️ Step 3-1 실행 후 **수 분 내**에 Step 3-2를 실행하세요 (인증 코드 만료)

3. 완료 후 로그에서 `BLOGGER_REFRESH_TOKEN` 값 복사
4. GitHub Secret에 등록

---

### Step 4 — Blogger 블로그 ID 확인

1. [blogger.com](https://www.blogger.com) → 대시보드
2. **설정 → 기본** → 블로그 ID 확인 (숫자만)
   또는 URL에서 확인: `https://www.blogger.com/blog/posts/`**`숫자`**
3. GitHub Secret `BLOGGER_BLOG_ID`에 숫자만 등록

---

### Step 5 — GitHub PAT 발급 (cron-job.org 연동용, 2분)

1. GitHub → 우측 상단 프로필 → **Settings**
2. 맨 아래 **Developer settings → Personal access tokens → Tokens (classic)**
3. **Generate new token (classic)**
4. Note: `cronjob-trigger` / Expiration: `No expiration`
5. 권한: **`workflow`** 체크
6. **Generate token** → `ghp_...` 토큰 복사 (안전하게 보관)

---

### Step 6 — cron-job.org 설정 (5분)

[cron-job.org](https://cron-job.org) 가입 후 Job 2개 생성

**공통 설정값:**

| 항목 | 값 |
|------|-----|
| URL | `https://api.github.com/repos/[유저명]/[레포명]/actions/workflows/blog_post.yml/dispatches` |
| Request method | `POST` |

**공통 Headers:**
```
Authorization  : Bearer ghp_여기에PAT붙여넣기
Accept         : application/vnd.github+json
Content-Type   : application/json
```

---

**Job 1 — 아침 포스팅 (KST 08:00)**

| 항목 | 값 |
|------|-----|
| Title | `Market Blog - Morning` |
| Execution schedule | Custom: `0 23 * * 0,1,2,3,4` (UTC 기준) |
| Request body | `{"ref":"main","inputs":{"post_type":"morning"}}` |

---

**Job 2 — 저녁 포스팅 (KST 22:30)**

| 항목 | 값 |
|------|-----|
| Title | `Market Blog - Evening` |
| Execution schedule | Custom: `30 13 * * 1,2,3,4,5` (UTC 기준) |
| Request body | `{"ref":"main","inputs":{"post_type":"evening"}}` |

> cron-job.org는 UTC 기준으로 입력합니다. KST = UTC+9

---

## ⏰ 자동화 스케줄

```
cron-job.org (UTC 23:00 = KST 08:00, 월~금)
  → GitHub blog_post.yml 트리거 (post_type: morning)
    → 미국 증시 마감 리뷰 포스팅

cron-job.org (UTC 13:30 = KST 22:30, 월~금)
  → GitHub blog_post.yml 트리거 (post_type: evening)
    → 프리마켓 프리뷰 포스팅
```

---

## 📊 포스팅 내용

### 오전 포스팅 — 미국 증시 마감 리뷰
- S&P 500, NASDAQ, 다우, 러셀 2000 실제 데이터
- 11개 섹터 ETF 등락률
- 상승/하락 상위 5종목 (시총 상위 41개 종목 기준)
- 국채 금리, VIX, 달러, 유가, 금
- matplotlib으로 자동 생성한 동적 썸네일 (실제 지수값 반영)
- SEO 최적화 제목, 태그, 메타 설명

### 저녁 포스팅 — 프리마켓 프리뷰
- ES/NQ/YM/RTY 선물 현황
- 아시아·유럽 시장 마감 데이터
- 오늘 실적 발표 기업 (EPS 예상 vs 실제, 매출 비교표, 과거 4분기)
- 경제 지표 (FRED 공개 데이터 — CPI, PCE, NFP 등 12개 지표)
- matplotlib으로 자동 생성한 동적 썸네일

---

## 🤖 AI 모델 (Gemini 무료 티어)

| 모델 | 역할 | 무료 한도 |
|------|------|----------|
| `gemini-1.5-flash-8b` | 기본 모델 | 15 RPM / 1,000 RPD |
| `gemini-1.5-flash` | 자동 폴백 | 15 RPM / 1,500 RPD |

기본 모델 실패 시 폴백 모델로 자동 전환됩니다.

---

## 🐛 문제 해결

**Gemini Rate Limit 오류**
- 무료 티어 한도 초과 시 자동으로 65초 간격 재시도 (최대 3회)
- 재시도 모두 실패 시 폴백 모델로 자동 전환
- 하루 2개 포스트로 일일 한도의 약 0.2%만 사용

**yfinance 데이터 없음**
- Yahoo Finance 일시적 rate limit → 다음 실행 시 정상화
- GitHub Actions 환경에서는 프록시 제한 없이 정상 동작

**Blogger 401 오류**
- Google Cloud Console에서 Blogger API v3 활성화 여부 확인
- `BLOGGER_BLOG_ID`가 숫자만 있는지 확인 (URL 아님)
- Refresh Token이 만료된 경우 `get_token.yml` → `get_token2.yml` 재실행

**cron-job.org 트리거 미작동**
- GitHub PAT의 `workflow` 권한 확인
- cron-job.org Job 실행 로그에서 HTTP 응답 코드 확인
  - `204`: 정상 트리거됨
  - `401`: PAT 오류 (Bearer 토큰 재확인)
  - `404`: URL의 유저명/레포명/파일명 오타 확인
  - `422`: Body의 JSON 형식 또는 `ref` 값 확인 (`main` 또는 `master`)

**FRED 데이터 없음**
- FRED 서버 일시 다운 시 해당 지표만 건너뜀 (포스트는 정상 게시)
- 경제 지표는 최근 2일 내 발표된 데이터만 표시
