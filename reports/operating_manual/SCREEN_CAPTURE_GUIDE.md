# Financial Path Twin 운영 매뉴얼 화면 캡처·갱신 가이드

이 폴더의 Word/Excel 매뉴얼은 **현재 로컬 앱을 실제 Edge에서 캡처한 화면**과, artifact 값을 바꾸지 않는 이미지형 설명도를 함께 사용합니다. 모든 고객 ID와 수치는 합성 PoC 기준입니다.

## 가장 간단한 갱신 방법

이미 캡처된 화면과 설명도로 Word/Excel만 다시 만들려면 아래 명령을 실행합니다.

```powershell
python scripts\generate_operating_manual.py
```

결과물은 다음 두 파일입니다.

- `Financial_Path_Twin_운영_사용자_매뉴얼.docx`
- `Financial_Path_Twin_운영_요약.xlsx`

## 실제 Edge 화면을 다시 캡처하는 방법

아래 명령은 **임시 Edge 프로필**과 localhost 전용 Streamlit 세션을 열고 PNG 한 장을 저장한 뒤 자동으로 종료·삭제합니다. 기존 Edge 탭, 사용자 프로필, 분석 원본, workflow/audit 원본은 건드리지 않습니다.

```powershell
python scripts\generate_operating_manual.py --edge-scenario general
python scripts\generate_operating_manual.py --edge-scenario presentation
python scripts\generate_operating_manual.py --edge-scenario presentation_landmark
python scripts\generate_operating_manual.py --edge-scenario presentation_whatif
python scripts\generate_operating_manual.py --edge-scenario rm
python scripts\generate_operating_manual.py --edge-scenario rm_queue
python scripts\generate_operating_manual.py --edge-scenario rm_customer_review
python scripts\generate_operating_manual.py --edge-scenario presentation_c002082_insufficient
python scripts\generate_operating_manual.py --edge-scenario rm_monitor_c000003
python scripts\generate_operating_manual.py --edge-scenario rm_queue_c000003_excluded
```

여러 장을 한 번에 갱신하려면 다음을 사용할 수 있습니다. 어떤 선택 화면 하나가 환경상 캡처되지 않아도, 이미 성공한 화면은 유지되고 Word/Excel에는 실제 존재하는 화면만 들어갑니다.

```powershell
python scripts\generate_operating_manual.py --try-edge-evidence-gallery
```

캡처 후에는 항상 아래 명령으로 Word/Excel을 한 번 더 갱신합니다.

```powershell
python scripts\generate_operating_manual.py
```

## 현재 매뉴얼에 쓰는 권장 Edge 화면

| 파일 | 화면 | 시연 목적 | 반드시 말할 경계 |
| --- | --- | --- | --- |
| `01_presentation_mode.png` | Presentation 시작 화면, C002608 | 5개 탭 기반 분석 story | 합성 데이터 PoC |
| `02_general_mode.png` | General 시작 화면, C002608 | 고객·지표 입력과 Q&A | 실제 고객 ID 입력 금지 |
| `03_rm_portfolio.png` | RM Portfolio | 5,000명 전체 funnel | 1,522명은 unbounded 참조값 |
| `04_presentation_historical_landmark.png` | Presentation ③ 유사 경로 근거 | historical landmark | 현재 고객의 미래 예측 시점 아님 |
| `05_presentation_whatif.png` | Presentation ④ 대응 시나리오 | rule-based What-if | 개입 효과·자동 조치 보장 아님 |
| `06_rm_human_capacity_3.png` | RM 용량 비교, 입력값 3 | 사람이 입력한 Selected/Deferred trade-off | 승인된 workload·시스템 권고 아님 |
| `07_rm_review_queue.png` | RM 검토 큐 | selected/routed only Queue | Monitor/NoSignal은 큐가 아님 |
| `08_rm_customer_review_c000001.png` | C000001 고객 검토 | 선정 이유·Why Now·current signals | 미래 위험 월·확률을 말하지 않음 |

`capacity=3` 캡처는 **임시 Streamlit 세션에만** 값을 넣어 만든 실제 UI 화면입니다. 저장된 순위·원본 triage·Alert·workflow 파일은 바뀌지 않습니다. `assets/12_capacity_comparison_example.png`은 같은 artifact 값을 더 읽기 쉽게 정리한 보조 이미지입니다. 입력값은 사람이 넣는 **draft 비교값**일 뿐, 승인된 workload나 시스템 권고가 아닙니다.

## 사람이 직접 Edge에서 추가 캡처할 때

자동 캡처 외에 발표용 화면을 더 만들고 싶다면 `03_run_app.bat`으로 앱을 연 뒤, 모드마다 새 브라우저 세션에서 아래만 수행합니다.

