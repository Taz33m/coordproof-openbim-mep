"""Reconcile ProjectSpec values with producer inputs and declared relationships."""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from project_spec import ProjectSpec, ProjectSpecError, load_project_spec

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_SPEC_PATH = ROOT / "spec" / "mechanical_room.project.json"
DEFAULT_CONTRACT_PATH = ROOT / "spec" / "reconciliation.contract.json"
CONTRACT_SCHEMA_PATH = ROOT / "spec" / "reconciliation.schema.json"
DEFAULT_CSV_PATH = ROOT / "reports" / "parameter_reconciliation.csv"
DEFAULT_MARKDOWN_PATH = ROOT / "reports" / "parameter_reconciliation.md"

ROW_FIELDS = (
    "relation_id",
    "subject_kind",
    "subject_id",
    "canonical_path",
    "producer",
    "producer_path",
    "relation",
    "expected",
    "actual",
    "unit",
    "tolerance_mm",
    "status",
    "reason",
)

SCAD_NAME = r"[A-Za-z_$][A-Za-z0-9_$]*"
SCAD_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
SCAD_DECLARATION = re.compile(rf"^\s*({SCAD_NAME})\s*=\s*(.*?)\s*$", re.DOTALL)
SCAD_NUMERIC_ASSIGNMENT = re.compile(
    rf"^\s*({SCAD_NAME})\s*=\s*({SCAD_NUMBER})\s*$",
    re.DOTALL,
)
INDEXED_PATH = re.compile(r"^(dimensions_mm|origin_mm)\[([0-2])\]$")

PYTHON_REFLECTION_NAMES = frozenset(
    {
        "__builtins__",
        "__import__",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "locals",
        "setattr",
        "vars",
    }
)
PYTHON_INTROSPECTION_ATTRIBUTES = frozenset(
    {"f_globals", "f_locals", "modules"}
)

JSONObject = dict[str, Any]


class ReconciliationError(ValueError):
    """Raised when the reconciliation contract cannot be used safely."""

    def __init__(self, heading: str, issues: Sequence[str]) -> None:
        self.heading = heading
        self.issues = tuple(issues)
        super().__init__(heading + "\n" + "\n".join(f"- {issue}" for issue in issues))


class _DuplicateKeyError(ValueError):
    pass


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError(f"non-standard number {value!r}")


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"number is outside the supported finite range: {value!r}")
    return number


def _parse_supported_int(value: str) -> int:
    number = int(value)
    try:
        finite_as_float = math.isfinite(float(number))
    except OverflowError:
        finite_as_float = False
    if not finite_as_float:
        raise ValueError("integer is outside the supported finite range")
    return number


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> JSONObject:
    result: JSONObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path, label: str) -> JSONObject:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReconciliationError(f"{label} could not be loaded", [f"{path}: {exc}"]) from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
            parse_float=_parse_finite_float,
            parse_int=_parse_supported_int,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError, RecursionError) as exc:
        raise ReconciliationError(f"{label} JSON is invalid", [str(exc)]) from exc
    if not isinstance(payload, dict):
        raise ReconciliationError(f"{label} JSON is invalid", ["document must be an object"])
    return payload


def _json_path(parts: Sequence[object]) -> str:
    value = "$"
    for part in parts:
        value += f"[{part}]" if isinstance(part, int) else f".{part}"
    return value


def _schema_issue(payload: JSONObject, error: Any) -> str:
    path = list(error.absolute_path)
    context = ""
    if len(path) >= 2 and path[0] in {"producers", "relations"} and isinstance(path[1], int):
        collection = payload.get(path[0], [])
        if path[1] < len(collection) and isinstance(collection[path[1]], dict):
            item = collection[path[1]]
            identifier = item.get("producer_id") or item.get("relation_id")
            classification = item.get("classification")
            if identifier:
                context = f" ({identifier}"
                if classification:
                    context += f", {classification}"
                context += ")"
    return f"{_json_path(path)}{context}: {error.message}"


