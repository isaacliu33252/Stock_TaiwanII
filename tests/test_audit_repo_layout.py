from pathlib import Path

from scripts.misc.audit_repo_layout import (
    build_layout_report,
    classify_root_file,
)


def test_classify_root_file_keeps_known_root_entries():
    entry = classify_root_file(Path("README.md"))

    assert entry.category == "keep_root"
    assert entry.suggested_location == "."


def test_classify_root_file_identifies_handoff_docs():
    entry = classify_root_file(Path("GROUP_A_PLUS_EXAMPLE_HANDOFF_20260810.md"))

    assert entry.category == "root_doc_candidate"
    assert entry.suggested_location == "docs/ or handoff/"


def test_classify_root_file_identifies_script_candidates():
    assert classify_root_file(Path("backtest_group_a.py")).category == "script_candidate"
    assert classify_root_file(Path("_scratch.py")).category == "scratch_script_candidate"
    assert classify_root_file(Path("ncf_2330.py")).category == "module_candidate"


def test_classify_root_file_identifies_data_and_runner_candidates():
    assert classify_root_file(Path("taiwan_stock_20260810.xlsx")).category == "data_artifact_candidate"
    assert classify_root_file(Path("group_a_plus_config.json")).category == "config_candidate"
    assert classify_root_file(Path("run_daily.bat")).category == "runner_candidate"


def test_build_layout_report_counts_categories(tmp_path):
    for name in [
        "README.md",
        "GROUP_A_HANDOFF_20260810.md",
        "backtest_group.py",
        "group_a_config.json",
        "run_daily.sh",
    ]:
        (tmp_path / name).write_text("", encoding="utf-8")

    report = build_layout_report(tmp_path, sample_limit=2)

    assert report["root_file_count"] == 5
    assert report["keep_root_count"] == 1
    assert report["relocation_candidate_count"] == 4
    assert report["category_counts"]["keep_root"] == 1
    assert report["category_counts"]["root_doc_candidate"] == 1
    assert report["category_counts"]["script_candidate"] == 1
    assert report["category_counts"]["config_candidate"] == 1
    assert report["category_counts"]["runner_candidate"] == 1
