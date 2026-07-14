from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from coordproof import _source_tree_version

ROOT = Path(__file__).resolve().parents[1]


def test_observed_formats_schema_rejects_duplicates() -> None:
    schema = json.loads(
        (ROOT / "manifest" / "parameter_schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)

    errors = list(validator.iter_errors({"observed_formats": ["step", "step"]}))

    assert any(error.validator == "uniqueItems" for error in errors)


def test_source_version_discovery_does_not_require_a_fixed_package_depth(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-root"
    package_file = source_root / "unusual" / "nested" / "coordproof" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    (source_root / "pyproject.toml").write_text(
        '[project]\nname = "coordproof-openbim-mep"\n',
        encoding="utf-8",
    )
    (source_root / "VERSION").write_text("9.8.7\n", encoding="utf-8")

    assert _source_tree_version(package_file) == "9.8.7"
