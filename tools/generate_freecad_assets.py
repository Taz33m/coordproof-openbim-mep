"""Generate FreeCAD-native source, BIM model, assembly STEP, and review IFC."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tooling import freecad_command

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    executable = freecad_command()
    if executable is None:
        raise SystemExit(
            "FreeCAD command was not found. Set FREECAD_CMD or add freecadcmd/FreeCADCmd to PATH."
        )
    freecad_dir = ROOT / "freecad"
    backups_before = set(freecad_dir.glob("*.FCBak"))
    try:
        for macro in [
            freecad_dir / "build_mechanical_room.FCMacro",
            freecad_dir / "export_bim_ifc.FCMacro",
        ]:
            cmd = [str(executable), str(macro)]
            print("$", " ".join(cmd), flush=True)
            subprocess.run(cmd, cwd=ROOT, check=True)
    finally:
        # FreeCAD creates timestamped backups when deterministic targets are
        # overwritten. Remove only backups created by this invocation; preserve
        # anything that existed before the automated build.
        for backup in set(freecad_dir.glob("*.FCBak")) - backups_before:
            backup.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
