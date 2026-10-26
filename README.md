# Market Daily 🌿

Ivory & Sage 테마의 시장 학습 프로젝트입니다.

- [대시보드](https://raygareth.github.io/market-reports/) — 명확히 표시한 가상 데이터 시연
- [개인 리포트 아카이브](https://raygareth.github.io/market-reports/reports/) — 비공개 연결 후 날짜·키워드 검색과 상세 열람
- [최신 상세 바로 열기](https://raygareth.github.io/market-reports/reports/?open=latest)

## 개인 리포트 열람

GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens에서 `RayGareth/market-reports-private`만 선택하고 **Contents: Read-only** 권한, 적절한 만료일로 발급합니다. 토큰을 아카이브의 비공개 연결란에 입력하면 날짜별 목록을 불러옵니다. 연결 후 날짜를 한 번 누르면 상세 리포트와 복습 퀴즈가 같은 화면에서 열립니다. `?open=latest`로 진입하면 연결 후 최신 발행본을 바로 엽니다.

GitHub 로그인과 이 연결은 별개입니다. 토큰은 GitHub API의 고정된 비공개 저장소 읽기 요청에만 전송합니다. 토큰·리포트는 탭 메모리에서만 사용하며 URL, localStorage, sessionStorage, 공개 저장소에 저장하지 않습니다. 새로고침·탭 종료 후에는 재연결이 필요합니다. **토큰을 채팅·PR·커밋에 남기지 마세요.**

연결 전 공개 페이지에는 실제 시황 수치·개인 리포트 목록이 없습니다. 연결 해제는 토큰·목록·열린 상세를 지웁니다. 권한 미확인 실제 데이터는 이 저장소에 복사하거나 Pages로 배포하지 않습니다. 비공개 저장소의 기존 Actions 다운로드 리더도 사용할 수 있습니다.

## 발행 구조

기존 수집·검증·생성·발행 코드는 변경하지 않습니다. 비공개 저장소가 생성하는 `reports/index.json`, `reports/daily/YYYY-MM-DD.html`, `assets/style.css`를 연결 시 읽으며 새로운 날짜를 공개 저장소에 수동 복사할 필요가 없습니다. 목록 새로고침으로 최신 발행본을 확인할 수 있습니다.

공개 저장소의 `scripts/`는 기존 코드 보존용입니다. 데이터 검증 성공은 공개 재게시 권한을 뜻하지 않습니다. 실제 데이터와 리포트를 이 저장소에 추가하지 마세요.

## 검증

브라우저 동작 검증은 Playwright와 Chromium을 사용합니다. 실제 인증 정보나 시장 데이터 없이 GitHub API 응답을 가상 자료로 대체해 실행합니다. 아래 테스트는 별도의 발행 워크플로를 추가하거나 실행하지 않습니다.

```sh
npm install --no-save playwright
npx playwright install chromium
node tests/private-reader.cjs
```

모바일 Chromium 에뮬레이션과 실제 Android 기기의 동작 확인은 구분합니다. 실제 GitHub 토큰 연결은 사용자가 발급한 토큰으로 배포 후 확인해야 합니다.
