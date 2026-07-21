# AGENT_WORKFLOW.md — 에이전트 협업 규칙

## 1. 공통 시작 문구

모든 요청에 포함:

> 작업을 시작하기 전에 README.md, SPEC.md, DATA_DICTIONARY.md, BUSINESS_RULES.md, ARCHITECTURE.md, TEST_PLAN.md, TASKS.md, DECISIONS.md를 읽어라. 기존 스키마와 규칙을 임의로 변경하지 말고, 변경이 필요하면 영향 범위와 변경안을 먼저 제시하라.

## 2. 역할

### ChatGPT
- 요구사항
- 문서
- 프롬프트
- 오류 분석
- 검토 기준
- 발표/Q&A

### Codex
- 구조
- 설정
- 데이터 생성
- 검증
- 특징
- 매칭
- 결과
- 분기점
- What-if
- pytest

### Claude
- 코드 리뷰
- 누수 검토
- Streamlit
- Plotly
- UX
- 설명 문장

한 모듈은 한 시점에 한 에이전트만 수정한다.

## 3. 작업 단위

좋음:
> `src/feature_engineering.py`와 관련 테스트만 구현.

나쁨:
> 데이터부터 UI까지 전부 구현.

## 4. 완료 보고 형식

1. 변경 파일
2. 구현 요약
3. 실행 명령
4. 테스트 결과
5. 남은 이슈
6. 문서 변경 여부
7. 다음 작업

## 5. 충돌 방지

- Codex 작업 파일을 Claude가 동시에 수정하지 않는다.
- Claude는 먼저 리뷰만 한다.
- 스키마 변경은 문서와 테스트부터.
- app.py는 UI 담당자만.
- settings.py 변경은 DECISIONS 기록.

## 6. 첫 Codex 요청

```text
프로젝트 루트의 모든 MD 문서를 읽어라.

이번 범위는 프로젝트 초기화만이다.

1. 문서 기준 폴더 구조 생성
2. Python 3.11 requirements.txt
3. config/settings.py
4. src/models.py 기본 모델
5. app.py에 제목과 데이터 미생성 안내
6. tests/test_bootstrap.py
7. README 명령 검증

합성 데이터 로직은 아직 구현하지 마라.

완료 후 변경 파일, 실행 명령, pytest 결과, 다음 권장 작업을 보고하라.
```

## 7. 합성 데이터 요청

```text
DATA_DICTIONARY.md와 BUSINESS_RULES.md를 준수하여
5,000명, 36개월 합성 데이터를 생성하라.

필수:
- 시드 42
- 5개 페르소나
- 회계식
- 월별 상태
- 미래 기반 최종 결과
- master/monthly CSV
- pytest

금지:
- final_outcome 랜덤 직접 지정
- NaN/inf
- 고객별 월 누락
```

## 8. 특징 요청

```text
1~12월만 사용해 trajectory_features.csv를 생성하라.
13~36월 값을 바꿔도 특징이 변하지 않는 누수 테스트를 작성하라.
```

## 9. 매칭 요청

```text
TrajectoryMatcher를 구현하라.

- StandardScaler
- sqrt(weight)
- 유클리드
- 자기 제외
- 상위 200
- 1/(1+distance)

인공 데이터 최근접 테스트를 작성하라.
```

## 10. 결과/분기점 요청

```text
outcome_analyzer.py와 breakpoint_analyzer.py를 구현하라.

- 결과 분포
- 최초 stress/연체
- 위험군/회피군
- 그룹 최소 20
- |SMD| >= 0.5
- 2개월 연속
- 미발견 처리
```

## 11. UI 요청

```text
계산 로직은 수정하지 말고 기존 src 모듈만 호출해 Streamlit UI를 구현하라.

필수:
- 고객 선택
- 현재 지표
- 12개월 궤적
- 유사 미래 궤적
- 결과 막대
- 분기점
- What-if
- 합성 데이터 고지

app.py에서 계산 공식을 재구현하지 마라.
```

## 12. Git

브랜치:
- feature/project-bootstrap
- feature/synthetic-data
- feature/data-validation
- feature/trajectory-features
- feature/matcher
- feature/outcome-breakpoint
- feature/whatif
- feature/streamlit-ui

커밋:
- chore: initialize project structure
- feat: add synthetic financial data generator
- test: add accounting consistency tests
- feat: build trajectory features
- feat: implement weighted trajectory matcher
- feat: add future outcome aggregation
- feat: detect trajectory breakpoints
- feat: add what-if simulator
- ui: add Streamlit dashboard

## 13. 단계 종료

- 테스트 통과
- 산출물 생성
- TASKS 업데이트
- 결정 변경 기록
- 실행 명령 기록
- Git 커밋

## 14. 데모 긴급 복구

1. AI API 끄기
2. 고객 고정
3. 사전 JSON 사용
4. 사전 생성 그래프 사용
5. 최종 백업 영상 사용
