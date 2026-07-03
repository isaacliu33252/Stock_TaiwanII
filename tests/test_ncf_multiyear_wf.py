from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "sweep" / "ncf_multiyear_wf.py"
    spec = importlib.util.spec_from_file_location("_test_ncf_multiyear_wf", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_auc_supports_current_flat_structure() -> None:
    module = _load_module()
    data = {
        "horizons": {
            "1": {"classification": {"val_auc": 0.61}},
            "5": {"classification": {"val_auc": 0.62}},
            "20": {"classification": {"val_auc": 0.63}},
        }
    }

    aucs = module._extract_auc(data)

    assert aucs[1] == {"bull": None, "bear": None, "all": 0.61}
    assert aucs[5]["all"] == 0.62
    assert aucs[20]["all"] == 0.63


def test_extract_auc_supports_current_regime_structure() -> None:
    module = _load_module()
    data = {
        "horizons": {
            "20": {
                "classification": {
                    "bull": {"ensemble": {"auc": 0.71}},
                    "bear": {"val_auc": 0.82},
                }
            }
        }
    }

    aucs = module._extract_auc(data)

    assert aucs[20] == {"bull": 0.71, "bear": 0.82, "all": None}


def test_extract_auc_supports_legacy_regime_classification() -> None:
    module = _load_module()
    data = {
        "horizons": {
            "5": {
                "regime_classification": {
                    "bull": {"ensemble": {"auc": 0.55}},
                    "bear": {"ensemble": {"auc": 0.66}},
                }
            }
        }
    }

    aucs = module._extract_auc(data)

    assert aucs[5] == {"bull": 0.55, "bear": 0.66, "all": None}


def test_extract_auc_converts_nan_to_none() -> None:
    module = _load_module()
    data = {"horizons": {"20": {"classification": {"val_auc": float("nan")}}}}

    aucs = module._extract_auc(data)

    assert aucs[20] == {"bull": None, "bear": None, "all": None}
