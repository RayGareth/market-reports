# Market Daily 🌿

개인 경제 공부와 시황 기록을 위한 간편한 Daily Report입니다. 기존 Ivory & Sage 디자인을 사용합니다.

- [대시보드](https://raygareth.github.io/market-reports/)
- [날짜별 아카이브](https://raygareth.github.io/market-reports/reports/)
- [최신 리포트](https://raygareth.github.io/market-reports/reports/latest.html)

로그인·토큰·다운로드 없이 날짜를 클릭해 공개 학습판을 바로 읽습니다. 최신 링크는 JavaScript가 없어도 작동하는 실제 HTML 파일입니다.

## 네 개의 SECTION

1. **오늘의 시장 한눈에 보기**: 국내외 지수별 확정 종가·등락률·기준일, 코스피·코스닥 종목 분포. 검증과 공개 게시 근거가 모두 갖춰진 자료만 표시합니다.
2. **오늘의 주요 이슈와 시장 흐름**: 확인된 사실과 작성자의 해석을 구분하고 원문 출처를 연결합니다.
3. **오늘의 경제 공부**: 직접 작성한 개념 한 가지와 쉬운 일상 연결 설명. 참고 자료는 Investor.gov의 Introduction to Investing입니다.
4. **오늘의 복습 퀴즈**: 객관식 선택·정답 확인·해설·다시 풀기.

상대 강도 분석·투자 시나리오·액션 플랜은 새 공개 템플릿에 포함하지 않습니다.

현재 실제 종가·종목 분포·당일 뉴스 데이터는 **미연결**입니다. 빈 항목을 가상의 시세나 추정 뉴스로 채우지 않습니다. 기존 날짜에 새로 작성한 학습판은 원본 상세 리포트의 재게시나 과거 시황 재구성이 아닙니다.

## 공개 게시와 보존

- `content/daily/`의 공개 학습 원고 → `scripts/build_public_reports.py` → `reports/daily/`, `reports/index.json`, `reports/latest.html`, `data/public-market.json`.
- 수치와 뉴스 입력에는 `verified: true`, `publication.status: approved_public`, 공개 근거 URL(`publication.evidence`), 출처(`source`)가 필요합니다. 지수·분포에는 개별 기준일(`asOf`)도 필요합니다. 미확인 입력은 HTML 생성 전에 거부합니다. 이 표시는 실제 권한 확인을 대신하지 않으며 편집자가 근거를 확인해야 합니다.
- 미확인 원자료는 공개 원고·커밋·PR에 넣지 마세요. 렌더러가 숨겨도 공개 저장소 파일은 공개됩니다.
- 기존 날짜 HTML을 자동으로 덮어쓰지 않습니다. 기존 비공개 원고·리포트·Actions 기록은 이동하거나 삭제하지 않습니다.
- 공개 아카이브의 학습판은 원본에서 날짜만 참고하고 수치·헤드라인·본문·퀴즈를 가져오지 않고 새로 작성했습니다.

## 자동 발행과 단계적 전환

기존 두 저장소의 워크플로 파일과 일정은 변경하지 않습니다. 공개 저장소의 기존 워크플로는 비활성 안내용이고 실제 발행은 비공개 저장소의 평일 18:00·18:15·18:30 KST 작업입니다.

새 `publish-study.yml`은 같은 시간대에 공개 학습판을 생성합니다. 비공개 저장소에 접근하지 않으며, STEP 2에서는 공개 승인된 제공자가 설정된 경우에만 시세 API에 접근합니다. 현재는 직접 작성한 네 가지 학습 개념을 순환합니다. 평일 학습판이므로 국내 휴장일에도 생성할 수 있으며 거래일 리포트로 표시하지 않습니다. 재실행해도 같은 날짜의 원고/상세는 보존합니다. 주말 수동 실행은 새 날짜를 생성하지 않습니다. GitHub Actions 지연 가능성이 있습니다.

이 PR을 기본 브랜치에 병합한 후 예약 발행과 Pages 배포가 실제로 성공하는지 확인해야 합니다. 현재 운영 성공을 보장한 상태는 아닙니다.

비공개 저장소는 기록 보존용으로 유지합니다. 공개 학습판의 연속 발행을 확인한 뒤 기존 비공개 예약 중단을 검토합니다. **이번 PR은 비공개 예약을 중단하지 않습니다.** 실제 지표와 뉴스 연결, 비공개 운영 중단은 남은 작업입니다.

## 검증

```sh
python -m unittest discover -s tests -p 'test_*.py'
python scripts/build_public_reports.py --date 2026-10-26
# Playwright/Chromium을 설치한 환경에서:
node tests/public-reader.cjs
```

모바일 Chromium 화면 검증과 실제 Android 기기 확인은 구분합니다. PR 병합·배포·실제 예약 발행은 별도로 확인해야 합니다.

## PR #1 최종 점검 보완

공개/비공개 예약은 별도 저장소를 쓰므로 직접 파일 충돌은 없습니다. 전환 기간 동안 두 작업이 같은 시간대에 실행되는 것은 유지합니다. 공개 작업은 `market-daily-public` 동시 실행 그룹으로 직렬화하고 main에서만 실행합니다.

발행 직전에 최신 main으로 임시 git worktree를 만들고, push가 경쟁 수정으로 거부되면 최대 세 번 최신 main에서 다시 생성합니다. 생성 파일을 rebase하거나 강제 push하지 않으며 원래 체크아웃도 변경하지 않습니다. 기존 날짜 원고/HTML과 기존 아카이브 항목을 보존합니다.

GitHub의 GITHUB_TOKEN으로 만든 커밋은 브랜치 방식 Pages 빌드를 자동으로 시작하지 않습니다. 예약 발행 후 실제 배포를 위해 승인 이후 Pages Source를 GitHub Actions로 설정하고 repository variable `MARKET_PAGES_DEPLOY=true`를 지정하면 준비된 Pages 배포 단계를 사용합니다. 이 전환 전에는 커밋 성공과 사이트 갱신 성공을 구분해야 합니다. 이번 작업은 설정 변경·병합·배포를 실행하지 않습니다.

## STEP 2: 확정 종가 연결 (별도 PR, 활성화 대기)

`market_close.py`는 다음 경로를 구현합니다.

1. 거래소 달력의 실제 마감 시각에 30분 안전 간격을 더해 지표별 마지막 마감 세션과 직전 세션을 선택합니다. 한국은 XKRX, S&P 500은 XNYS, NASDAQ Composite는 XNAS를 사용합니다. 한국·미국 휴장, 미국 서머타임·조기 폐장을 반영합니다. 달력 검토 기한은 현재 2026-12-31이며 이후 자동 추측하지 않고 안내를 표시합니다. 임시 휴장 등 달력 변경은 유지보수가 필요합니다.
2. 검토된 출처 설정에서 해당 지수의 공개 표시·재배포·등락률 계산 허용 범위와 유효 기간을 확인합니다. 공개 승인 출처가 없으면 **어떤 원자료 API도 호출하지 않습니다**.
3. 허용된 1차 출처와 다른 제공 계열의 비교 출처에서 최근/직전 세션 종가를 읽습니다. 두 시점 모두 기존 `collect_close.cross_check`의 허용 차이(0.05%, 최소 0.5포인트)를 재사용합니다. 등락률은 직전 거래일 대비 계산하고 제공된 등락률이 있으면 이를 대조합니다. 두 제공자의 계산 등락률 차이는 0.02%p 이내여야 합니다. 일간 변동 폭 절댓값 25% 초과, 중복 날짜, 0·음수·NaN, 세션 누락은 보류합니다.
4. 공개 승인된 1차 종가와 계산 등락률만 JSON·SECTION 01에 넣습니다. 비교 출처의 원자료, 키, 오류 응답·원문 메시지는 파일/로그/PR로 내보내지 않습니다. 출처명·기준일·직전 기준일·교차 검증 링크를 함께 표시합니다.
5. 동일 날짜에 늦게 도착한 자료나 오류 상태가 변경되면 `YYYY-MM-DD-r001.html` 형태의 수정판을 만듭니다. 최초 발행본과 이전 수정판은 유지하고 아카이브/최신 링크만 갱신합니다. 값과 상태가 같으면 수정판을 추가하지 않습니다. 기존 8 SECTION 비공개 기록은 건드리지 않습니다.

### 어댑터와 현재 상태

| 어댑터 | 지수 | 현재 활성화 | 비고 |
| --- | --- | --- | --- |
| Yahoo | 국내·미국 4개 | 꺼짐 | 기존 코드 보존, 일별 비조정 OHLC 방식 재사용 |
| 네이버 | KOSPI·KOSDAQ | 꺼짐 | 기존 조회/교차 검증 코드 보존 |
| 금융위원회 V2 | KOSPI·KOSDAQ | 꺼짐 | `FSC_API_KEY` 필요. 다음 영업일 오후 갱신 안내가 있어 당일 18시 자료가 없으면 보류 |
| FRED | SP500·NASDAQCOM | 꺼짐 | 관측일별 종가 CSV 어댑터. 공개 재게시 승인으로 간주하지 않음 |

**현재 공개 승인된 출처는 없으며 실제 수치 공개 연결은 아직 활성화하지 않았습니다.** 금융위원회 안내에는 제3자 제공/재배포 제한이 있고, FRED의 두 지수도 제3자 저작권 및 사전 승인 안내가 있습니다. 무료 조회 여부를 공개 허용으로 처리하지 않습니다.

권한 확인 후 `config/market-sources.json`의 지수 범위·공개 근거 링크·검토일·유효 기한과 표시/재배포/가공 허용 항목을 검토하여 별도 변경으로 활성화합니다. 비교 전용 출처는 수집 허용 여부를 별도로 확인합니다. API 키는 GitHub Secret에만 넣으며 코드/채팅에 넣지 않습니다. FSC 키는 미설정 상태로도 안전하게 안내 처리됩니다.

공식 확인 경로:
- 금융위원회: https://www.data.go.kr/data/15094807/openapi.do
- S&P 500: https://fred.stlouisfed.org/series/SP500
- NASDAQ Composite: https://fred.stlouisfed.org/series/NASDAQCOM
- FRED 이용 안내: https://fred.stlouisfed.org/legal/
- 거래소 달력: https://github.com/gerrymanoim/exchange_calendars

### 실행과 검증

```sh
pip install -r requirements-public.txt
python -m unittest discover -s tests -p 'test_*.py'
python scripts/build_public_reports.py --market
node tests/public-reader.cjs
node tests/market-ui.cjs
```

새 별도 스케줄을 추가하지 않고 PR #1의 기존 공개 발행 작업이 `--market` 경로를 호출합니다. 따라서 STEP 2를 적용한다고 두 번째 공개 발행 작업이 생기지 않습니다. 승인된 제공자·키·실제 API 응답의 최종 연결, Pages 설정/예약 실행, 실제 Android 기기 확인은 배포 전후에 별도로 확인해야 합니다. 합성 입력 테스트의 수치는 실제 시장 가격이 아닙니다.
