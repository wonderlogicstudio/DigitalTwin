# UI Visual QA

## 1. 검사 환경

- Python 버전: 3.10.9
- Streamlit 버전: 1.57.0
- 검사 일시: 2026-07-19 21:57:01 +09:00
- 화면 크기 기준: 1366x768, 1920x1080
- 검사 방식: Streamlit AppTest, Plotly Figure JSON 검증, 제한시간 Streamlit HTTP 헬스체크, 계산 결과 직접 비교
- 실제 픽셀 스크린샷: 미수행. 현재 환경에 Playwright와 npx가 설치되어 있지 않아 브라우저 viewport 스크린샷을 자동 수집하지 못했다.
- 검사 고객:
  - 메인 고객: C002608
  - 안정 비교 고객: C002082
  - 고위험 고객: C002672
- 검사 모드:
  - 일반 모드
  - 발표 모드

## 2. Critical 문제

발견된 Critical 문제 없음.

## 3. High 문제

### UI-H01

- 문제 ID: UI-H01
- 심각도: High
- 화면: 일반 모드, 위험 분기점 그래프
- 고객: 메인 고객 C002608
- 모드: 일반 모드
- 현재 문제: 사전 계산 캐시의 `breakpoint_comparison`이 빈 DataFrame일 때 분기점 그래프가 Figure로 표시되지 않고 "차트를 표시하지 못해 요약 표로 대체합니다." 경고가 노출됐다.
- 사용자 영향: 3분 시연 핵심 장면인 위험 분기점 설명이 그래프 대신 fallback 경고처럼 보여 발표 신뢰도를 떨어뜨린다.
- 관련 파일: `src/visualizations.py`, `tests/test_visualizations.py`
- 수정 내용: `comparison_df`가 비어 있거나 필수 컬럼이 없으면 새 계산을 수행하지 않고, 이미 존재하는 `breakpoint_result`의 분기점 월과 두 그룹 평균값으로 1포인트 비교 Figure를 생성하도록 했다.
- 수정 결과: 일반 모드 메인 고객 AppTest 재확인에서 Streamlit warning 요소 0건. 분기점 Figure JSON 직렬화도 통과했다.

## 4. Medium 문제

### UI-M01

- 문제 ID: UI-M01
- 심각도: Medium
- 화면: 전체 화면
- 고객: 메인, 안정 비교, 고위험
- 모드: 일반 모드, 발표 모드
- 현재 문제: 이 환경에서는 1366x768과 1920x1080의 실제 브라우저 스크린샷 검증을 수행하지 못했다.
- 사용자 영향: 잘린 글자, 겹치는 범례, 실제 발표 빔프로젝터 화면의 밀도 문제는 사람이 마지막으로 확인해야 한다.
- 관련 파일: `assets/styles.css`, `app.py`, `src/visualizations.py`
- 수정 내용: 이번 단계에서는 코드 수정 없음.
- 수정 결과: 자동 텍스트/JSON/HTTP 확인은 통과했지만 실제 픽셀 확인은 발표 전 수동 점검 항목으로 남긴다.

### UI-M02

- 문제 ID: UI-M02
- 심각도: Medium
- 화면: 발표 모드 사이드바
- 고객: 안정 비교 고객, 고위험 고객
- 모드: 발표 모드
- 현재 문제: 발표 모드는 기존 요구사항대로 메인 데모 고객을 자동 선택하므로 안정 비교 고객과 고위험 고객을 발표 모드에서 직접 선택할 수 없다.
- 사용자 영향: 발표 모드의 3분 시연은 메인 고객 중심으로 안정적이지만, 발표 중 다른 고객을 보여주려면 일반 모드로 전환해야 한다.
- 관련 파일: `app.py`, `src/presentation.py`
- 수정 내용: 새 기능 추가 범위를 벗어나 수정하지 않았다.
- 수정 결과: 일반 모드에서는 세 데모 고객 선택이 가능하고, 발표 모드는 메인 고객 전용으로 유지된다.

### UI-M03

