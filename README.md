# Market Daily 🌿

Ivory & Sage 테마의 국내·미국 시장 리서치 대시보드.

- [웹사이트](https://raygareth.github.io/market-reports/)
- [리포트 아카이브](https://raygareth.github.io/market-reports/reports/)

## 공통 리포트 템플릿

앞으로 발행할 리포트는 `content/daily/YYYY-MM-DD.json` 원고를 이용해 `scripts/build_reports.py`가 HTML로 생성합니다.

- 8개 고정 섹션, Sage 구분선, 객관식 선택 → 정답 확인 → 해설 → 다시 풀기 기능
- 기존 CSS `assets/style.css` 및 퀴즈 엔진 `assets/quiz.js` 공통 사용
- `reports/index.json`에서 아카이브 목록 자동 생성
- `content/daily/2026-10-13.json`은 **발행되지 않는 예시 초안**입니다.

### 리포트 발행 절차

1. 해당 거래일의 종가·거래일·수급·뉴스 출처를 확인합니다.
2. `content/daily/YYYY-MM-DD.json`에 검증한 원고를 채웁니다.
3. `publish: true` 및 `verification: "verified"`를 설정합니다.
4. GitHub 저장소 → **Actions** → **Build Market Daily Reports** → **Run workflow**를 실행합니다.
5. GitHub Pages 자동 배포가 완료되면 HTML과 아카이브가 공개됩니다.

로컬에서 테스트할 때는 `python3 scripts/build_reports.py`를 실행할 수 있습니다.

> 중요: GitHub Actions 발행 공통 생성 워크플로는 **수동 실행**이며, 별도 오후 5시 예약 발행 워크플로가 있습니다. 자동 자료 수집과 예약 실행은 추가됐지만 첫 실제 성공 여부를 확인해야 합니다. 뉴스 분석은 수동 보강 대상입니다. 검증되지 않은 숫자를 임의로 채우지 않습니다.

기존 2026-10-12 리포트는 오후 작성판으로 국내 **10월 8일 확정 종가**를 사용하고 있습니다. 국내 **10월 12일 마감 종가로 갱신한 버전은 아직 아닙니다**.

## 거래일 오후 5시(KST) 자동 발행 — 계정 없는 교차 검증

- 자동 실행 시간: 월~금 **17:00 KST (08:00 UTC)** — GitHub Actions 지연 가능
- 1차 데이터: Yahoo Finance `^KS11` (KOSPI), `^KQ11` (KOSDAQ)의 일별 OHLC
- 2차 데이터: 네이버 금융 일별 지수 가격 공개 엔드포인트 (`KOSPI`, `KOSDAQ`)
- 검증: **당일 날짜가 두 출처에 모두 있어야 하고**, 지수 종가 차이가 0.05% 또는 최소 0.5포인트 이내여야 함
- 이외 Yahoo OHLC의 숫자 유효성, 고가/저가 범위, 직전 종가, 비정상 변동률 검사
- 어느 한쪽이 차단·지연되거나 수치가 다르면 **발행 중단**, 기존 리포트 유지
- 검증 성공: 8개 섹션과 선택형 퀴즈로 HTML 생성 → 아카이브·대시보드 갱신
- 미국 지수·뉴스·외국인/기관 수급은 현재 자동 검증 대상이 아님
- KRX 계정·GitHub Secrets·비밀번호 **필요 없음**

**주의:** Yahoo Finance와 네이버 금융 모두 비공식 공개 데이터 접근 방식입니다. 서비스 정책, 지연, 종가 정의 및 데이터 변경에 따라 실패할 수 있고, 두 서비스 간 일치가 공식 거래소 보증을 의미하지는 않습니다. 이 도구는 발행 오류 예방을 위한 데이터 품질 장치입니다.

[GitHub Actions 실행 기록](https://github.com/RayGareth/market-reports/actions)에서 오늘 오후 5시 작업 완료 여부를 확인하세요. 첫 자동 실행은 아직 확인되지 않았으며, 작업이 정상 실행되어야 10월 12일 국내 종가가 기존 오후 브리핑을 대체합니다.
