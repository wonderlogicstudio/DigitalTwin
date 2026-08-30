# Financial Path Twin

> Synthetic universe v2: the project keeps 5,000 synthetic customers and the
> existing Financial Path Twin method, while using a broader deterministic set
> of financial-flow archetypes. See `SYNTHETIC_UNIVERSE_V2_DESIGN.md` for the
> scope, evidence, and regeneration contract. The archetypes are not real CRM,
> occupation, AUM, wealth, or customer classifications.

## 1. 프로젝트 소개

Financial Path Twin은 고객의 최근 12개월 재무 궤적과 유사한 합성 고객 집단을 찾아, 그 집단이 이후 24개월 동안 어떤 결과를 보였는지 보여주는 해커톤 PoC입니다.

실제 개인 정보, 실제 신용평가 모델, 금융상품 추천, 외부 LLM API 없이도 전체 데모가 동작하도록 구성되어 있습니다.

## 2. 한 줄 컨셉

당신의 미래를 예측하지 않습니다. 같은 길을 먼저 걸은 트윈들의 결과를 보여줍니다.

## 3. 문제 정의

금융 상담 현장에서는 고객의 현재 상태만으로는 앞으로 어떤 재무 압박이 올 수 있는지 설명하기 어렵습니다. 이 프로젝트는 복잡한 예측 모델 대신, 비슷한 재무 흐름을 먼저 경험한 합성 고객 집단의 실제 후속 결과를 보여주어 상담과 자기 점검을 돕습니다.

## 4. 주요 기능

- 5,000명 합성 고객과 고객별 36개월 월별 재무 데이터 생성
- 필수 컬럼, 회계식, 결측, 중복, 분포 검증
- 1~12개월 관측 구간만 사용하는 재무 궤적 특징 생성
- StandardScaler와 가중 유클리드 거리 기반 유사 고객 200명 매칭
- 유사 고객의 13~36개월 결과 분포 집계
- 위험 경로 고객과 위험 회피 고객의 월별 차이 기반 위험 분기점 분석
- 24개월 대응 시나리오 현금흐름 계산
- 데모 고객 자동 선정
- Plotly 시각화와 Streamlit 데모 UI
- LLM 없이 동작하는 템플릿 설명
- live 계산 실패 시 사전 계산 산출물을 사용하는 데모 fallback

## 5. 기술 구조

```text
Data Generator
  -> Validator
  -> Feature Engineering
  -> Matcher
  -> Demo Selector
  -> 이후 결과 요약
  -> Breakpoint Analyzer
  -> 대응 시나리오 계산
  -> Demo Cache / Backup
  -> Streamlit UI
```

주요 기술:

- Python 3.11
- pandas
- numpy
- scikit-learn
- Plotly
- Streamlit
- pytest
- pydantic

## 6. 폴더 구조

```text
.
├── app.py
├── config/
│   └── settings.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── demo/
├── reports/
│   ├── charts/
│   └── demo_backup/
├── scripts/
│   ├── generate_data.py
│   ├── validate_data.py
│   ├── build_features.py
│   ├── prepare_demo.py
│   ├── run_pipeline.py
│   └── check_demo_readiness.py
├── src/
├── tests/
├── requirements.txt
├── run_demo.bat
└── run_demo.sh
```

## 7. 설치 방법

### Windows 빠른 시작

일반 사용자는 프로젝트 루트에서 아래 배치 파일을 순서대로 실행합니다.

1. `01_install_requirements.bat`
2. `02_run_pipeline.bat`
3. `03_run_app.bat`

세 번째 파일은 Streamlit 서버가 실행되는 동안 콘솔 창을 유지합니다. 콘솔에 표시된 `http://localhost:8501` 주소를 브라우저에서 열고, 종료할 때는 같은 창에서 `Ctrl+C`를 누릅니다.

8501 포트가 이미 사용 중이면 Windows CMD에서 아래처럼 다른 포트를 지정한 뒤 세 번째 파일을 실행합니다.

```bat
set DEMO_PORT=8502
03_run_app.bat
```