1. 창 크기를 `1366×768` 또는 `1920×1080`으로 고정합니다.
2. 화면 모드를 하나 선택하고, 아래 예시 customer를 설정합니다.
3. `Win+Shift+S`로 화면을 저장합니다.
4. `reports/operating_manual/screens/`에 PNG를 저장한 뒤 `python scripts\generate_operating_manual.py`를 실행합니다.

권장 수동 샘플:

- General: `C002608` 메인, `C002082`(landmark 근거 부족을 정직하게 보이는 Q&A), `C002672`(시각적 대비용)
- Presentation: `C002608`의 ① 현재 상태, ② 유사 경로, ③ 과거 landmark, ④ What-if
- RM: `C000001` Priority Review, `C000007` Review, `C000003` Monitor 비교 사례

## 캡처하면 안 되는 것

- 실제 고객 ID, 개인정보, API key, 비밀값이 보이는 화면
- 기본 앱에 fixture가 없는데 Action/Audit 버튼을 눌러 파일을 새로 생성하는 장면
- `reports/ui_check_main_1366.png` 같은 과거 문구가 남은 archival 화면
- historical landmark를 현재 고객의 ‘13개월 후 위험일’처럼 보이게 하는 자막
- historical outcome share를 prediction probability라고 표시하는 화면

기본 앱에서 `선정됨 · Case 미생성` / `open Case 0`이 보이는 것은 정상입니다. Alert → Action → Audit의 동작 근거는 격리된 합성 rehearsal인 `artifacts/post_p0/pilot_dry_run/seed42_capacity_3/`로만 설명합니다. 이는 실제 RM 성과, 외부 발송, SLA, 실제 고객 결과를 증명하지 않습니다.

## 상태별 FAQ 화면 캡처

Word 매뉴얼의 **20장**과 Excel의 `상태별_FAQ` 시트를 발표 Q&A용으로 사용합니다. 아래 화면은 모두 현재 로컬의 synthetic demo를 임시 Edge 세션에서 캡처한 것이며, 실제 고객·외부 발송·승인된 업무량의 증거가 아닙니다.

| FAQ | 실제 화면 파일 | 화면에서 확인할 것 | 한 줄 답변 |
| --- | --- | --- | --- |
| C002082 landmark 근거 부족 | `09_presentation_c002082_landmark_insufficient.png` | 고객 ID C002082, Presentation ③, ‘분석 제한 / 비교 제한’ | 200명 매칭은 성공했지만 과거 risk-path 0명이라 landmark 비교 집단이 부족합니다. |
| C000003 Monitor가 Queue 밖 | `10_rm_monitor_c000003.png`, `11_rm_queue_c000003_excluded.png` | 대표 비교 사례, Queue 검색 `C000003`의 0건 | Monitor는 관찰 상태이며 이번 triage의 active review routing 대상은 아닙니다. |
| Capacity=3 / Deferred=1,519 | `06_rm_human_capacity_3.png` | unbounded 1,522 vs 입력 3 / deferred 1,519 / draft | 사람 입력 비교값 3에 따라 저장 순위 앞 3명만 비교상 Selected입니다. |
| Alert / Case=0 | `03_rm_portfolio.png`, `assets/13_rm_alert_case_status_explained.png` | Open Alert 0, Queue Case 0, pending 1,522 | 기본 workflow에 Case fixture가 없으며 selection과 Case 생성은 분리됩니다. |

발표 전에 다음 네 문장을 연습합니다.

1. “근거 부족은 오류나 안전 판정이 아니라, 유사 과거 cohort에 landmark를 비교할 두 집단이 충분하지 않다는 뜻입니다.”
2. “Monitor는 policy signal과 triage selection을 구분하기 위한 비교 상태이며 operational Queue 행이 아닙니다.”
3. “Capacity 3은 사람이 입력한 draft 비교값이고, 1,519명은 거절이 아니라 이번 가정에서 deferred입니다.”
4. “Alert/Case 0은 기본 데모가 읽기 전용이기 때문이며, Action/Audit은 격리된 synthetic rehearsal 증거로만 설명합니다.”

## Alert / Case 상태를 설명할 때

매뉴얼의 **18~19장**과 Excel의 `Alert_Case_안내` 시트를 함께 사용합니다.

- `열린 Alert 없음` = 기본 workflow repository에 생성된 Case가 0개
- `선정됨 · Case 미생성` = Triage로 선정됐지만 Alert cycle은 아직 실행되지 않음
- `Case 생성 대기 1,522` = unbounded demo 후보 집합이며 실제 RM 업무량이나 실제 Alert 수가 아님

기본 RM 메뉴에 숨은 Case 생성 작업은 없습니다. `02_run_pipeline.bat`, 화면 탐색, capacity 비교로 Case를 만들지 않으며, 기본 화면을 Action/Audit 시연용으로 바꾸지 않습니다. 발표에서는 기본 RM 화면의 선정 근거를 먼저 보이고, Action/Audit 질문에는 격리된 synthetic rehearsal의 **3 Cases / 10 Audit events / network=false**를 별도 증거로만 제시합니다.
