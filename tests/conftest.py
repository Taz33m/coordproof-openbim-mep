from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "tools", ROOT / "validation", ROOT / "cadquery"):
    value = str(folder)
    if value not in sys.path:
        sys.path.insert(0, value)
