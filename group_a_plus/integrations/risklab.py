"""Load selected RiskLabAI modules without importing its optional-heavy package API."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load RiskLabAI module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_risklab_components(root: Path) -> dict[str, Any]:
    """Load only the independently usable RiskLabAI research components."""
    root = root.resolve()
    package = root / "RiskLabAI"
    license_path = root / "LICENSE"
    if not package.is_dir() or not license_path.exists():
        raise FileNotFoundError(f"Invalid RiskLabAI root: {root}")

    namespace = f"_group_a_plus_risklab_{abs(hash(str(root)))}"
    backtest_pkg = types.ModuleType(f"{namespace}.backtest")
    backtest_pkg.__path__ = [str(package / "backtest")]
    sys.modules[backtest_pkg.__name__] = backtest_pkg
    micro_pkg = types.ModuleType(f"{namespace}.microstructure")
    micro_pkg.__path__ = [str(package / "features" / "microstructural_features")]
    sys.modules[micro_pkg.__name__] = micro_pkg

    numba_shim_created = False
    if importlib.util.find_spec("numba") is None:
        numba_shim = types.ModuleType("numba")

        def jit(*args: Any, **kwargs: Any) -> Any:
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]

            def decorator(function: Any) -> Any:
                return function

            return decorator

        numba_shim.jit = jit
        sys.modules["numba"] = numba_shim
        numba_shim_created = True

    statistics = _load_module(
        f"{backtest_pkg.__name__}.backtest_statistics",
        package / "backtest" / "backtest_statistics.py",
    )
    psr = _load_module(
        f"{backtest_pkg.__name__}.probabilistic_sharpe_ratio",
        package / "backtest" / "probabilistic_sharpe_ratio.py",
    )
    pbo = _load_module(
        f"{backtest_pkg.__name__}.probability_of_backtest_overfitting",
        package / "backtest" / "probability_of_backtest_overfitting.py",
    )
    overfit = _load_module(
        f"{backtest_pkg.__name__}.test_set_overfitting",
        package / "backtest" / "test_set_overfitting.py",
    )
    corwin = _load_module(
        f"{micro_pkg.__name__}.corwin_schultz",
        package / "features" / "microstructural_features" / "corwin_schultz.py",
    )
    bekker = _load_module(
        f"{micro_pkg.__name__}.bekker_parkinson_volatility_estimator",
        package
        / "features"
        / "microstructural_features"
        / "bekker_parkinson_volatility_estimator.py",
    )
    if numba_shim_created:
        sys.modules.pop("numba", None)
    return {
        "statistics": statistics,
        "psr": psr,
        "pbo": pbo,
        "overfit": overfit,
        "corwin": corwin,
        "bekker": bekker,
        "license": str(license_path),
    }
