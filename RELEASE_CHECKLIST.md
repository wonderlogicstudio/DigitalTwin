# Release Checklist

## 검사 일시

- 2026-07-18 10:53:49 +09:00

## Python 버전

- `python --version`: Python 3.10.9
- 프로젝트 목표 버전: Python 3.11
- 판정: 경고. 현재 로컬 기본 Python은 3.10.9이며, readiness도 같은 경고를 표시한다.

## 패키지 설치 결과

- `python scripts/check_demo_readiness.py`: required packages import successfully
- `python -m pip check`: 전역 환경에 이 프로젝트와 직접 관련 없는 패키지 충돌 경고가 있음
  - `imgaug`, `paddleocr`, `pdf2docx`의 OpenCV 계열 요구사항 경고
  - `google-auth`와 `cachetools` 버전 경고
  - `paddlex`와 `PyYAML` 버전 경고
  - `torchaudio`, `torchvision`과 `torch` 빌드 태그 경고
- 판정: 데모 차단 아님. 프로젝트 필수 직접 의존성 import는 통과했다.

## 실행 명령 결과

1. `python scripts/check_demo_readiness.py`
   - 종료 코드: 0
   - 상태: READY_WITH_WARNINGS

2. `pytest -q`
   - 종료 코드: 0
   - 결과: 115 passed in 156.60s

3. `python scripts/run_pipeline.py`
   - 종료 코드: 0
   - 실행 시간: 2.66초
   - 기본 산출물 재사용 모드로 완료

4. `python scripts/prepare_demo.py`
   - 종료 코드: 0
   - 실행 시간: 25.64초
   - `relaxation_applied`: true

5. `python scripts/export_demo_charts.py`
   - 종료 코드: 0
   - 실행 시간: 1.56초
   - HTML 차트 export 완료

6. Streamlit 기동 확인
   - 명령: `python scripts/start_streamlit.py --port 8504 --timeout 30`
   - 결과: `http://localhost:8504` HTTP 200

## 테스트 수와 결과

- 전체 테스트: 115개
- 실패: 0개
- 결과: PASS

## 파이프라인 실행 시간

- `python scripts/run_pipeline.py`: 2.66초
- 단계별 시간:
  - synthetic_data_generation: 0.516초
  - data_validation: 0.810초
  - feature_generation: 0.013초
  - matcher_preparation: 0.003초
  - demo_candidate_search: 0.004초
  - main_demo_analysis: 0.001초
  - result_aggregation: 0.015초
  - breakpoint_analysis: 0.171초
  - whatif_simulation: 0.020초
  - demo_outputs: 1.105초
  - chart_export: 0.000초

## 메인 고객 ID

- `C002608`
- 메인 고객 고정 확인: PASS

## 핵심 데모 수치

- 전체 고객 수: 5,000명
- 월별 데이터 행 수: 180,000행
- 특징 행 수: 5,000행
- 유사 고객 수: 200명
- 결과 분포:
  - healthy: 87명, 43.5%
  - recovered: 41명, 20.5%
  - stress: 66명, 33.0%
  - delinquent: 6명, 3.0%
- 결과 비율 합계: 100.0%
- 위험군 비율: 36.0%
- 분기점:
  - status: found
  - breakpoint_month: 13
  - months_from_current: 1
  - primary_factor: cash_balance_ratio
  - risk_group_mean: 3.4329698218288542
  - avoidance_group_mean: 5.494472234166576
  - standardized_difference: -1.2672623851125968
  - persistence_months: 24
- What-if 시나리오 수: 4개
- 최선 What-if:
  - scenario_name: debt_payment_cut_20
  - improvement_vs_baseline: 8,994,667.2원
  - baseline ending_cash_balance: 50,622,709.84원

## 최종 점검 항목

- 모든 테스트 통과: PASS
- 데이터 누수 없음: PASS. 특징 생성은 `month <= 12` 필터를 강제하며 관련 테스트가 통과했다.
- 메인 고객 고정: PASS. `C002608`
- 유사 고객 200명: PASS
- 결과 비율 합계 100%: PASS
- 분기점 정상: PASS. `found`, month 13
- What-if 4개: PASS
- 고객용 설명: PASS. 템플릿 설명 생성 및 합성 데이터 고지 확인
- 직원용 설명: PASS. 템플릿 설명 생성 및 공식 신용평가/금융상품 판매 판단 아님 고지 확인
- 합성 데이터 고지: PASS
- fallback 정상: PASS. 사전 계산 demo cache 파일 존재 및 core smoke 통과
- README 명령 정상: PASS. 주요 실행 명령과 실제 스크립트 파일명이 일치하고 릴리스 명령이 성공했다.
- 발표 화면 오류 없음: PASS. Streamlit HTTP 200 확인

## readiness 상태

- 최종 상태: READY_WITH_WARNINGS
- READY:
  - packages
  - required_md
  - raw_data
  - processed_data
  - demo_json
  - precomputed_cache
  - core_smoke
- READY_WITH_WARNINGS:
  - python_version: 3.10.9; project target is Python 3.11
  - port_8501: port 8501 is already in use
  - api_key: OPENAI_API_KEY is not set; template fallback will be used

## 알려진 경고

- 현재 로컬 기본 Python은 3.10.9로, 문서 목표인 Python 3.11과 다르다.
- 8501 포트가 이미 사용 중이다. 발표 시 `DEMO_PORT=8502` 또는 Streamlit `--server.port` 옵션을 사용한다.
- `OPENAI_API_KEY`가 없어 템플릿 설명 fallback을 사용한다. MVP 요구사항상 차단 요소는 아니다.
- 전역 Python 환경의 `pip check`에 이 프로젝트와 직접 관련 없는 패키지 충돌 경고가 있다.
- `prepare_demo.py`에서 메인 고객 조건 중 fixed expense ratio 기준 완화가 적용되었다. 선택 사유에 완화 내용이 기록되어 있다.

## 최종 판정

- READY_WITH_WARNINGS

차단 실패는 없다. 위 경고를 발표 전에 확인하면 현재 상태로 해커톤 데모 진행 가능하다.