- 문제 ID: UI-M03
- 심각도: Medium
- 화면: Streamlit 실행 콘솔
- 고객: 전체
- 모드: 일반 모드, 발표 모드
- 현재 문제: Streamlit 1.57.0에서 `use_container_width` 폐기 예정 콘솔 경고가 반복된다.
- 사용자 영향: 사용자 화면에는 보이지 않지만 실행 로그가 지저분해지고 향후 Streamlit 업그레이드 때 호환성 이슈가 될 수 있다.
- 관련 파일: `app.py`
- 수정 내용: 데모 화면 안정성에 직접 영향을 주는 Critical/High 문제가 아니라 이번 단계에서는 수정하지 않았다.
- 수정 결과: pytest와 Streamlit 헬스체크는 통과했다.

### UI-M04

- 문제 ID: UI-M04
- 심각도: Medium
- 화면: 발표 모드 전체 흐름
- 고객: 메인 고객 C002608
- 모드: 발표 모드
- 현재 문제: 4개 장면은 한 페이지에 순서대로 표시되지만, 그래프 8개 수준의 정보량 때문에 1366x768에서 스크롤은 여전히 필요했다.
- 사용자 영향: 3분 발표 중 스크롤 위치를 놓치면 설명 흐름이 느려질 수 있다.
- 관련 파일: `app.py`, `assets/styles.css`
- 수정 내용: 발표 모드의 4개 세로 장면과 하단 고지를 5개 상단 탭으로 분리했다.
- 수정 결과: 현재 상태, 유사 경로, 위험 분기점, 대응 시나리오, 분석 요약을 스크롤 대신 탭으로 전환한다. 탭 내부의 세부 표·그래프 스크롤은 남아 있다.

## 5. Low 문제

### UI-L01

- 문제 ID: UI-L01
- 심각도: Low
- 화면: 개발 환경
- 고객: 전체
- 모드: 전체
- 현재 문제: `git status`가 "not a git repository"로 실패한다. 작업 폴더에 `.git` 디렉터리는 보이지만 저장소로 인식되지 않는다.
- 사용자 영향: 변경 파일 추적을 Git diff로 확인하기 어렵다.
- 관련 파일: `.git`
- 수정 내용: 앱 코드와 무관하므로 수정하지 않았다.
- 수정 결과: 변경 파일은 파일명과 테스트 결과 기준으로 보고한다.

### UI-L02

- 문제 ID: UI-L02
- 심각도: Low
- 화면: Streamlit toolbar
- 고객: 전체
- 모드: 일반 모드, 발표 모드
- 현재 문제: Streamlit 기본 toolbar, Deploy, Main menu 노출 여부는 실제 브라우저에서 최종 확인이 필요하다.
- 사용자 영향: 발표 화면이 개발 도구처럼 보일 수 있다.
- 관련 파일: `.streamlit/config.toml`, `assets/styles.css`
- 수정 내용: 이번 단계에서는 수정하지 않았다.
- 수정 결과: 발표 전 브라우저에서 확인할 항목으로 남긴다.

## 6. 수정한 문제

- UI-H01: 일반 모드 메인 고객 분기점 그래프가 캐시의 빈 비교 DataFrame 때문에 fallback warning으로 표시되던 문제를 수정했다.

## 7. 미수정 문제

- UI-M01: 실제 1366x768, 1920x1080 브라우저 픽셀 스크린샷 미수행.
- UI-M02: 해결. 발표 모드는 메인 고객으로 시작하지만 안정 비교 고객과 고위험 고객도 같은 탭 구조로 선택할 수 있다.
- UI-M03: `use_container_width` 콘솔 경고.
- UI-M04: 1366x768 발표 화면의 스크롤 길이.
- UI-L01: Git 저장소 인식 불가.
- UI-L02: Streamlit toolbar 실제 브라우저 노출 여부.

## 8. 사람이 발표 전에 확인할 항목

1. 1366x768 발표 노트북 화면에서 Hero, KPI 5개, 장면 1 그래프가 잘리지 않는지 확인한다.
2. 1920x1080 화면에서 그래프 범례가 제목이나 주석과 겹치지 않는지 확인한다.
3. 발표 모드에서 Streamlit toolbar와 브라우저 UI가 시연 화면을 방해하지 않는지 확인한다.
4. 일반 모드에서 안정 비교 고객과 고위험 고객을 선택하고 분석 버튼이 정상 동작하는지 브라우저로 확인한다.
5. 빔프로젝터 환경에서 글자 크기와 색상 대비가 충분한지 확인한다.