### 수동 설치

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 8. 데이터 생성

기본 5,000명 데이터를 생성합니다.

Windows:

```bat
python scripts\generate_data.py
```

macOS/Linux:

```bash
python scripts/generate_data.py
```

생성 파일:

- `data/raw/customer_master.csv`
- `data/raw/customer_monthly_5000.csv`

## 9. 검증

Windows:

```bat
python scripts\validate_data.py
```

macOS/Linux:

```bash
python scripts/validate_data.py
```

검증 보고서:

- `reports/data_validation_report.csv`
- `reports/persona_summary.csv`
- `reports/outcome_distribution.csv`

## 10. 전체 파이프라인

전체 산출물을 한 번에 생성합니다.

Windows:

```bat
python scripts\run_pipeline.py
```

macOS/Linux:

```bash
python scripts/run_pipeline.py
```

강제 재생성 및 차트 HTML 생성:

Windows:

```bat
python scripts\run_pipeline.py --force --export-charts
```

macOS/Linux:

```bash
python scripts/run_pipeline.py --force --export-charts
```

소규모 smoke run:

Windows:

```bat
python scripts\run_pipeline.py --customer-count 100 --top-k 20 --force
```

macOS/Linux:

```bash
python scripts/run_pipeline.py --customer-count 100 --top-k 20 --force
```

주의: 위 소규모 명령은 기본 `data/` 산출물을 소규모 데이터로 덮어씁니다. 데모 전에는 다시 `python scripts/run_pipeline.py --force --export-charts`를 실행하세요.

## 11. Streamlit 실행

### 사용자용 수동 실행

Windows 사용자에게는 위의 `03_run_app.bat` 실행을 권장합니다. 직접 실행해야 할 때는 다음 명령을 사용합니다.

Windows:

```bat
python -m streamlit run app.py --server.port=8501 --server.headless=true
```

macOS/Linux:

```bash
python -m streamlit run app.py --server.port=8501 --server.headless=true
```

브라우저 주소:

```text
http://localhost:8501
```

`run_demo.bat`와 `run_demo.sh`는 readiness를 먼저 점검하는 보조 스크립트입니다. 일반 사용자가 화면을 안정적으로 유지하며 실행할 때는 `03_run_app.bat`을 사용합니다.

### Codex 및 자동 점검용 제한시간 실행

`streamlit run app.py`는 서버가 살아 있는 동안 종료되지 않는 정상 동작입니다. 자동 점검에서는 아래 제한시간 런처를 사용해 HTTP 응답을 확인한 뒤 임시 서버를 종료합니다.

Windows:

```bat
python scripts\start_streamlit.py --port 8519 --timeout 60
```

macOS/Linux:

```bash
python scripts/start_streamlit.py --port 8519 --timeout 60
```

자동 점검에서 `--keep-running` 또는 일반 `streamlit run app.py`를 사용하면 명령이 끝나지 않아 대기 상태처럼 보일 수 있습니다.

## 12. 테스트

Windows:

```bat
pytest -q
```

macOS/Linux:

```bash
pytest -q
```

데모 준비 상태 점검:

Windows:

```bat
python scripts\check_demo_readiness.py
```

macOS/Linux:

```bash
python scripts/check_demo_readiness.py
```

## 13. 데모 고객

파이프라인은 3명의 고정 데모 고객을 생성합니다.

- `main`
- `stable_comparison`
- `high_risk`

주요 파일:

- `data/demo/demo_customers.csv`
- `data/demo/main_demo_customer.json`

메인 데모 고객의 사전 계산 fallback 파일:

- `data/demo/matched_customers.csv`
- `data/demo/matched_future_trajectory.csv`
- `data/demo/outcome_summary.json`
- `data/demo/breakpoint_result.json`
- `data/demo/whatif_results.json`

## 14. 화면 흐름

1. 현재 고객 요약
2. 유사 고객 탐색
3. 미래 궤적
4. 결과 분포
5. 위험 분기점
6. 대응 시나리오
7. 브리핑

