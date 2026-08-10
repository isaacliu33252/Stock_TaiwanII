from scripts.misc.audit_worktree_artifacts import (
    WorktreeEntry,
    is_artifact_path,
    is_cleanup_candidate,
    parse_status_porcelain,
    select_cleanup_candidates,
    summarize_entries,
    top_level_name,
)


def test_parse_status_porcelain_handles_modified_untracked_and_rename():
    raw = "\n".join(
        [
            " M group_a_plus/operations/daily_signal.py",
            "?? report/group_a_plus/latest/live_signal.json",
            "R  old_name.py -> scripts/misc/new_name.py",
        ]
    )

    entries = parse_status_porcelain(raw)

    assert entries == [
        WorktreeEntry(status=" M", path="group_a_plus/operations/daily_signal.py"),
        WorktreeEntry(status="??", path="report/group_a_plus/latest/live_signal.json"),
        WorktreeEntry(status="R ", path="scripts/misc/new_name.py"),
    ]


def test_artifact_path_classification_uses_known_generated_prefixes():
    assert is_artifact_path("report/group_a_plus/latest/live_signal.json")
    assert is_artifact_path("results/sweep/output.json")
    assert is_artifact_path("FinRL/results/backtest.json")
    assert is_artifact_path("FinRL/catboost_info/time_left.tsv")
    assert not is_artifact_path("group_a_plus/operations/daily_signal.py")
    assert not is_artifact_path("scripts/evaluate/build_report.py")


def test_summarize_entries_splits_artifact_and_source_changes():
    entries = [
        WorktreeEntry(status=" M", path="group_a_plus/operations/daily_signal.py"),
        WorktreeEntry(status=" M", path="report/group_a_plus/latest/live_signal.json"),
        WorktreeEntry(status="??", path="results/run.json"),
        WorktreeEntry(status="??", path="docs/new_note.md"),
    ]

    summary = summarize_entries(entries)

    assert summary["total_changed_paths"] == 4
    assert summary["artifact_changed_paths"] == 2
    assert summary["source_changed_paths"] == 2
    assert summary["artifact_top_levels"] == {"report": 1, "results": 1}
    assert summary["source_top_levels"] == {"group_a_plus": 1, "docs": 1}


def test_top_level_name_marks_root_files_explicitly():
    assert top_level_name("README.md") == ".root"
    assert top_level_name("scripts/misc/tool.py") == "scripts"


def test_cleanup_candidates_preserve_docs_and_model_registry():
    assert is_cleanup_candidate("report/group_a_plus/latest/live_signal.json")
    assert is_cleanup_candidate("models/portfolio/model.zip")
    assert not is_cleanup_candidate("report/group_a_plus/architecture/ARCHITECTURE_20260619.md")
    assert not is_cleanup_candidate("results/plotter.py")
    assert not is_cleanup_candidate("models/MODEL_REGISTRY.json")
    assert not is_cleanup_candidate("group_a_plus/operations/daily_signal.py")


def test_select_cleanup_candidates_sorts_deduplicates_and_filters():
    candidates = select_cleanup_candidates(
        [
            "report/group_a_plus/latest/live_signal.json",
            "report/group_a_plus/latest/live_signal.json",
            "report/group_a_plus/architecture/ARCHITECTURE_20260619.md",
            "news/ltn_mainstream_2023-01.jsonl",
        ]
    )

    assert candidates == [
        "news/ltn_mainstream_2023-01.jsonl",
        "report/group_a_plus/latest/live_signal.json",
    ]