## 9. 최종 시각 품질 판정

VISUAL_READY_WITH_WARNINGS

## 12. 2026-07-21 Presentation Tabs Update

- UI-M02: 발표 모드가 메인 고객으로 시작하되 안정 비교 고객과 고위험 고객도 선택할 수 있도록 표시 선택 상태를 보완했다. 메인 고객의 사전 계산 fallback 우선순위는 유지했다.
- UI-M04: 세로 4개 장면과 하단 고지를 5개 상단 탭으로 분리해 전체 장면을 보기 위한 페이지 스크롤을 제거했다. 탭 내부의 표와 그래프 스크롤은 남아 있다.
- 검증: 한국어/영어 및 메인·안정 비교·고위험 고객 발표 모드에서 탭 5개, 차트 8개, 예외 0건을 AppTest로 확인했다.
- 제한: 1366×768과 1920×1080 실제 브라우저 픽셀 스크린샷은 Playwright 부재로 발표 전 수동 점검 항목으로 남긴다.

판정 근거:

- Critical 문제는 발견되지 않았다.
- High 문제 1건은 수정했고 관련 테스트와 AppTest 재확인을 통과했다.
- 금액은 `만원`/`억원`, 비율은 `%`, 기간은 `개월 차` 중심으로 표시된다.
- Plotly Figure JSON 직렬화, 축 단위, hover 내부 변수명 미노출, 결과 분포 합계, What-if 최적 시나리오 강조 검증이 통과했다.
- 다만 실제 브라우저 viewport 스크린샷 검증이 불가했고, Streamlit 콘솔 경고와 발표 전 수동 확인 항목이 남아 있다.

## 10. 레이아웃 겹침 재점검

- 점검 일시: 2026-07-19 23:30 +09:00
- 추가 판정: LAYOUT_READY_WITH_WARNINGS
- 수정 파일: `src/visualizations.py`, `src/i18n.py`, `assets/styles.css`, `app.py`, `scripts/export_demo_charts.py`, `tests/test_ui_layout.py`, `tests/test_visualizations.py`, `tests/test_i18n.py`
- 수정 내용: 영어/한국어 차트 제목을 짧게 만들고, Plotly title/legend/annotation top margin을 공통 헬퍼에서 동적으로 확보했다.
- 수정 내용: KPI 카드의 최소 높이, wrap, 숫자 크기, 상태 배지 줄바꿈 규칙을 보강했다.
- 수정 내용: `use_container_width` 호출을 `width="stretch"`로 정리해 Streamlit 1.57 경고를 제거했다.
- 확인 결과: 한국어/영어, 일반/발표 모드, 메인/안정 비교/고위험 고객 AppTest 예외 0건.
- 확인 결과: `pytest -q`는 208개 테스트 전체 통과, `python scripts/check_demo_readiness.py`는 READY_WITH_WARNINGS.
- 남은 제한: Playwright 미설치로 실제 1366x768 및 1920x1080 픽셀 스크린샷은 자동 수집하지 못했다.

## 11. 추가 레이아웃 보정

- 점검 일시: 2026-07-19 23:50 +09:00
- 수정 파일: `src/visualizations.py`, `src/i18n.py`, `assets/styles.css`, `tests/test_ui_layout.py`, `tests/test_visualizations.py`, `tests/test_i18n.py`
- 수정 내용: 단일 지표 그래프의 중복 범례와 현재 시점 annotation을 줄이고, 현재값 마커 텍스트를 값만 표시하도록 축약했다.
- 수정 내용: 영어 유사 고객 궤적 범례를 짧은 라벨로 바꾸고, 범례를 plot 영역 바깥 위쪽 공간에 고정했다.
- 수정 내용: 결과 분포 제목과 저축률/DSR 제목을 짧게 바꾸고, Plotly title y와 top margin을 보수적으로 조정했다.
- 수정 내용: Streamlit Plotly chart 컨테이너의 위쪽 padding을 늘려 제목이 카드 테두리에 붙어 보이지 않게 했다.
- 확인 결과: `pytest -q` 209개 통과, `python scripts/check_demo_readiness.py`는 READY_WITH_WARNINGS, 제한 시간 Streamlit 헬스체크 통과.
