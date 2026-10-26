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

새 `publish-study.yml`은 같은 시간대에 공개 학습판을 생성합니다. 외부 시세 API나 비공개 저장소에 접근하지 않고, 기본 라이브러리만 사용합니다. 현재는 직접 작성한 네 가지 학습 개념을 순환합니다. 평일 학습판이므로 국내 휴장일에도 생성할 수 있으며 거래일 리포트로 표시하지 않습니다. 재실행해도 같은 날짜의 원고/상세는 보존합니다. 주말 수동 실행은 새 날짜를 생성하지 않습니다. GitHub Actions 지연 가능성이 있습니다.

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