앱 상단에는 현재 실행 모드가 표시됩니다.

- `Live calculation`
- `Cached calculation`
- `Demo fallback`

## 15. 브리핑 및 선택 설정

현재 MVP는 외부 LLM API를 호출하지 않고 템플릿 설명으로 동작합니다. 따라서 API 키나 `.env` 파일은 실행에 필요하지 않습니다.

`.env.example`은 향후 외부 서비스 연동 시 사용할 수 있는 설정 예시입니다. 현재 `OPENAI_API_KEY` 환경변수는 readiness 점검에 상태로만 표시되며, 브리핑 결과나 앱 실행 방식은 바꾸지 않습니다.

## 16. 합성 데이터 고지

이 프로젝트의 모든 고객 데이터는 합성 데이터입니다.

- 실제 개인 정보가 아닙니다.
- 실제 신용평가 결과가 아닙니다.
- 대출 승인 판단이 아닙니다.
- 금융상품 추천이나 판매 목적이 아닙니다.
- 결과 분포는 비슷한 흐름을 보인 고객 집단에서 실제로 나타난 비율입니다.

## 17. 제한사항

- 실제 금융기관 데이터와 연결하지 않습니다.
- 데이터베이스를 사용하지 않습니다.
- 머신러닝 예측 모델을 학습하지 않습니다.
- 실시간 스트리밍 데이터는 없습니다.
- 모바일 UI 최적화는 MVP 범위 밖입니다.
- 대응 시나리오는 현금흐름 계산이며 위험 비율을 변경하지 않습니다.
- 사전 계산 fallback은 메인 데모 고객 중심으로 고정됩니다.

## 18. 장애 대응

데모 전 점검:

```bash
python scripts/check_demo_readiness.py
```

`NOT_READY`가 나오면:

```bash
python scripts/run_pipeline.py --force --export-charts
python scripts/check_demo_readiness.py
```

앱이 live 계산을 못 하면:

1. 화면 모드가 `Demo fallback`인지 확인합니다.
2. `data/demo/` 사전 계산 파일이 있는지 확인합니다.
3. 그래프가 실패하면 표와 `reports/demo_backup/` HTML을 사용합니다.
4. 포트 충돌 시 `DEMO_PORT=8502` 또는 `set DEMO_PORT=8502`를 사용합니다.

## 19. 심사위원 질문 대응

Q. 이건 미래 예측인가요?

A. 아닙니다. 비슷한 12개월 재무 궤적을 가진 합성 고객 집단이 이후 24개월 동안 어떤 결과를 보였는지 집계합니다.

Q. final_outcome은 랜덤인가요?

A. 아닙니다. 13~36개월의 월별 상태를 BUSINESS_RULES 기준으로 판정합니다.

Q. 매칭에 미래 데이터가 들어가나요?

A. 아닙니다. 특징 생성은 함수 시작 단계에서 `month <= 12`를 강제합니다.

Q. persona나 final_outcome이 매칭 특징에 포함되나요?

A. 아닙니다. 매칭은 `settings.MATCH_FEATURES`만 사용하며 persona/final_outcome은 표시용입니다.

Q. 대응 시나리오로 위험 비율이 바뀌나요?

A. 아닙니다. 대응 시나리오는 24개월 현금흐름 개선 효과만 보여줍니다.

Q. 인터넷이나 LLM API가 없어도 되나요?

A. 됩니다. 템플릿 설명과 사전 계산 fallback으로 동작합니다.

## 20. 향후 확장

- 실제 금융 데이터 스키마와의 안전한 매핑
- Explainable matching report
- 상담 이력 관리
- 사용자별 민감도 조정
- 시나리오 확장
- LLM 기반 설명 품질 개선
- 배포 환경용 인증/권한/감사 로그
- 데이터베이스 및 캐시 계층 도입

## 21. 디자인 및 에셋

Financial Path Twin의 화면 정체성은 은행 상담용 금융 대시보드를 기준으로 설계했습니다. 배경은 밝고 차분하게 유지하고, 카드와 그래프는 얇은 테두리와 높은 대비의 텍스트를 사용합니다.

