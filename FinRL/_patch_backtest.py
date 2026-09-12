#!/usr/bin/env python3
"""Patch BacktestEngine with progress bar support."""
import sys

path = '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/FinRL/v2/backtesting/backtest_engine.py'
with open(path, 'r') as f:
    content = f.read()

# =============================================================================
# 1. Add progress bar wrapper after the import line
# =============================================================================
wrapper_code = '''

# =============================================================================
# Progress Bar Wrapper (graceful fallback — no hard dependency on tqdm)
# =============================================================================

def _get_progress_bar(total: int, desc: str = "", disable: bool = False):
    """
    Return a context-manager that mimics tqdm's API but is a no-op if
    tqdm is unavailable or disable=True.
    """
    if disable:
        class _NoOpBar:
            def update(self, n: int = 1): pass
            def set_postfix(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return _NoOpBar()

    try:
        from tqdm import tqdm as _tqdm

        class _TqdmWrapper:
            def __init__(self, total, desc, disable):
                self._bar = _tqdm(
                    total=total, desc=desc, disable=disable,
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
                )

            def update(self, n: int = 1):
                self._bar.update(n)

            def set_postfix(self, **kwargs):
                self._bar.set_postfix(**kwargs)

            def __enter__(self):
                return self._bar.__enter__()

            def __exit__(self, *args):
                self._bar.__exit__(*args)

        return _TqdmWrapper(total=total, desc=desc, disable=disable)
    except Exception:
        class _NoOpBarSilent:
            def update(self, n: int = 1): pass
            def set_postfix(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return _NoOpBarSilent()

'''

import_marker = "from .performance_metrics import PerformanceMetrics, PerformanceResult"
parts = content.split(import_marker, 1)
if len(parts) != 2:
    print("ERROR: could not find import marker")
    sys.exit(1)
content = parts[0] + import_marker + wrapper_code + "\n\n" + parts[1]

# =============================================================================
# 2. Patch run_with_model loop
# =============================================================================
old = '''        obs, _ = env.reset()
        
        for step in range(len(self.df)):
            action, _ = model.predict(obs, deterministic=deterministic)'''
new = '''        obs, _ = env.reset()

        n_steps = len(self.df)
        pbar = _get_progress_bar(n_steps, desc="Backtesting (model)", disable=not self.config.verbose)
        pbar.__enter__()
        try:
            for step in range(n_steps):
                pbar.update(1)
                action, _ = model.predict(obs, deterministic=deterministic)'''
if old not in content:
    print("ERROR: could not find run_with_model loop marker")
    sys.exit(1)
content = content.replace(old, new)

# =============================================================================
# 3. Add pbar.__exit__() before return in run_with_model
# Pattern (exact indentation verified):
#   "            if terminated:\n                break\n        \n        return self._calculate_results()\n    \n    def run_with_strategy("
# =============================================================================
old = '''            if terminated:
                break
        
        return self._calculate_results()
    
    
    def run_with_strategy('''
new = '''            if terminated:
                break
        finally:
            pbar.__exit__(None, None, None)

        return self._calculate_results()
    
    
    def run_with_strategy('''
if old not in content:
    print("ERROR: could not find run_with_model return marker")
    sys.exit(1)
content = content.replace(old, new, 1)

# =============================================================================
# 4. Patch run_with_strategy loop
# =============================================================================
old = '''        history = []
        
        for step in range(len(self.df)):
            state = self._get_state(step)'''
new = '''        history = []
        n_steps = len(self.df)
        pbar = _get_progress_bar(n_steps, desc="Backtesting (strategy)", disable=not self.config.verbose)
        pbar.__enter__()
        try:
            for step in range(n_steps):
                pbar.update(1)
                state = self._get_state(step)'''
if old not in content:
    print("ERROR: could not find run_with_strategy loop marker")
    sys.exit(1)
content = content.replace(old, new)

# =============================================================================
# 5. Add pbar.__exit__() before return in run_with_strategy
# Pattern (exact indentation verified):
#   "            history.append(state)\n\n        return self._calculate_results()\n    \n    def _get_prev_value("
# =============================================================================
old = '''            history.append(state)

        return self._calculate_results()


    def _get_prev_value'''
new = '''            history.append(state)
        finally:
            pbar.__exit__(None, None, None)

        return self._calculate_results()


    def _get_prev_value'''
if old not in content:
    print("ERROR: could not find run_with_strategy return marker")
    sys.exit(1)
content = content.replace(old, new, 1)

with open(path, 'w') as f:
    f.write(content)
print("Done! All 5 patches applied successfully.")
