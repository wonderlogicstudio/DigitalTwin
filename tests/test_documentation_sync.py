"""Source-of-truth documentation and referenced P0-path sanity checks."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCS = (
    "README.md",
    "ARCHITECTURE.md",
    "PROJECT_HANDOFF.md",
    "DECISIONS.md",
    "BUSINESS_RULES.md",
    "DATA_DICTIONARY.md",
    "SPEC.md",
    "TEST_PLAN.md",
    "TASKS.md",
)


def test_source_of_truth_docs_record_the_implemented_p0_boundaries() -> None:
    contents = {
        name: (PROJECT_ROOT / name).read_text(encoding="utf-8")
        for name in SOURCE_DOCS
    }

    assert "Current P0 operational prototype" in contents["README.md"]
    assert "Current extension architecture (P0)" in contents["ARCHITECTURE.md"]
    assert "Current implementation snapshot (2026-08-26)" in contents["PROJECT_HANDOFF.md"]
    assert "DEC-016 Population artifact isolation" in contents["DECISIONS.md"]
    assert "P0 prospective, triage, and workflow boundaries" in contents["BUSINESS_RULES.md"]
    assert "Separate P0 prototype artifacts" in contents["DATA_DICTIONARY.md"]
    assert "P0 extension: RM operational prototype" in contents["SPEC.md"]
    assert "P0 regression extensions" in contents["TEST_PLAN.md"]
    assert "P0 Population, Early Warning, Triage, RM Workflow, and UI Status" in contents["TASKS.md"]


def test_documented_p0_paths_exist_and_external_delivery_remains_out_of_scope() -> None:
    expected_paths = (
        "scripts/run_triage_selection_manifest.py",
        "src/population_result.py",
        "src/population_batch.py",
        "src/population_artifacts.py",
        "src/as_of_features.py",
        "src/reference_matcher.py",
        "src/prospective_signals.py",
        "src/crossfit_backtest.py",
        "src/demo_policy.py",
        "src/triage_selector.py",
        "src/alert_case.py",
        "src/alert_repository.py",
        "src/banker_service.py",
        "src/audit_trail.py",
        "src/notifications.py",
        "NOTIFICATION_ADAPTER_CONTRACT.md",
        "artifacts/population/seed42_full_run/population_manifest.json",
        "artifacts/triage/seed42_crossfit_5fold_asof12_unbounded/rm_selection_manifest.json",
    )
    missing = [path for path in expected_paths if not (PROJECT_ROOT / path).exists()]
    assert not missing

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    handoff = (PROJECT_ROOT / "PROJECT_HANDOFF.md").read_text(encoding="utf-8")
    assert "No external notification channel is implemented." in readme
    assert "DB remains unapproved and unimplemented." in handoff


def test_post_p0_docs_keep_feedback_claims_and_real_data_boundaries_explicit() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    handoff = (PROJECT_ROOT / "PROJECT_HANDOFF.md").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "BUSINESS_RULES.md").read_text(encoding="utf-8")
    report = (PROJECT_ROOT / "reports" / "post_p0" / "12-17_feedback_security_sync.md").read_text(
        encoding="utf-8"
    )
    closure_matrix = PROJECT_ROOT / "artifacts" / "post_p0" / "feedback" / "coverage_matrix_12_17.json"

    assert "Post-P0 feedback-readiness status" in readme
    assert "not an approved workload" in readme
    assert "No approved real/anonymized data has been admitted or validated" in readme
    assert "Post-P0 feedback-readiness additions" in handoff
    assert "Post-P0 evidence and public-repository boundaries" in rules
    assert "actual RM pilot" in report
    assert "external notification delivery" in report
    assert closure_matrix.exists()


def test_guided_workflow_docs_and_manual_generator_keep_the_display_only_boundary() -> None:
    architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    decisions = (PROJECT_ROOT / "DECISIONS.md").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "BUSINESS_RULES.md").read_text(encoding="utf-8")
    test_plan = (PROJECT_ROOT / "TEST_PLAN.md").read_text(encoding="utf-8")
    handoff = (PROJECT_ROOT / "PROJECT_HANDOFF.md").read_text(encoding="utf-8")
    generator = (PROJECT_ROOT / "scripts" / "generate_operating_manual.py").read_text(
        encoding="utf-8"
    )
    capture_guide = (
        PROJECT_ROOT / "reports" / "operating_manual" / "SCREEN_CAPTURE_GUIDE.md"
    ).read_text(encoding="utf-8")

    assert "Guided RM display/orchestration boundary" in architecture
    assert "DEC-024 Guided Workflow is guidance, not a decision engine" in decisions
    assert "Guided RM workflow boundaries" in rules
    assert "Guided RM final regression gate" in test_plan
    assert "five-step Guided Workflow display shell" in handoff
    assert "안내된 RM 업무 흐름: 화면을 처음 보는 사용자를 위한 5단계" in generator
    assert "다음 탭이 막힌 것처럼 보일 때: 실제 동작과 해결 순서" in generator
    assert "Guided Workflow image status: Korean reference capture complete / device sign-off pending" in capture_guide


def test_operating_manual_images_match_their_current_source_and_caption() -> None:
    """Keep every embedded manual image traceable to its source and caption."""

    manual_dir = PROJECT_ROOT / "reports" / "operating_manual"
    manual_path = manual_dir / "Financial_Path_Twin_운영_사용자_매뉴얼.docx"
    source_paths = [
        *sorted((manual_dir / "assets").glob("*.png")),
        *sorted((manual_dir / "screens").glob("*.png")),
    ]
    source_name_by_hash = {
        sha256(path.read_bytes()).hexdigest(): path.name for path in source_paths
    }
    caption_cues = {
        "01_modes_overview.png": "세 화면 모드",
        "02_analytics_to_rm_flow.png": "책임 경계",
        "03_recommended_demo_storyboard.png": "2분 시연",
        "02_general_mode.png": "일반 모드",
        "07_general_mode_annotated_inputs.png": "입력 순서",
        "08_general_sample_customers.png": "합성 고객 샘플",
        "02a_general_direct_c000001.png": "C000001",
        "07_rm_review_queue.png": "검토 큐",
        "08_rm_customer_review_c000001.png": "Customer Review",
        "11a_rm_workflow_demo_entry_cta.png": "Workflow Demo",
        "12_workflow_demo_entry_uninitialized.png": "Demo 진입 직후",
        "13_workflow_demo_new_before_action.png": "초기화 직후",
        "14_workflow_demo_ack_after_action.png": "append-only",
        "16_workflow_demo_preview_not_sent.png": "not sent",
        "01_presentation_mode.png": "발표 모드",
        "03_rm_portfolio.png": "RM 업무 모드 Portfolio",
        "09_evidence_status_matrix.png": "증명된 범위",
        "10_rm_preparation_workflow.png": "준비",
        "12_capacity_comparison_example.png": "capacity=3",
        "11_evaluator_feedback_response_map.png": "피드백",
        "04_presentation_historical_landmark.png": "landmark",
        "05_presentation_whatif.png": "What-if",
        "06_rm_human_capacity_3.png": "capacity=3",
        "09_presentation_c002082_landmark_insufficient.png": "C002082",
        "10_rm_monitor_c000003.png": "C000003",
        "11_rm_queue_c000003_excluded.png": "C000003",
        "13_rm_alert_case_status_explained.png": "Alert 0",
        "14_default_rm_vs_synthetic_rehearsal.png": "synthetic workflow rehearsal",
        "15_faq_status_overview.png": "네 가지 상태 FAQ",
        "16_faq_landmark.png": "C002082",
        "17_faq_monitor.png": "C000003",
        "18_faq_capacity.png": "Capacity=3",
        "19_faq_alert_case.png": "Alert / Case=0",
        "20_workflow_demo_data_boundary.png": "데이터 변경 경계",
        "21_workflow_demo_presentation_flow.png": "내부 발표 흐름",
        "22_workflow_demo_action_before_after.png": "NEW에서 ACKNOWLEDGED",
    }
    namespaces = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }
    with ZipFile(manual_path) as archive:
        document_root = ElementTree.fromstring(archive.read("word/document.xml"))
        relationships_root = ElementTree.fromstring(
            archive.read("word/_rels/document.xml.rels")
        )
        target_by_relation_id = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_root
            if relationship.attrib.get("Target", "").startswith("media/")
        }
        paragraphs = document_root.findall(".//w:body/w:p", namespaces)

        def paragraph_text(paragraph: ElementTree.Element) -> str:
            return "".join(node.text or "" for node in paragraph.findall(".//w:t", namespaces))

        matched_sources: set[str] = set()
        embedded_image_count = 0
        for index, paragraph in enumerate(paragraphs):
            embeds = paragraph.findall(".//a:blip", namespaces)
            if not embeds:
                continue
            caption = next(
                (
                    paragraph_text(candidate).strip()
                    for candidate in paragraphs[index + 1 :]
                    if paragraph_text(candidate).strip()
                ),
                "",
            )
            for embed in embeds:
                relation_id = embed.attrib[f"{{{namespaces['r']}}}embed"]
                target = target_by_relation_id[relation_id]
                source_name = source_name_by_hash[sha256(archive.read(f"word/{target}")).hexdigest()]
                assert caption_cues[source_name] in caption
                matched_sources.add(source_name)
                embedded_image_count += 1

    assert matched_sources == set(caption_cues)
    assert embedded_image_count == 42