- 로고: `assets/financial_path_twin_logo.svg`
- Hero 이미지: `assets/financial_path_twin_hero.svg`
- 스타일: `assets/styles.css`
- 에셋 로더: `src/assets.py`

로고와 Hero 이미지는 모두 자체 제작 SVG입니다. 외부 이미지 URL, 외부 은행 상표, 저작권 이미지에 의존하지 않습니다. SVG에는 `title`과 `desc`를 포함해 접근성을 보강했으며, 에셋 파일이 누락되어도 앱이 중단되지 않도록 코드 내부 fallback SVG를 사용합니다.

기본 글꼴은 외부 다운로드 없이 다음 시스템 한글 폰트 스택을 사용합니다.

```text
Pretendard, Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, sans-serif
```

색상 토큰은 `src/theme.py`에서 관리하며 CSS 변수와 Plotly 그래프 색상이 같은 의미를 공유하도록 구성했습니다.

## 22. 화면 문구와 용어

화면 문구는 일반 사용자가 상담 흐름을 따라갈 수 있도록 한글 중심으로 정리합니다.

| 기존 기술어 | 화면 표현 |
|---|---|
| Trajectory Matching | 유사 재무 흐름 찾기 |
| Outcome Distribution | 유사 고객의 이후 결과 |
| Breakpoint | 위험 분기점 |
| Risk Group | 위험 경로 고객 |
| Avoidance Group | 위험 회피 고객 |
| What-if | 대응 시나리오 |
| Similarity Score | 재무 흐름 유사도 |
| Cash Depletion | 현금 고갈 |
| Baseline | 아무 조치 없음 |

주요 용어 설명:

- DSR: 월소득 중 대출 원리금 상환에 사용하는 비율입니다.
- 저축률: 월소득에서 모든 지출을 제외하고 남은 비율입니다.
- 고정지출 비중: 월소득 중 매월 반복적으로 지출되는 금액의 비율입니다.
- 위험 분기점: 위험 경로 고객과 위험을 피한 고객의 재무 흐름이 처음으로 뚜렷하게 달라진 시점입니다.
- 대응 시나리오: 현재 재무 조건에 특정 행동을 적용했을 때 현금흐름이 어떻게 달라지는지 계산한 결과입니다.

## 23. 발표 모드 실행 방법

Streamlit 사이드바의 `화면 모드`에서 `발표 모드`를 선택하면 메인 데모 고객으로 시작합니다. 발표 모드는 사전 계산된 `data/demo/main_demo_customer.json` 결과를 먼저 사용하고, 고객을 바꾼 경우에는 해당 고객의 기존 분석 결과를 한 번 준비해 세션에서 재사용합니다. 기술 설정과 세부 원본 표는 숨기고, 상단 탭으로 장면을 전환합니다.

3분 시연 흐름:

1. `① 현재 상태`: 현재 고객의 KPI, 소득·지출, 저축률, DSR
2. `② 유사 경로`: 유사 고객의 이후 흐름과 결과 분포
3. `③ 위험 분기점`: 두 경로가 갈라진 시점과 주요 차이
4. `④ 대응 시나리오`: 현금흐름 개선 비교
5. `⑤ 분석 요약`: 고객용·직원용 브리핑과 PoC 고지

탭을 클릭하거나 언어를 바꿔도 선택 고객, 화면 모드, 표시 지표, 이미 준비한 분석 결과는 유지됩니다. 탭 내부에서는 매칭, 결과 집계, 분기점, What-if 계산을 다시 실행하지 않습니다.

앱을 직접 열 때는 일반 Streamlit 명령을 사용할 수 있습니다.

```powershell
streamlit run app.py
```

자동 확인이나 테스트 중에는 서버 프로세스가 계속 실행되어 멈춘 것처럼 보이지 않도록 제한시간 런처를 사용합니다.

```powershell
python scripts\start_streamlit.py --port 8501 --timeout 60
```

## 24. 언어 선택

