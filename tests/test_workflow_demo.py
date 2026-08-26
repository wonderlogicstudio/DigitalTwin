"""Focused contracts for the isolated deterministic workflow-demo fixture."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import src.workflow_demo as workflow_demo_module
from config import settings
from src.alert_repository import FileAlertCaseRepository
from src.workflow_demo import (
    WORKFLOW_DEMO_FIXTURE_FILENAME,
    WORKFLOW_DEMO_MAX_CASES,
    WorkflowDemoError,
    WorkflowDemoPaths,
    load_demo_fixture,
    load_demo_runtime,
    reset_demo,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    PROJECT_ROOT / "artifacts" / "workflow_demo" / "fixture_v1" / WORKFLOW_DEMO_FIXTURE_FILENAME
)


def _paths(tmp_path: Path) -> WorkflowDemoPaths:
    fixture_path = tmp_path / "fixture" / WORKFLOW_DEMO_FIXTURE_FILENAME
    fixture_path.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE_FIXTURE, fixture_path)
    return WorkflowDemoPaths(fixture_path=fixture_path, runtime_root=tmp_path / "runtime")


def _read_fixture(paths: WorkflowDemoPaths) -> dict[str, object]:
    return json.loads(paths.fixture_path.read_text(encoding="utf-8"))


def _write_fixture(paths: WorkflowDemoPaths, payload: dict[str, object]) -> None:
    paths.fixture_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _digest(path: Path) -> str | None:
    return None if not path.exists() else hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_is_bounded_deterministic_and_contains_only_initial_cases(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    fixture = load_demo_fixture(paths)

    assert 1 <= len(fixture.cases) <= WORKFLOW_DEMO_MAX_CASES
    assert [case.fixture_order for case in fixture.cases] == [1, 2, 3]
    assert [case.customer_id for case in fixture.cases] == ["C000001", "C000008", "C000010"]
    assert all(case.initial_state == "NEW" for case in fixture.cases)
    assert all(case.created_at.tzinfo is not None for case in fixture.cases)
    assert fixture.synthetic_demo is True
    assert fixture.external_delivery_attempted is False
    assert fixture.network_called is False
    assert fixture.sent is False
    assert fixture.future_label_selection is False


@pytest.mark.parametrize("case_count", [0, WORKFLOW_DEMO_MAX_CASES + 1])
def test_fixture_rejects_empty_or_oversized_case_sets(tmp_path: Path, case_count: int) -> None:
    paths = _paths(tmp_path)
    payload = _read_fixture(paths)
    original_case = payload["cases"][0]  # type: ignore[index]
    payload["cases"] = [
        {**original_case, "fixture_case_id": f"SYN-{index}", "fixture_order": index, "alert_id": f"ALT-{index}", "customer_id": f"C0000{index:02d}"}
        for index in range(1, case_count + 1)
    ]
    _write_fixture(paths, payload)

    with pytest.raises(WorkflowDemoError, match="1 to"):
        load_demo_fixture(paths)


def test_fixture_load_and_runtime_read_are_explicit_and_do_not_bootstrap(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    fixture = load_demo_fixture(paths)
    snapshot = load_demo_runtime(paths)

    assert fixture.fixture_id == "seed42_workflow_demo_fixture"
    assert snapshot.status == "DEMO_NOT_INITIALIZED"
    assert snapshot.cases == ()
    assert not paths.runtime_root.exists()


def test_fixture_rejects_customer_identifier_outside_synthetic_universe(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    payload = _read_fixture(paths)
    payload["cases"][0]["customer_id"] = "C999999"  # type: ignore[index]
    _write_fixture(paths, payload)

    with pytest.raises(WorkflowDemoError, match="synthetic universe"):
        load_demo_fixture(paths)


def test_reset_is_deterministic_and_replaces_only_injected_demo_runtime(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    protected_paths = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
        settings.DATA_RAW_DIR / "customer_master.csv",
        settings.DATA_PROCESSED_DIR / "trajectory_features.csv",
        settings.BASE_DIR
        / "artifacts"
        / "triage"
        / "seed42_crossfit_5fold_asof12_unbounded"
        / "rm_selection_manifest.json",
    )
    before = {path: _digest(path) for path in protected_paths}

    first = reset_demo(paths)
    first_files = {
        "manifest": paths.runtime_manifest_path.read_bytes(),
        "cases": (paths.workflow_root / "alert_cases.json").read_bytes(),
    }
    (paths.runtime_root / "sentinel.txt").write_text("only demo runtime", encoding="utf-8")
    second = reset_demo(paths)
    second_files = {
        "manifest": paths.runtime_manifest_path.read_bytes(),
        "cases": (paths.workflow_root / "alert_cases.json").read_bytes(),
    }

    assert first.is_ready and second.is_ready
    assert [case.alert_id for case in first.cases] == [case.alert_id for case in second.cases]
    assert [case.to_dict() for case in first.cases] == [case.to_dict() for case in second.cases]
    assert first_files == second_files
    assert len(second.cases) == 3
    assert not (paths.runtime_root / "sentinel.txt").exists()
    assert not paths.reset_marker_path.exists()
    assert not list(paths.runtime_root.rglob("*.tmp"))
    assert {path: _digest(path) for path in protected_paths} == before


def test_interrupted_reset_fails_closed_until_a_later_explicit_reset_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    reset_demo(paths)

    def interrupt_after_marker(_: WorkflowDemoPaths) -> None:
        raise OSError("simulated reset interruption")

    monkeypatch.setattr(
        workflow_demo_module,
        "_remove_runtime_contents_except_reset_marker",
        interrupt_after_marker,
    )
    with pytest.raises(OSError, match="simulated reset interruption"):
        reset_demo(paths)

    interrupted = load_demo_runtime(paths)
    assert interrupted.status == "DEMO_NOT_INITIALIZED"
    assert interrupted.cases == ()
    assert paths.reset_marker_path.exists()

    monkeypatch.undo()
    recovered = reset_demo(paths)
    assert recovered.is_ready
    assert [case.state for case in recovered.cases] == ["NEW", "NEW", "NEW"]
    assert not paths.reset_marker_path.exists()


def test_missing_or_corrupt_runtime_fails_closed_without_default_fallback(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    unrelated_default = tmp_path / "unrelated-default-workflow"
    unrelated_default.mkdir()
    assert FileAlertCaseRepository(unrelated_default).list_cases() == ()

    missing = load_demo_runtime(paths)
    assert missing.status == "DEMO_NOT_INITIALIZED"
    assert missing.cases == ()

    paths.runtime_root.mkdir(parents=True)
    paths.runtime_manifest_path.write_text("{broken-json", encoding="utf-8")
    corrupt = load_demo_runtime(paths)
    assert corrupt.status == "DEMO_CORRUPT"
    assert corrupt.cases == ()
    assert corrupt.manifest is None


def test_corrupt_case_repository_is_not_exposed_as_a_ready_demo(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    reset_demo(paths)
    storage_path = paths.workflow_root / "alert_cases.json"
    storage_path.write_text("{not-json", encoding="utf-8")

    snapshot = load_demo_runtime(paths)

    assert snapshot.status == "DEMO_CORRUPT"
    assert snapshot.cases == ()


def test_paths_reject_default_workflow_or_audit_roots() -> None:
    fixture_path = SOURCE_FIXTURE
    with pytest.raises(WorkflowDemoError, match="separate"):
        WorkflowDemoPaths(
            fixture_path=fixture_path,
            runtime_root=settings.BASE_DIR / "artifacts" / "workflow",
        )
    with pytest.raises(WorkflowDemoError, match="separate"):
        WorkflowDemoPaths(
            fixture_path=fixture_path,
            runtime_root=settings.BASE_DIR / "artifacts" / "audit",
        )


def test_module_is_ui_network_and_label_independent() -> None:
    source = (PROJECT_ROOT / "src" / "workflow_demo.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert {"streamlit", "requests", "httpx", "urllib", "socket", "pandas"}.isdisjoint(imported_roots)
    assert not any(
        forbidden in module
        for module in imported_modules
        for forbidden in ("data_generator", "crossfit", "matcher", "evaluator", "scorer")
    )
    assert "final_outcome" not in source
    assert "persona" not in source
    assert "real RM" not in source
