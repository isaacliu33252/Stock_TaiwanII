import sys
from pathlib import Path

# Allow tests to import root-level modules (train_dual_group_2024_2026, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent))
# Allow tests to import scripts/misc modules (validate_*, run_group_a_*, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "misc"))