def _is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and value == path.as_posix()
        and "\\" not in value
        and ":" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _duplicates(values: Sequence[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def load_contract(path: str | Path = DEFAULT_CONTRACT_PATH) -> JSONObject:
    """Load and validate a reconciliation contract without executing producers."""

    contract_path = Path(path).resolve()
    payload = _read_json(contract_path, "Reconciliation contract")
    schema = _read_json(CONTRACT_SCHEMA_PATH, "Reconciliation schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ReconciliationError("Reconciliation schema is invalid", [exc.message]) from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: (_json_path(list(error.absolute_path)), error.message),
    )
    if errors:
        raise ReconciliationError(
            "Reconciliation contract schema validation failed",
            [_schema_issue(payload, error) for error in errors],
        )

    issues: list[str] = []
    producer_ids = [item["producer_id"] for item in payload["producers"]]
    producer_subjects = [
        (item["subject"]["kind"], item["subject"]["id"])
        for item in payload["producers"]
    ]
    producer_paths = [item["path"] for item in payload["producers"]]
    relation_ids = [item["relation_id"] for item in payload["relations"]]
    relation_targets = [
        (item["to"]["kind"], item["to"]["id"], item["to"]["path"])
        for item in payload["relations"]
    ]
    duplicate_producers = _duplicates(producer_ids)
    duplicate_relations = _duplicates(relation_ids)
    if duplicate_producers:
        issues.append("duplicate producer_id value(s): " + ", ".join(duplicate_producers))
    duplicate_producer_subjects = sorted(
        subject for subject, count in Counter(producer_subjects).items() if count > 1
    )
    for kind, identifier in duplicate_producer_subjects:
        issues.append(f"multiple producers cover {kind} {identifier}")
    duplicate_producer_paths = _duplicates(producer_paths)
    if duplicate_producer_paths:
        issues.append(
            "multiple producers use the same source path(s): "
            + ", ".join(duplicate_producer_paths)
        )
    if duplicate_relations:
        issues.append("duplicate relation_id value(s): " + ", ".join(duplicate_relations))
    duplicate_relation_targets = sorted(
        target for target, count in Counter(relation_targets).items() if count > 1
    )
    for kind, identifier, path in duplicate_relation_targets:
        issues.append(f"multiple relations target {kind} {identifier}.{path}")

    for producer in payload["producers"]:
        if not _is_safe_relative_path(producer["path"]):
            issues.append(
                f"{producer['producer_id']} has unsafe producer path {producer['path']!r}"
            )
        producer_path = PurePosixPath(producer["path"])
        if producer["subject"]["kind"] != "asset_type":
            issues.append(
                f"{producer['producer_id']} producer subject must be an asset_type"
            )
        if producer["adapter"] == "python_mapping" and (
            producer_path.parent != PurePosixPath("cadquery")
            or producer_path.suffix != ".py"
        ):
            issues.append(
                f"{producer['producer_id']} python_mapping path must be cadquery/*.py"
            )
        if producer["adapter"] == "openscad_assignments" and (
            producer_path.parent != PurePosixPath("openscad")
            or producer_path.suffix != ".scad"
        ):
            issues.append(
                f"{producer['producer_id']} openscad_assignments path must be openscad/*.scad"
            )
        parameter_map = producer["parameter_map"]
        if "*" in parameter_map and parameter_map != {"*": "*"}:
            issues.append(
                f"{producer['producer_id']} wildcard parameter_map must be exactly {{'*': '*'}}"
            )
        if producer["adapter"] == "python_mapping" and parameter_map != {"*": "*"}:
            issues.append(
                f"{producer['producer_id']} python_mapping must use the identity wildcard map"
            )
        targets = list(parameter_map.values())
        excluded = producer.get("excluded_parameters", {})
        if parameter_map == {"*": "*"} and excluded:
            issues.append(
                f"{producer['producer_id']} wildcard parameter_map cannot define exclusions"
            )
        overlap = sorted(set(targets) & set(excluded))
        if overlap:
            issues.append(
                f"{producer['producer_id']} both maps and excludes: " + ", ".join(overlap)
            )
        duplicate_targets = _duplicates(targets)
        if duplicate_targets:
            issues.append(
                f"{producer['producer_id']} maps multiple parameters to: "
                + ", ".join(duplicate_targets)
            )

    for relation in payload["relations"]:
        relation_id = relation["relation_id"]
        source = relation["from"]
        target = relation["to"]
        if source["kind"] != "asset_type" or target["kind"] != "occurrence":
            issues.append(
                f"{relation_id} must point from an asset_type to an occurrence"
            )
        if source == target:
            issues.append(f"{relation_id} relation endpoints must be distinct")
        classification = relation["classification"]
        transform = relation.get("transform")
        if classification == "equal" and transform is not None:
            issues.append(f"{relation_id} equal relation cannot define a transform")
        if classification == "derived":
            if transform is None:
                issues.append(f"{relation_id} derived relation requires a transform")
            elif transform["operator"] == "identity":
                issues.append(
                    f"{relation_id} derived relation requires a non-identity transform"
                )
            else:
                operator = transform["operator"]
                operand = transform.get("operand")
                if (
                    (operator in {"add", "subtract"} and operand == 0)
                    or (operator == "multiply" and operand in {0, 1})
                    or (operator == "divide" and operand == 1)
                ):
                    issues.append(
                        f"{relation_id} derived relation uses a neutral or degenerate transform"
                    )
                if operator == "divide" and operand == 0:
                    issues.append(f"{relation_id} derived relation divides by zero")
        if classification == "override" and transform is not None:
            issues.append(f"{relation_id} override relation cannot define a transform")

    if issues:
        raise ReconciliationError("Reconciliation contract semantics failed", issues)
    return payload


def _declared_project_spec_path(contract: JSONObject, contract_path: Path) -> Path:
    base = contract_path.resolve().parent
    project_path = (base / contract["project_spec"]).resolve()
    try:
        project_path.relative_to(base)
    except ValueError as exc:
        raise ReconciliationError(
            "Reconciliation ProjectSpec path escaped the contract directory",
            [contract["project_spec"]],
        ) from exc
    return project_path


def contract_project_spec_path(
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
) -> Path:
    """Resolve the ProjectSpec declared by a validated reconciliation contract."""

    resolved_contract_path = Path(contract_path).resolve()
    return _declared_project_spec_path(
        load_contract(resolved_contract_path),
        resolved_contract_path,
    )


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _source_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ReconciliationError("Producer path escaped the repository", [relative_path]) from exc
    return path


def _canonical_python_build_call(
    tree: ast.Module,
    path: Path,
    selector: str,
) -> tuple[ast.FunctionDef, ast.Call, str]:
    builds = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build"
    ]
    if len(builds) != 1:
        raise ReconciliationError(
            "Python producer must define one canonical build() function",
            [f"{path}: found {len(builds)} definitions"],
        )
    build = builds[0]
    arguments = build.args
    signature_is_supported = (
        not build.decorator_list
        and not arguments.posonlyargs
        and len(arguments.args) == 1
        and arguments.args[0].arg == "parameters"
        and arguments.vararg is None
        and not arguments.kwonlyargs
        and arguments.kwarg is None
        and len(arguments.defaults) == 1
        and isinstance(arguments.defaults[0], ast.Constant)
        and arguments.defaults[0].value is None
    )
    if not signature_is_supported:
        raise ReconciliationError(
            "Python producer build() signature is unsupported",
            [f"{path}: expected undecorated build(parameters=None)"],
        )
    if not build.body or not isinstance(build.body[0], ast.Assign):
        raise ReconciliationError(
            "Python producer build() must start with the canonical merged() call",
            [str(path)],
        )
    first_statement = build.body[0]
    call = first_statement.value
    call_is_supported = (
        len(first_statement.targets) == 1
        and isinstance(first_statement.targets[0], ast.Name)
        and isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "merged"
        and len(call.args) == 2
        and not call.keywords
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "parameters"
        and isinstance(call.args[1], ast.Name)
        and call.args[1].id == selector
    )
    if not call_is_supported:
        raise ReconciliationError(
            "Python producer build() must start with the canonical merged() call",
            [f"{path}: expected merged(parameters, {selector})"],
        )
    result_target = first_statement.targets[0]
    if not isinstance(result_target, ast.Name):  # Narrowed by call_is_supported.
        raise AssertionError("canonical merged() result target was not a name")
    return build, call, result_target.id


def _validate_python_mapping_consumption(
    build: ast.FunctionDef,
    result_name: str,
    mapping: Mapping[str, object],
    path: Path,
) -> None:
    """Validate the bounded, reviewable use shape of the merged input mapping."""

    first_statement = build.body[0]
    if not isinstance(first_statement, ast.Assign):  # Guaranteed by the caller.
        raise AssertionError("canonical merged() statement was not an assignment")
    initial_target = first_statement.targets[0]
    parents = {
        child: parent
        for parent in ast.walk(build)
        for child in ast.iter_child_nodes(parent)
    }
    consumed_keys: set[str] = set()
    issues: list[str] = []
    for node in ast.walk(build):
        if not isinstance(node, ast.Name) or node.id != result_name:
            continue
        if node is initial_target:
            continue
        parent = parents.get(node)
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(parent, ast.Subscript)
            and parent.value is node
            and isinstance(parent.ctx, ast.Load)
            and isinstance(parent.slice, ast.Constant)
            and isinstance(parent.slice.value, str)
        ):
            key = parent.slice.value
            if key in mapping:
                consumed_keys.add(key)
            else:
                issues.append(f"line {node.lineno}: unknown input key {key!r}")
            continue
        issues.append(
            f"line {node.lineno}: merged result {result_name!r} escapes literal key reads"
        )

    numeric_keys = {key for key, value in mapping.items() if _is_number(value)}
    missing_keys = sorted(numeric_keys - consumed_keys)
    if missing_keys:
        issues.append("numeric inputs are not consumed: " + ", ".join(missing_keys))
    if issues:
        raise ReconciliationError(
            "Python producer does not consume the merged inputs safely",
            [f"{path}: {issue}" for issue in issues],
        )