Financial Path Twin은 한국어와 영어 화면을 지원합니다. 기본 언어는 한국어입니다.

- 지원 언어: 한국어(`ko`), English(`en`)
- 선택 위치: 앱 상단 Hero 영역 오른쪽의 `언어 / Language` 콤보 박스
- 영어 발표: 발표 전에 상단 언어 선택을 `English`로 변경한 뒤 사이드바에서 `Presentation Mode`를 확인합니다.
- 언어를 변경해도 고객 ID, 화면 모드, 선택 지표, raw 궤적 표시 여부, 캐시된 분석 결과와 원본 데이터 값은 변경되지 않습니다.
- 금액은 한국어에서 `만원/억원`, 영어에서 `KRW million/KRW billion` 중심으로 표시합니다.
- 비율은 두 언어 모두 `%`로 표시합니다.

번역 문구는 `src/i18n.py`의 `TRANSLATIONS`에서 관리합니다. 새 문구를 추가할 때는 `section.current.title`, `chart.whatif.title`, `table.ending_balance`처럼 화면 영역을 알 수 있는 계층형 key를 사용하고, 한국어와 영어 양쪽에 같은 key를 추가합니다.

번역이 누락되어도 앱은 중단되지 않고 한국어 문구 또는 key 자체를 fallback으로 표시합니다. 누락 key는 다음 테스트로 확인합니다.

```powershell
pytest -q tests\test_i18n.py
```

## 25. RM Daily Review

### UX-07 운영 흐름

RM 화면의 `오늘의 업무 조회`는 저장된 Monthly Snapshot, RM Portfolio/독립 synthetic CRM metadata, synthetic presentation overlay, JSONL review log를 읽는 1.5~2초 UX 피드백이다. 실시간 분석이나 timing의 일 단위 감소가 아니다. 고객 상세에서는 historical cohort comparison과 저장된 supporting evidence를 보며, `FOLLOW_UP`은 단순 RM 기록으로 Case를 만들지 않는다.

Financial Path Twin은 월별 재무 궤적 분석으로 유사 고객의 경로가 갈라졌던 시점을 찾고,
Daily Review가 그 저장 결과를 매일 업무로 연결해 RM이 오늘 누구를 왜 확인할지 알려준다.

RM Daily Review는 일반 모드·발표 모드와 별도의 단순 업무 모드다. 5,000명 전체
synthetic universe는 기존 분석과 Matching reference universe로 유지하고, 그중 seed
기반으로 선택한 300명만 `RM-POC-001`의 업무 범위로 표시한다. CORE/PRIORITY/STANDARD는
금융 수치나 분석 결과에서 유도하지 않은 합성 CRM 관계 메타데이터다.

월별 분석 Snapshot은 아래 명령으로 별도 artifact에 만든다. 이 명령은 기존 raw 금융
CSV와 feature CSV를 읽기만 하며, Portfolio 고객별 Matching은 여전히 5,000명 전체를
사용한다.

```powershell
python scripts\build_rm_monthly_snapshot.py --snapshot-id YYYY-MM
```

Snapshot이 있으면 앱의 `RM 오늘의 업무` 모드에서 실제 저장 결과로 `오늘 먼저 확인`,
`곧 확인 예정`, `모니터링` 수를 표시한다. `곧 확인 예정`에서는 핵심관리 고객만
별도 filter할 수 있지만 관계 중요도가 timing bucket을 바꾸지는 않는다. Snapshot이
없으면 화면은 분석을 실행하지 않고 위 CLI 안내만 표시한다.

Daily Review는 Snapshot, Portfolio metadata, 수동 review log만 읽는다. Matching,
Outcome, Breakpoint, What-if, feature engineering, pipeline은 Daily 경로에서 호출하지
않는다. RM은 “왜 확인?”과 대화 준비를 확인한 뒤 `확인 완료`, `추가 상담 검토`,
`추후 모니터링` 중 하나를 기록한다. Case, 자동 연락, 새 예측 모델, risk score,
Capacity/Queue/Guided Stepper는 포함하지 않는다.
