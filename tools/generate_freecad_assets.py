"""Generate FreeCAD-native source, BIM model, assembly STEP, and review IFC."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREECADCMD = Path("/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd")


def main() -> int:
    if not FREECADCMD.exists():
        raise SystemExit("FreeCAD command was not found at /Applications/FreeCAD.app.")
    for macro in [
        ROOT / "freecad" / "build_mechanical_room.FCMacro",
        ROOT / "freecad" / "export_bim_ifc.FCMacro",
    ]:
        cmd = [str(FREECADCMD), str(macro)]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
