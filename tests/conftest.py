"""
Shared pytest configuration.
Adds the project root and scripts/ directory to sys.path so all test files can
import from trading_utils and scripts/ without manual sys.path hacks (L6).
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'scripts'))
