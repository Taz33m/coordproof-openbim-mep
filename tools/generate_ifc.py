"""Generate the IFC-first OpenBIM mechanical room model."""

from __future__ import annotations

from openbim_core import IFC_PATH, build_openbim_model, write_openbim_outputs


def main() -> None:
    model = build_openbim_model()
    write_openbim_outputs(model)
    print(f"Wrote {IFC_PATH}")


if __name__ == "__main__":
    main()