def _python_mapping(path: Path, selector: str) -> dict[str, object]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise ReconciliationError("Python producer could not be parsed", [f"{path}: {exc}"]) from exc
    assignments: list[ast.Assign | ast.AnnAssign] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == selector for target in targets):
            assignments.append(node)
    if len(assignments) != 1:
        raise ReconciliationError(
            "Python producer selector must have one literal assignment",
            [f"{path}::{selector}: found {len(assignments)} assignments"],
        )

    trusted_import_aliases: set[int] = set()
    for node in tree.body:
        if not (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "asset_io"
        ):
            continue
        for alias in node.names:
            if alias.name == "merged" and alias.asname is None:
                trusted_import_aliases.add(id(alias))
    if len(trusted_import_aliases) != 1:
        raise ReconciliationError(
            "Python producer must import the trusted merged() helper",
            [f"{path}: expected exactly `from asset_io import merged`"],
        )

    import_issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                signature = (alias.name, alias.asname)
                if signature not in {("cadquery", "cq"), ("math", None)}:
                    import_issues.append(
                        f"line {node.lineno}: import {alias.name} is unsupported"
                    )
        elif isinstance(node, ast.ImportFrom):
            allowed_names: set[str]
            if node.level == 0 and node.module == "__future__":
                allowed_names = {"annotations"}
            elif node.level == 0 and node.module == "asset_io":
                allowed_names = {"export_shape", "merged"}
            else:
                allowed_names = set()
            for alias in node.names:
                if alias.name not in allowed_names or alias.asname is not None:
                    import_issues.append(
                        f"line {node.lineno}: from {node.module or '.'} "
                        f"import {alias.name} is unsupported"
                    )
    if import_issues:
        raise ReconciliationError(
            "Python producer imports outside the supported geometry subset",
            [f"{path}: {issue}" for issue in import_issues],
        )

    assignment = assignments[0]
    assignment_targets = (
        assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
    )
    if len(assignment_targets) != 1 or not (
        isinstance(assignment_targets[0], ast.Name)
        and assignment_targets[0].id == selector
    ):
        raise ReconciliationError(
            "Python producer selector must have one unaliased assignment",
            [f"{path}::{selector}"],
        )

    build, supported_call, result_name = _canonical_python_build_call(
        tree,
        path,
        selector,
    )
    allowed_reads = {supported_call.args[1]}
    selector_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == selector
        and isinstance(node.ctx, ast.Load)
    ]
    unsupported_reads = [node for node in selector_reads if node not in allowed_reads]
    if unsupported_reads or not allowed_reads:
        lines = ", ".join(str(node.lineno) for node in unsupported_reads) or "none"
        raise ReconciliationError(
            "Python producer selector escapes the supported merged() read",
            [f"{path}::{selector}: unsupported line(s) {lines}"],
        )

    merged_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "merged"
        and isinstance(node.ctx, ast.Load)
    ]
    unsupported_merged_reads = [
        node for node in merged_reads if node is not supported_call.func
    ]
    if unsupported_merged_reads:
        lines = ", ".join(str(node.lineno) for node in unsupported_merged_reads)
        raise ReconciliationError(
            "Python producer escapes the trusted merged() call",
            [f"{path}: unsupported line(s) {lines}"],
        )

    parameter_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "parameters"
        and isinstance(node.ctx, ast.Load)
    ]
    unsupported_parameter_reads = [
        node for node in parameter_reads if node is not supported_call.args[0]
    ]
    parameter_bindings = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Name)
            and node.id == "parameters"
            and isinstance(node.ctx, ast.Store | ast.Del)
        )
        or (
            isinstance(node, ast.arg)
            and node.arg == "parameters"
            and node is not build.args.args[0]
        )
    ]
    if unsupported_parameter_reads or parameter_bindings:
        lines = sorted(
            {
                str(node.lineno)
                for node in unsupported_parameter_reads + parameter_bindings
            }
        )
        raise ReconciliationError(
            "Python producer mutates or escapes the build parameters",
            [f"{path}: unsupported line(s) {', '.join(lines)}"],
        )

    binding_issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.alias):
            bound_name = node.asname or node.name.split(".", 1)[0]
            if bound_name == "merged" and id(node) not in trusted_import_aliases:
                binding_issues.append(
                    f"line {getattr(node, 'lineno', '?')}: untrusted merged import"
                )
            elif bound_name == "build":
                binding_issues.append(
                    f"line {getattr(node, 'lineno', '?')}: build is shadowed by an import"
                )
        elif (
            isinstance(node, ast.Name)
            and node.id in {"build", "merged"}
            and isinstance(node.ctx, ast.Store | ast.Del)
        ):
            binding_issues.append(f"line {node.lineno}: {node.id} is rebound")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name == "merged":
                binding_issues.append(f"line {node.lineno}: merged is redefined")
            elif node.name == "build" and node is not build:
                binding_issues.append(f"line {node.lineno}: build is redefined")
        elif isinstance(node, ast.arg) and node.arg in {"build", "merged"}:
            binding_issues.append(
                f"line {node.lineno}: {node.arg} is shadowed by an argument"
            )
        elif isinstance(node, ast.ExceptHandler) and node.name in {"build", "merged"}:
            binding_issues.append(
                f"line {node.lineno}: {node.name} is shadowed by an exception"
            )
        elif isinstance(node, ast.MatchAs | ast.MatchStar) and node.name in {
            "build",
            "merged",
        }:
            binding_issues.append(
                f"line {node.lineno}: {node.name} is shadowed by a pattern"
            )
        elif isinstance(node, ast.Global | ast.Nonlocal) and set(node.names) & {
            "build",
            "merged",
        }:
            binding_issues.append(f"line {node.lineno}: protected name uses dynamic scope")
    if binding_issues:
        raise ReconciliationError(
            "Python producer rebinds the trusted merged() helper",
            [f"{path}: {issue}" for issue in binding_issues],
        )

    dynamic_issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and (
            (
                isinstance(node.ctx, ast.Load)
                and node.id in PYTHON_REFLECTION_NAMES
            )
            or (
                node.id.startswith("__")
                and node.id.endswith("__")
                and node.id != "__name__"
            )
        ):
            dynamic_issues.append(f"line {node.lineno}: {node.id}")
        elif isinstance(node, ast.Attribute) and (
            node.attr in PYTHON_INTROSPECTION_ATTRIBUTES
            or (node.attr.startswith("__") and node.attr.endswith("__"))
        ):
            dynamic_issues.append(f"line {node.lineno}: {node.attr}")
        elif isinstance(node, ast.Constant) and node.value in {
            "build",
            "merged",
            "parameters",
            selector,
        }:
            dynamic_issues.append(f"line {node.lineno}: dynamic binding lookup")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {
                "__delattr__",
                "__delitem__",
                "__setattr__",
                "__setitem__",
            }
        ):
            dynamic_issues.append(f"line {node.lineno}: {node.func.attr}")
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        if any(isinstance(target, ast.Attribute | ast.Subscript) for target in targets):
            dynamic_issues.append(f"line {node.lineno}: indirect object mutation")
    if dynamic_issues:
        raise ReconciliationError(
            "Python producer uses unsupported dynamic access",
            [f"{path}: {issue}" for issue in dynamic_issues],
        )
    for name in ast.walk(tree):
        if (
            isinstance(name, ast.Name)
            and name.id == selector
            and isinstance(name.ctx, ast.Store | ast.Del)
            and name is not assignment_targets[0]
        ):
            raise ReconciliationError(
                "Python producer selector is rebound after declaration",
                [f"{path}::{selector} at line {name.lineno}"],
            )

    mutation_methods = {"clear", "pop", "popitem", "setdefault", "update"}
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        for target in targets:
            root = target
            while isinstance(root, ast.Subscript | ast.Attribute):
                root = root.value
            is_declaration = target is assignment_targets[0] and node is assignment
            if (
                isinstance(root, ast.Name)
                and root.id == selector
                and not is_declaration
            ):
                raise ReconciliationError(
                    "Python producer selector is mutated after declaration",
                    [f"{path}::{selector} at line {node.lineno}"],
                )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == selector
            and node.func.attr in mutation_methods
        ):
            raise ReconciliationError(
                "Python producer selector is mutated after declaration",
                [f"{path}::{selector}.{node.func.attr} at line {node.lineno}"],
            )

    try:
        value = ast.literal_eval(assignment.value)
    except (ValueError, TypeError) as exc:
        raise ReconciliationError(
            "Python producer selector is not a literal mapping",
            [f"{path}::{selector}: {exc}"],
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ReconciliationError(
            "Python producer selector is invalid",
            [f"{path}::{selector} must be a string-keyed mapping"],
        )
    _validate_python_mapping_consumption(
        build,
        result_name,
        value,
        path,
    )
    return value


def _python_string_assignment(path: Path, selector: str) -> str:
    """Read one module-level literal string assignment without importing code."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise ReconciliationError("Python producer could not be parsed", [f"{path}: {exc}"]) from exc
    assignments: list[ast.Assign | ast.AnnAssign] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == selector for target in targets):
            assignments.append(node)
    if len(assignments) != 1:
        raise ReconciliationError(
            "Python producer selector must have one literal assignment",
            [f"{path}::{selector}: found {len(assignments)} assignments"],
        )
    try:
        value = ast.literal_eval(assignments[0].value)
    except (ValueError, TypeError) as exc:
        raise ReconciliationError(
            "Python producer selector is not a literal string",
            [f"{path}::{selector}: {exc}"],
        ) from exc
    if not isinstance(value, str) or not value:
        raise ReconciliationError(
            "Python producer selector is not a literal string",
            [f"{path}::{selector}"],
        )
    return value


def _strip_openscad_comments(text: str, path: Path) -> str:
    """Remove comments without interpreting markers inside string literals."""

    result: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            result.extend((" ", " "))
            index += 2
            while index < len(text) and text[index] != "\n":
                result.append(" ")
                index += 1
            continue
        if char == "/" and following == "*":
            result.extend((" ", " "))
            index += 2
            while index < len(text) and not (
                text[index] == "*"
                and index + 1 < len(text)
                and text[index + 1] == "/"
            ):
                result.append("\n" if text[index] == "\n" else " ")
                index += 1
            if index >= len(text):
                raise ReconciliationError(
                    "OpenSCAD producer has an unterminated block comment",
                    [str(path)],
                )
            result.extend((" ", " "))
            index += 2
            continue
        result.append(char)
        index += 1
    if in_string:
        raise ReconciliationError(
            "OpenSCAD producer has an unterminated string literal",
            [str(path)],
        )
    return "".join(result)


def _has_openscad_include_directive(text: str) -> bool:
    """Detect include/use tokens anywhere outside OpenSCAD string literals."""

    index = 0
    in_string = False
    escaped = False
    name_characters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        for keyword in ("include", "use"):
            end = index + len(keyword)
            if not text.startswith(keyword, index):
                continue
            before_is_name = index > 0 and text[index - 1] in name_characters
            after_is_name = end < len(text) and text[end] in name_characters
            if before_is_name or after_is_name:
                continue
            cursor = end
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor < len(text) and text[cursor] == "<":
                return True
        index += 1
    return False


def _openscad_top_level_statements(text: str, path: Path) -> list[str]:
    """Return semicolon-terminated statements outside braces and comments."""

    statements: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if depth == 0:
                current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            if depth == 0:
                current.append(char)
            continue
        if char == "{":
            if depth == 0:
                current.clear()
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                raise ReconciliationError(
                    "OpenSCAD producer has an unmatched closing brace",
                    [str(path)],
                )
            depth -= 1
            if depth == 0:
                current.clear()
            continue
        if depth != 0:
            continue
        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current.clear()
        else:
            current.append(char)
    if depth:
        raise ReconciliationError(
            "OpenSCAD producer has an unterminated brace scope",
            [str(path)],
        )
    trailing = "".join(current).strip()
    if trailing and SCAD_DECLARATION.fullmatch(trailing):
        raise ReconciliationError(
            "OpenSCAD top-level assignment is missing a semicolon",
            [f"{path}: {trailing}"],
        )
    return statements


def _openscad_assignments(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReconciliationError("OpenSCAD producer could not be read", [f"{path}: {exc}"]) from exc
    stripped = _strip_openscad_comments(text, path)
    if _has_openscad_include_directive(stripped):
        raise ReconciliationError(
            "OpenSCAD producer cannot use unscanned include/use directives",
            [str(path)],
        )
    assignments: dict[str, object] = {}
    for statement in _openscad_top_level_statements(stripped, path):
        declaration = SCAD_DECLARATION.fullmatch(statement)
        if declaration is None:
            continue
        numeric = SCAD_NUMERIC_ASSIGNMENT.fullmatch(statement)
        if numeric is None:
            raise ReconciliationError(
                "OpenSCAD top-level inputs must use finite numeric literals",
                [f"{path}: {declaration.group(1)} = {declaration.group(2)}"],
            )
        name, raw_value = numeric.groups()
        if name in assignments:
            raise ReconciliationError(
                "OpenSCAD producer repeats a top-level input",
                [f"{path}: {name}"],
            )
        try:
            value = _parse_finite_float(raw_value)
        except ValueError as exc:
            raise ReconciliationError(
                "OpenSCAD top-level input is outside the finite numeric range",
                [f"{path}: {name} = {raw_value}"],
            ) from exc
        assignments[name] = int(value) if value.is_integer() else value
    if not assignments:
        raise ReconciliationError(
            "OpenSCAD producer has no top-level numeric inputs", [str(path)]
        )
    return assignments


def _producer_values(producer: JSONObject) -> dict[str, object]:
    path = _source_path(producer["path"])
    if producer["adapter"] == "python_mapping":
        asset_id = _python_string_assignment(path, "ASSET_ID")
        if asset_id != producer["subject"]["id"]:
            raise ReconciliationError(
                "Python producer asset identity does not match the contract",
                [
                    f"{path}::ASSET_ID is {asset_id!r}; expected "
                    f"{producer['subject']['id']!r}"
                ],
            )
        return _python_mapping(path, producer["selector"])
    if producer["adapter"] == "openscad_assignments":
        return _openscad_assignments(path)
    raise ReconciliationError(
        "Unsupported reconciliation adapter",
        [f"{producer['producer_id']}: {producer['adapter']}"],
    )


def _subject_parameters(project: ProjectSpec, subject: JSONObject) -> Mapping[str, object]:
    if subject["kind"] != "asset_type":
        raise ReconciliationError(
            "Producer subject is unsupported",
            [f"producer adapters currently require asset_type, found {subject['kind']}"],
        )
    try:
        return project.asset_types_by_id[subject["id"]].parameters
    except KeyError as exc:
        raise ReconciliationError(
            "Producer subject is unknown", [f"asset_type {subject['id']}"]
        ) from exc


def _full_endpoint_path(endpoint: JSONObject) -> str:
    collection = "asset_types" if endpoint["kind"] == "asset_type" else "occurrences"
    return f"$.{collection}[{endpoint['id']}].{endpoint['path']}"


def _endpoint_value(project: ProjectSpec, endpoint: JSONObject) -> object:
    kind = endpoint["kind"]
    identifier = endpoint["id"]
    path = endpoint["path"]
    if kind == "asset_type":
        try:
            item = project.asset_types_by_id[identifier]
        except KeyError as exc:
            raise ReconciliationError("Relation endpoint is unknown", [f"asset_type {identifier}"]) from exc
        if not path.startswith("parameters."):
            raise ReconciliationError(
                "Relation endpoint path is invalid",
                [f"asset_type {identifier} cannot resolve {path}"],
            )
        parameter = path.removeprefix("parameters.")
        try:
            return item.parameters[parameter]
        except KeyError as exc:
            raise ReconciliationError(
                "Relation parameter is unknown", [f"asset_type {identifier}.{parameter}"]
            ) from exc

    if kind == "occurrence":
        try:
            item = project.occurrences_by_id[identifier]
        except KeyError as exc:
            raise ReconciliationError("Relation endpoint is unknown", [f"occurrence {identifier}"]) from exc
        match = INDEXED_PATH.fullmatch(path)
        if match is None:
            raise ReconciliationError(
                "Relation endpoint path is invalid",
                [f"occurrence {identifier} cannot resolve {path}"],
            )
        values = item.dimensions_mm if match.group(1) == "dimensions_mm" else item.origin_mm
        index = int(match.group(2))
        if index >= len(values):
            raise ReconciliationError(
                "Relation endpoint index is invalid", [f"occurrence {identifier}.{path}"]
            )
        return values[index]

    raise ReconciliationError("Relation endpoint kind is unsupported", [str(kind)])


def _unit(parameter: str) -> str:
    if "_mm" in parameter:
        return "mm"
    if parameter.endswith("_count"):
        return "count"
    return "scalar"


def _matches(expected: object, actual: object, tolerance: float) -> bool:
    return _is_number(expected) and _is_number(actual) and math.isclose(
        float(expected), float(actual), rel_tol=0.0, abs_tol=tolerance
    )


def _transform(value: object, transform: JSONObject | None) -> object:
    if not _is_number(value):
        raise ReconciliationError("Relation source is not numeric", [repr(value)])
    if transform is None or transform["operator"] == "identity":
        return value
    operator = transform["operator"]
    operand = transform["operand"]
    if not _is_number(operand):
        raise ReconciliationError("Relation transform operand is not numeric", [repr(operand)])
    left = float(value)
    right = float(operand)
    if operator == "divide":
        if right == 0:
            raise ReconciliationError(
                "Relation transform divides by zero",
                ["divide operand must be nonzero"],
            )
        return left / right
    if operator == "multiply":
        return left * right
    if operator == "add":
        return left + right
    if operator == "subtract":
        return left - right
    raise ReconciliationError("Relation transform is unsupported", [str(operator)])


def _failed_result(failures: Sequence[str]) -> dict[str, object]:
    return {
        "name": "Parameter Reconciliation",
        "status": "failed",
        "summary": {
            "contract_schema_version": "unavailable",
            "producer_count": 0,
            "required_producer_count": 0,
            "relation_count": 0,
            "row_count": 0,
            "passed_row_count": 0,
            "failed_row_count": 0,
            "scoped_numeric_parameter_count": 0,
            "covered_numeric_parameter_count": 0,
            "producer_input_count": 0,
            "covered_producer_input_count": 0,
            "excluded_producer_input_count": 0,
            "producer_error_count": 0,
            "failure_count": len(failures),
        },
        "failures": list(failures),
        "warnings": [],
        "rows": [],
    }


def _scoped_error_messages(
    scope: str,
    identifier: str,
    error: ReconciliationError,
) -> list[str]:
    prefix = f"[{scope}] {identifier}"
    return [
        f"{prefix}: {error.heading}",
        *(f"{prefix}: {issue}" for issue in error.issues),
    ]


def reconcile(
    project_spec_path: str | Path | None = None,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, object]:
    """Return deterministic reconciliation evidence without modifying artifacts."""

    resolved_contract_path = Path(contract_path).resolve()
    try:
        contract = load_contract(resolved_contract_path)
        resolved_project_path = (
            Path(project_spec_path).resolve()
            if project_spec_path is not None
            else _declared_project_spec_path(contract, resolved_contract_path)
        )
        project = load_project_spec(resolved_project_path)
    except (ReconciliationError, ProjectSpecError) as exc:
        issues = getattr(exc, "issues", (str(exc),))
        heading = getattr(exc, "heading", type(exc).__name__)
        return _failed_result([f"[CONTRACT] {heading}: {issue}" for issue in issues])

    failures: list[str] = []
    warnings = [
        "This v1 contract verifies CadQuery fallback mappings and canonical ProjectSpec "
        "forwarding, OpenSCAD literal declarations and deterministic -D injection, and "
        "declared type-to-occurrence relations.",
        "CadQuery parameter-sensitivity tests show that each current numeric input changes "
        "generated geometry, but reconciliation does not prove exact BRep/mesh dimensions "
        "or dimensional parity of committed exports by itself. The separate observed-geometry "
        "gate now checks current IFC, STEP, STL, and selected DXF bounds; FreeCAD assembly "
        "decomposition, unselected drawing entities, and topology remain outside that scope.",
    ]
    rows: list[dict[str, object]] = []
    required_types = {
        asset.type_id: asset
        for asset in project.asset_types
        if asset.group in {"cadquery", "openscad"}
    }
    scoped_parameters: set[tuple[str, str, str]] = {
        ("asset_type", asset_id, name)
        for asset_id, asset in required_types.items()
        for name, value in asset.parameters.items()
        if _is_number(value)
    }
    covered_parameters: set[tuple[str, str, str]] = set()
    producer_inputs: set[tuple[str, str]] = set()
    covered_inputs: set[tuple[str, str]] = set()
    excluded_inputs: set[tuple[str, str]] = set()
    producer_error_count = 0

    contract_subjects = [producer["subject"]["id"] for producer in contract["producers"]]
    duplicate_subjects = _duplicates(contract_subjects)
    if duplicate_subjects:
        failures.append(
            "[DUPLICATE_PRODUCER_SUBJECT] multiple producers cover: "
            + ", ".join(duplicate_subjects)
        )
    missing_subjects = sorted(set(required_types) - set(contract_subjects))
    extra_subjects = sorted(set(contract_subjects) - set(required_types))
    if missing_subjects:
        failures.append(
            "[MISSING_PRODUCER] reconciliation coverage misses ProjectSpec producer type(s): "
            + ", ".join(missing_subjects)
        )
    if extra_subjects:
        failures.append(
            "[UNKNOWN_PRODUCER_SUBJECT] contract covers unsupported ProjectSpec type(s): "
            + ", ".join(extra_subjects)
        )

    for producer in contract["producers"]:
        producer_id = producer["producer_id"]
        subject = producer["subject"]
        try:
            parameters = _subject_parameters(project, subject)
        except ReconciliationError as exc:
            failures.extend(_scoped_error_messages("PRODUCER", producer_id, exc))
            producer_error_count += 1
            continue

        canonical_numeric = {
            name: value for name, value in parameters.items() if _is_number(value)
        }
        asset = required_types.get(subject["id"])
        if asset is not None:
            expected_adapter = (
                "python_mapping" if asset.group == "cadquery" else "openscad_assignments"
            )
            if producer["adapter"] != expected_adapter:
                failures.append(
                    f"[WRONG_PRODUCER_ADAPTER] {producer_id} uses {producer['adapter']}, "
                    f"expected {expected_adapter} for {subject['id']}"
                )

        declared_map = producer["parameter_map"]
        parameter_map = (
            {name: name for name in sorted(canonical_numeric)}
            if declared_map == {"*": "*"}
            else dict(declared_map)
        )
        mapped_canonical = set(parameter_map)
        mapped_producer = set(parameter_map.values())
        excluded = dict(producer.get("excluded_parameters", {}))
        excluded_producer = set(excluded)
        producer_inputs.update((producer_id, name) for name in mapped_producer | excluded_producer)
        excluded_inputs.update((producer_id, name) for name in excluded_producer)

        try:
            observed = _producer_values(producer)
        except ReconciliationError as exc:
            observed = {}
            producer_error_count += 1
            failures.extend(_scoped_error_messages("PRODUCER", producer_id, exc))
        observed_numeric = {
            name: value for name, value in observed.items() if _is_number(value)
        }
        producer_inputs.update((producer_id, name) for name in observed_numeric)

        missing_canonical = sorted(set(canonical_numeric) - mapped_canonical)
        canonical_names = set(parameters)
        unknown_canonical = sorted(mapped_canonical - canonical_names)
        nonnumeric_canonical = sorted(
            mapped_canonical & canonical_names - set(canonical_numeric)
        )
        missing_producer = sorted(
            set(observed_numeric) - mapped_producer - excluded_producer
        )
        unknown_producer = sorted(mapped_producer - set(observed_numeric))
        unknown_exclusions = sorted(excluded_producer - set(observed_numeric))

        for name in missing_canonical:
            failures.append(
                f"[UNMAPPED_CANONICAL_PARAMETER] {producer_id} coverage misses "
                f"{subject['id']}.{name}"
            )
        for name in unknown_canonical:
            failures.append(
                f"[UNKNOWN_CANONICAL_PARAMETER] {producer_id} maps absent "
                f"{subject['id']}.{name}"
            )
        for name in nonnumeric_canonical:
            failures.append(
                f"[NONNUMERIC_CANONICAL_PARAMETER] {producer_id} maps nonnumeric "
                f"{subject['id']}.{name}"
            )
        for name in missing_producer:
            failures.append(
                f"[UNMAPPED_PRODUCER_PARAMETER] {producer_id} coverage misses producer input {name}"
            )
        for name in unknown_producer:
            failures.append(
                f"[UNKNOWN_PRODUCER_PARAMETER] {producer_id} maps absent producer input {name}"
            )
        for name in unknown_exclusions:
            failures.append(
                f"[UNKNOWN_EXCLUDED_PARAMETER] {producer_id} excludes absent producer input {name}"
            )
        covered_inputs.update(
            (producer_id, name) for name in excluded_producer & set(observed_numeric)
        )

        for name in sorted(excluded_producer):
            exclusion_is_observed = name in observed_numeric
            rows.append(
                {
                    "relation_id": f"{producer_id}.excluded.{name}",
                    "subject_kind": subject["kind"],
                    "subject_id": subject["id"],
                    "canonical_path": (
                        f"$.producers[{producer_id}].excluded_parameters.{name}"
                    ),
                    "producer": producer_id,
                    "producer_path": f"{producer['path']}::{name}",
                    "relation": "excluded",
                    "expected": None,
                    "actual": observed_numeric.get(name),
                    "unit": _unit(name),
                    "tolerance_mm": 0.0,
                    "status": "passed" if exclusion_is_observed else "failed",
                    "reason": excluded[name],
                }
            )

        tolerance = float(producer.get("tolerance_mm", contract["default_tolerance_mm"]))
        for canonical_name in sorted(parameter_map):
            producer_name = parameter_map[canonical_name]
            expected = canonical_numeric.get(canonical_name)
            actual = observed_numeric.get(producer_name)
            key = (subject["kind"], subject["id"], canonical_name)
            binding_is_valid = (
                canonical_name in canonical_numeric
                and producer_name in observed_numeric
            )
            if binding_is_valid:
                covered_parameters.add(key)
                covered_inputs.add((producer_id, producer_name))
            passed = binding_is_valid and _matches(expected, actual, tolerance)
            row = {
                "relation_id": f"{producer_id}.{canonical_name}",
                "subject_kind": subject["kind"],
                "subject_id": subject["id"],
                "canonical_path": (
                    f"$.asset_types[{subject['id']}].parameters.{canonical_name}"
                ),
                "producer": producer_id,
                "producer_path": (
                    f"{producer['path']}::"
                    + (
                        f"{producer['selector']}.{producer_name}"
                        if producer["adapter"] == "python_mapping"
                        else producer_name
                    )
                ),
                "relation": "equal",
                "expected": expected,
                "actual": actual,
                "unit": _unit(canonical_name),
                "tolerance_mm": tolerance,
                "status": "passed" if passed else "failed",
                "reason": (
                    ""
                    if binding_is_valid
                    else "Comparison skipped because a binding endpoint is invalid."
                ),
            }
            rows.append(row)
            if binding_is_valid and not passed:
                failures.append(
                    f"[VALUE_MISMATCH] {producer_id} {subject['id']}.{canonical_name}: "
                    f"expected {expected!r}, observed {actual!r} at {row['producer_path']} "
                    f"(tolerance {tolerance})"
                )

    for relation in contract["relations"]:
        relation_id = relation["relation_id"]
        source = relation["from"]
        target = relation["to"]
        classification = relation["classification"]
        tolerance = float(relation.get("tolerance_mm", contract["default_tolerance_mm"]))
        reason = relation.get("reason", "")
        try:
            source_value = _endpoint_value(project, source)
            target_value = _endpoint_value(project, target)
            target_occurrence = project.occurrences_by_id[target["id"]]
            if target_occurrence.type_id != source["id"]:
                raise ReconciliationError(
                    "Relation target occurrence does not instantiate the source type",
                    [
                        f"{relation_id}: {target['id']} has type "
                        f"{target_occurrence.type_id}, expected {source['id']}"
                    ],
                )
            if not _is_number(source_value) or not _is_number(target_value):
                raise ReconciliationError(
                    "Relation endpoints must both resolve to finite numbers",
                    [relation_id],
                )
            expected = _transform(source_value, relation.get("transform"))
            passed = (
                bool(reason.strip()) and not _matches(source_value, target_value, tolerance)
                if classification == "override"
                else _matches(expected, target_value, tolerance)
            )
        except ReconciliationError as exc:
            source_value = None
            target_value = None
            expected = None
            passed = False
            failures.extend(_scoped_error_messages("RELATION", relation_id, exc))

        row = {
            "relation_id": relation_id,
            "subject_kind": target["kind"],
            "subject_id": target["id"],
            "canonical_path": _full_endpoint_path(source),
            "producer": "project_spec.relation",
            "producer_path": _full_endpoint_path(target),
            "relation": classification,
            "expected": expected,
            "actual": target_value,
            "unit": _unit(source["path"]),
            "tolerance_mm": tolerance,
            "status": "passed" if passed else "failed",
            "reason": reason,
        }
        rows.append(row)
        if not passed and source_value is not None:
            failures.append(
                f"[RELATION_MISMATCH] {relation_id}: expected {expected!r}, "
                f"observed {target_value!r} at {row['producer_path']} "
                f"(tolerance {tolerance})"
            )

    rows.sort(
        key=lambda row: (
            str(row["producer"]),
            str(row["subject_kind"]),
            str(row["subject_id"]),
            str(row["canonical_path"]),
            str(row["relation_id"]),
        )
    )
    failed_rows = sum(row["status"] == "failed" for row in rows)
    summary = {
        "contract_schema_version": contract["schema_version"],
        "producer_count": len(contract["producers"]),
        "required_producer_count": len(required_types),
        "relation_count": len(contract["relations"]),
        "row_count": len(rows),
        "passed_row_count": len(rows) - failed_rows,
        "failed_row_count": failed_rows,
        "scoped_numeric_parameter_count": len(scoped_parameters),
        "covered_numeric_parameter_count": len(covered_parameters),
        "producer_input_count": len(producer_inputs),
        "covered_producer_input_count": len(covered_inputs),
        "excluded_producer_input_count": len(excluded_inputs),
        "producer_error_count": producer_error_count,
        "failure_count": len(failures),
    }
    return {
        "name": "Parameter Reconciliation",
        "status": "passed" if not failures and not failed_rows else "failed",
        "summary": summary,
        "failures": failures,
        "warnings": warnings,
        "rows": rows,
    }


def _markdown_value(value: object) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|")


def render_reports(result: Mapping[str, object]) -> tuple[str, str]:
    """Render deterministic CSV and Markdown evidence without filesystem writes."""

    rows = list(result["rows"])
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=ROW_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    status = "PASSED" if result["status"] == "passed" else "FAILED"
    lines = [
        "# Parameter Reconciliation Report",
        "",
        f"Overall Status: **{status}**",
        "",
        "This report compares authoritative ProjectSpec values with declared producer",
        "inputs and explicit type-to-occurrence relationships. No arbitrary expressions",
        "are evaluated; derived values use the contract's small transform vocabulary.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in result["summary"].items():
        lines.append(f"| `{key}` | {value} |")

    lines.extend(["", "## Failures", ""])
    failures = list(result["failures"])
    lines.extend(f"- {failure}" for failure in failures) if failures else lines.append("- None")
    lines.extend(["", "## Scope Warnings", ""])
    warnings = list(result["warnings"])
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- None")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "| Relation | Subject | Canonical | Producer | Relation | Expected | Actual | Status | Reason |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_value(row["relation_id"]),
                    _markdown_value(f"{row['subject_kind']}:{row['subject_id']}"),
                    _markdown_value(row["canonical_path"]),
                    _markdown_value(row["producer_path"]),
                    _markdown_value(row["relation"]),
                    _markdown_value(row["expected"]),
                    _markdown_value(row["actual"]),
                    _markdown_value(row["status"]),
                    _markdown_value(row["reason"]),
                ]
            )
            + " |"
        )
    return csv_buffer.getvalue(), "\n".join(lines) + "\n"


def write_reports(
    result: Mapping[str, object],
    csv_path: str | Path = DEFAULT_CSV_PATH,
    markdown_path: str | Path = DEFAULT_MARKDOWN_PATH,
) -> None:
    """Write deterministic machine-readable and review-friendly evidence reports."""

    csv_target = Path(csv_path)
    markdown_target = Path(markdown_path)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    csv_text, markdown_text = render_reports(result)
    csv_target.write_text(csv_text, encoding="utf-8")
    markdown_target.write_text(markdown_text, encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-spec",
        type=Path,
        default=None,
        help="override the contract-relative ProjectSpec path",
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and print the summary without rewriting reports",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = reconcile(args.project_spec, args.contract)
    if not args.check:
        write_reports(result, args.csv, args.markdown)
        print(f"Wrote {args.csv}")
        print(f"Wrote {args.markdown}")
    print(json.dumps({"status": result["status"], **result["summary"]}, indent=2))
    if result["status"] != "passed":
        for failure in result["failures"]:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
