"""Load and semantically validate the versioned CoordProof ProjectSpec."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Never, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_SPEC_PATH = ROOT / "spec" / "mechanical_room.project.json"
PROJECT_SPEC_SCHEMA_PATH = ROOT / "spec" / "project.schema.json"
SUPPORTED_SCHEMA_VERSION = 1
MAX_REPORTED_ISSUES = 100

JSONObject = dict[str, Any]


class _DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a member name."""


class _NonStandardNumberError(ValueError):
    """Raised for JavaScript number constants that are not valid JSON."""


class ProjectSpecError(ValueError):
    """Raised when a ProjectSpec is structurally or semantically invalid."""

    def __init__(self, heading: str, issues: list[str]) -> None:
        self.heading = heading
        self.issues = tuple(issues)
        super().__init__(heading + "\n" + "\n".join(f"- {issue}" for issue in issues))


@dataclass(frozen=True)
class ProjectMetadata:
    project_id: str
    name: str
    description: str


@dataclass(frozen=True)
class SpatialSpec:
    project_ifc_name: str
    site_ifc_name: str
    building_ifc_name: str
    storey_ifc_name: str
    storey_elevation_mm: float
    space_type_id: str
    space_occurrence_id: str
    space_ifc_name: str
    space_long_name: str
    space_dimensions_mm: tuple[float, float, float]
    semantic_source_tool: str


@dataclass(frozen=True)
class SystemSpec:
    name: str
    long_name: str
    object_type: str
    description: str


@dataclass(frozen=True)
class AssetTypeSpec:
    type_id: str
    catalog_order: int
    group: str
    display_name: str
    category: str
    source_tool: str
    ifc_class: str
    parameters: Mapping[str, object]
    exports: Mapping[str, str]
    notes: str


@dataclass(frozen=True)
class OccurrenceSpec:
    occurrence_id: str
    type_id: str
    ifc_name: str
    material: str
    systems: tuple[str, ...]
    object_type: str
    geometry: str
    origin_mm: tuple[float, float, float]
    dimensions_mm: tuple[float, ...]
    extrusion_axis: tuple[float, float, float]
    ports: tuple[str, ...]
    port_systems: Mapping[str, str]
    properties: Mapping[str, object]


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    catalog_order: int
    group: str
    display_name: str
    category: str
    source_tool: str
    ifc_class: str
    parameters: Mapping[str, object]
    exports: Mapping[str, str]
    notes: str


@dataclass(frozen=True)
class EndpointSpec:
    occurrence_id: str
    port: str


@dataclass(frozen=True)
class ConnectionSpec:
    connection_id: str
    system: str
    source: EndpointSpec
    target: EndpointSpec
    name: str
    realizing_occurrence_id: str | None = None


@dataclass(frozen=True)
class RequirementsSpec:
    categories: frozenset[str]
    asset_ids: frozenset[str]


@dataclass(frozen=True)
class CatalogRecord:
    asset_id: str
    catalog_order: int
    group: str
    display_name: str
    category: str
    source_tool: str
    ifc_class: str
    parameters: Mapping[str, object]
    exports: Mapping[str, str]
    notes: str


@dataclass(frozen=True)
class ProjectSpec:
    schema_version: int
    project: ProjectMetadata
    units: str
    spatial: SpatialSpec
    systems: tuple[SystemSpec, ...]
    asset_types: tuple[AssetTypeSpec, ...]
    occurrences: tuple[OccurrenceSpec, ...]
    artifacts: tuple[ArtifactSpec, ...]
    connections: tuple[ConnectionSpec, ...]
    requirements: RequirementsSpec
    source_path: Path

    @property
    def system_names(self) -> tuple[str, ...]:
        return tuple(system.name for system in self.systems)

    @property
    def asset_types_by_id(self) -> dict[str, AssetTypeSpec]:
        return {asset.type_id: asset for asset in self.asset_types}

    @property
    def occurrences_by_id(self) -> dict[str, OccurrenceSpec]:
        return {occurrence.occurrence_id: occurrence for occurrence in self.occurrences}

    @property
    def artifacts_by_id(self) -> dict[str, ArtifactSpec]:
        return {artifact.artifact_id: artifact for artifact in self.artifacts}

    def catalog_records(self) -> tuple[CatalogRecord, ...]:
        records = [
            CatalogRecord(
                asset_id=asset.type_id,
                catalog_order=asset.catalog_order,
                group=asset.group,
                display_name=asset.display_name,
                category=asset.category,
                source_tool=asset.source_tool,
                ifc_class=asset.ifc_class,
                parameters=asset.parameters,
                exports=asset.exports,
                notes=asset.notes,
            )
            for asset in self.asset_types
        ]
        records.extend(
            CatalogRecord(
                asset_id=artifact.artifact_id,
                catalog_order=artifact.catalog_order,
                group=artifact.group,
                display_name=artifact.display_name,
                category=artifact.category,
                source_tool=artifact.source_tool,
                ifc_class=artifact.ifc_class,
                parameters=artifact.parameters,
                exports=artifact.exports,
                notes=artifact.notes,
            )
            for artifact in self.artifacts
        )
        return tuple(sorted(records, key=lambda record: record.catalog_order))

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project.project_id,
            "units": self.units,
            "asset_type_count": len(self.asset_types),
            "occurrence_count": len(self.occurrences),
            "artifact_count": len(self.artifacts),
            "catalog_record_count": len(self.catalog_records()),
            "system_count": len(self.systems),
            "connection_count": len(self.connections),
            "declared_port_count": sum(len(item.ports) for item in self.occurrences),
        }


def _json_path(parts: Iterable[object]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> JSONObject:
    result: JSONObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> Never:
    raise _NonStandardNumberError(f"non-standard number constant {value!r}")


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise _NonStandardNumberError(f"number is outside the supported finite range: {value!r}")
    return number


def _parse_supported_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise _NonStandardNumberError("integer is outside the supported parsing range") from exc
    try:
        finite_as_float = math.isfinite(float(number))
    except OverflowError:
        finite_as_float = False
    if not finite_as_float:
        raise _NonStandardNumberError("integer is outside the supported finite range")
    return number


def _load_json(path: Path, *, document_name: str = "ProjectSpec") -> JSONObject:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectSpecError(
            f"{document_name} could not be loaded", [f"file not found: {path}"]
        ) from exc
    except UnicodeDecodeError as exc:
        raise ProjectSpecError(
            f"{document_name} could not be loaded",
            [f"file is not valid UTF-8: {path} ({exc})"],
        ) from exc
    except OSError as exc:
        raise ProjectSpecError(f"{document_name} could not be loaded", [f"{path}: {exc}"]) from exc

    try:
        data = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
            parse_float=_parse_finite_float,
            parse_int=_parse_supported_int,
        )
    except json.JSONDecodeError as exc:
        raise ProjectSpecError(
            f"{document_name} JSON is invalid",
            [f"line {exc.lineno}, column {exc.colno}: {exc.msg}"],
        ) from exc
    except (_DuplicateKeyError, _NonStandardNumberError) as exc:
        raise ProjectSpecError(f"{document_name} JSON is invalid", [str(exc)]) from exc
    except RecursionError as exc:
        raise ProjectSpecError(
            f"{document_name} JSON is invalid", ["document nesting is too deep"]
        ) from exc
    if not isinstance(data, dict):
        raise ProjectSpecError(f"{document_name} JSON is invalid", ["$ must be a JSON object"])
    return data


def _validate_schema(payload: JSONObject) -> None:
    version = payload.get("schema_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != SUPPORTED_SCHEMA_VERSION
    ):
        raise ProjectSpecError(
            "ProjectSpec version is unsupported",
            [f"$.schema_version: expected {SUPPORTED_SCHEMA_VERSION}, found {version!r}"],
        )
    schema = _load_json(PROJECT_SPEC_SCHEMA_PATH, document_name="ProjectSpec schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        schema_path = _json_path(exc.absolute_path)
        raise ProjectSpecError(
            "ProjectSpec schema is invalid", [f"{schema_path}: {exc.message}"]
        ) from exc
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (_json_path(error.absolute_path), error.message),
    )
    if errors:
        issues = [
            f"{_json_path(error.absolute_path)}: {error.message}"
            for error in errors[:MAX_REPORTED_ISSUES]
        ]
        if len(errors) > MAX_REPORTED_ISSUES:
            issues.append(
                f"... {len(errors) - MAX_REPORTED_ISSUES} additional schema error(s) omitted"
            )
        raise ProjectSpecError("ProjectSpec schema validation failed", issues)


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _safe_export_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
        and ":" not in value
        and "\\" not in value
        and not path.is_absolute()
        and path != PurePosixPath(".")
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _validate_semantics(payload: JSONObject) -> None:
    issues: list[str] = []
    asset_types = payload["asset_types"]
    occurrences = payload["occurrences"]
    artifacts = payload["artifacts"]
    systems = payload["systems"]
    connections = payload["connections"]
    requirements = payload["requirements"]
    spatial = payload["spatial"]

    type_ids = [item["type_id"] for item in asset_types]
    occurrence_ids = [item["occurrence_id"] for item in occurrences]
    artifact_ids = [item["artifact_id"] for item in artifacts]
    system_names = [item["name"] for item in systems]
    connection_ids = [item["connection_id"] for item in connections]
    ifc_names = [item["ifc_name"] for item in occurrences]

    for label, values in (
        ("asset type", type_ids),
        ("occurrence", occurrence_ids),
        ("artifact", artifact_ids),
        ("system", system_names),
        ("connection", connection_ids),
        ("occurrence IFC name", ifc_names),
    ):
        duplicates = _duplicates(values)
        if duplicates:
            issues.append(f"[DUPLICATE_ID] duplicate {label} value(s): {', '.join(duplicates)}")

    catalog_ids = type_ids + artifact_ids
    overlapping_catalog_ids = sorted(set(type_ids) & set(artifact_ids))
    if overlapping_catalog_ids:
        issues.append(
            "[DUPLICATE_ID] asset types and artifacts share catalog ID(s): "
            + ", ".join(overlapping_catalog_ids)
        )
    orders = [item["catalog_order"] for item in [*asset_types, *artifacts]]
    if sorted(orders) != list(range(len(orders))):
        issues.append(
            "[CATALOG_ORDER] catalog_order values must be unique and contiguous from zero"
        )

    type_by_id = {item["type_id"]: item for item in asset_types}
    occurrence_by_id = {item["occurrence_id"]: item for item in occurrences}
    known_systems = set(system_names)

    for item in [*asset_types, *artifacts]:
        item_id = item.get("type_id", item.get("artifact_id"))
        for name, value in item["parameters"].items():
            if name.endswith("_mm") and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                issues.append(
                    f"[INVALID_PARAMETER] {item_id}.{name} must be a finite positive number"
                )
            if name.endswith("_count") and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                issues.append(f"[INVALID_PARAMETER] {item_id}.{name} must be an integer >= 1")
        for export_name, export_path in item["exports"].items():
            if not _safe_export_path(export_path):
                issues.append(
                    f"[UNSAFE_EXPORT_PATH] {item_id}.exports.{export_name}: {export_path!r}"
                )

    for occurrence in occurrences:
        occurrence_id = occurrence["occurrence_id"]
        if occurrence["type_id"] not in type_by_id:
            issues.append(
                f"[UNKNOWN_REFERENCE] {occurrence_id} uses unknown type {occurrence['type_id']}"
            )
        unknown_systems = sorted(set(occurrence["systems"]) - known_systems)
        if unknown_systems:
            issues.append(
                f"[UNKNOWN_REFERENCE] {occurrence_id} uses unknown system(s): "
                + ", ".join(unknown_systems)
            )
        ports = set(occurrence["ports"])
        bindings = occurrence["port_systems"]
        missing_bindings = sorted(ports - bindings.keys())
        extra_bindings = sorted(bindings.keys() - ports)
        if missing_bindings:
            issues.append(
                f"[PORT_SYSTEM_BINDING] {occurrence_id} ports missing system binding: "
                + ", ".join(missing_bindings)
            )
        if extra_bindings:
            issues.append(
                f"[UNKNOWN_PORT] {occurrence_id} has bindings for unknown ports: "
                + ", ".join(extra_bindings)
            )
        for port, system in bindings.items():
            if system not in known_systems:
                issues.append(
                    f"[UNKNOWN_REFERENCE] {occurrence_id}.{port} binds to unknown system {system}"
                )
            if system not in occurrence["systems"]:
                issues.append(
                    f"[SYSTEM_MEMBERSHIP] {occurrence_id}.{port} binds to {system}, "
                    "but the occurrence is not a member"
                )
        origin = occurrence["origin_mm"]
        if not all(math.isfinite(float(value)) for value in origin):
            issues.append(f"[INVALID_GEOMETRY] {occurrence_id} origin_mm must be finite")
        dimensions = occurrence["dimensions_mm"]
        if not all(math.isfinite(float(value)) and float(value) > 0 for value in dimensions):
            issues.append(
                f"[INVALID_GEOMETRY] {occurrence_id} dimensions_mm must be finite and positive"
            )
        axis = occurrence["extrusion_axis"]
        if not all(math.isfinite(float(value)) for value in axis):
            issues.append(f"[INVALID_AXIS] {occurrence_id} extrusion_axis must be finite")
        elif math.isclose(sum(float(value) ** 2 for value in axis), 0.0, abs_tol=1e-12):
            issues.append(f"[INVALID_AXIS] {occurrence_id} extrusion_axis cannot be zero")

    if not math.isfinite(float(spatial["storey_elevation_mm"])):
        issues.append("[INVALID_GEOMETRY] spatial.storey_elevation_mm must be finite")

    space_type = type_by_id.get(spatial["space_type_id"])
    if space_type is None:
        issues.append(f"[UNKNOWN_REFERENCE] spatial.space_type_id: {spatial['space_type_id']}")
    elif space_type["ifc_class"] != "IfcSpace":
        issues.append(
            "[SPATIAL_CONTRACT] spatial.space_type_id must reference an IfcSpace asset type"
        )
    space_occurrence = occurrence_by_id.get(spatial["space_occurrence_id"])
    if space_occurrence is None:
        issues.append(
            f"[UNKNOWN_REFERENCE] spatial.space_occurrence_id: {spatial['space_occurrence_id']}"
        )
    else:
        if space_occurrence["type_id"] != spatial["space_type_id"]:
            issues.append("[SPATIAL_CONTRACT] spatial space type and occurrence do not match")
        if space_occurrence["geometry"] != "box":
            issues.append("[SPATIAL_CONTRACT] spatial space occurrence must use box geometry")
        if space_occurrence["ifc_name"] != spatial["space_ifc_name"]:
            issues.append("[SPATIAL_CONTRACT] spatial and occurrence IFC names do not match")
        if space_occurrence["dimensions_mm"] != spatial["space_dimensions_mm"]:
            issues.append("[SPATIAL_CONTRACT] spatial and occurrence dimensions do not match")

    connection_names = [item["name"] for item in connections]
    duplicate_connection_names = _duplicates(connection_names)
    if duplicate_connection_names:
        issues.append(
            "[DUPLICATE_ID] duplicate connection name(s): " + ", ".join(duplicate_connection_names)
        )
    seen_connections: set[tuple[str, tuple[str, str], tuple[str, str]]] = set()
    connected_ports: dict[tuple[str, str], str] = {}
    for connection in connections:
        connection_id = connection["connection_id"]
        system = connection["system"]
        if system not in known_systems:
            issues.append(f"[UNKNOWN_REFERENCE] {connection_id} uses unknown system {system}")
        endpoints: list[tuple[str, str]] = []
        for endpoint_name in ("from", "to"):
            endpoint = connection[endpoint_name]
            occurrence = occurrence_by_id.get(endpoint["occurrence_id"])
            endpoint_key = (endpoint["occurrence_id"], endpoint["port"])
            endpoints.append(endpoint_key)
            previous_connection = connected_ports.get(endpoint_key)
            if previous_connection is not None:
                issues.append(
                    f"[PORT_ALREADY_CONNECTED] {connection_id}.{endpoint_name} reuses "
                    f"{endpoint['occurrence_id']}.{endpoint['port']} from {previous_connection}"
                )
            else:
                connected_ports[endpoint_key] = connection_id
            if occurrence is None:
                issues.append(
                    f"[UNKNOWN_REFERENCE] {connection_id}.{endpoint_name} uses unknown occurrence "
                    f"{endpoint['occurrence_id']}"
                )
                continue
            if endpoint["port"] not in occurrence["ports"]:
                issues.append(
                    f"[UNKNOWN_PORT] {connection_id}.{endpoint_name}: "
                    f"{endpoint['occurrence_id']}.{endpoint['port']}"
                )
            elif occurrence["port_systems"].get(endpoint["port"]) != system:
                issues.append(
                    f"[SYSTEM_MEMBERSHIP] {connection_id}.{endpoint_name} is not bound to {system}"
                )
        if endpoints[0] == endpoints[1]:
            issues.append(f"[SELF_CONNECTION] {connection_id} connects a port to itself")
        normalized = (system, *sorted(endpoints))
        if normalized in seen_connections:
            issues.append(f"[DUPLICATE_CONNECTION] {connection_id} repeats an existing connection")
        seen_connections.add(normalized)
        realizing = connection.get("realizing_occurrence_id")
        if realizing and realizing not in occurrence_by_id:
            issues.append(
                f"[UNKNOWN_REFERENCE] {connection_id} realizing occurrence {realizing} does not exist"
            )

    required_ids = set(requirements["asset_ids"])
    missing_required_ids = sorted(required_ids - set(catalog_ids))
    if missing_required_ids:
        issues.append(
            "[UNKNOWN_REFERENCE] required asset IDs missing: " + ", ".join(missing_required_ids)
        )
    catalog_categories = {item["category"] for item in [*asset_types, *artifacts]}
    missing_categories = sorted(set(requirements["categories"]) - catalog_categories)
    if missing_categories:
        issues.append(
            "[UNKNOWN_REFERENCE] required categories missing: " + ", ".join(missing_categories)
        )

    if issues:
        reported_issues = issues[:MAX_REPORTED_ISSUES]
        if len(issues) > MAX_REPORTED_ISSUES:
            reported_issues.append(
                f"... {len(issues) - MAX_REPORTED_ISSUES} additional semantic error(s) omitted"
            )
        raise ProjectSpecError("ProjectSpec semantic validation failed", reported_issues)


def _deep_freeze(value: Any) -> object:
    """Return an immutable representation of a validated JSON value."""

    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _deep_freeze(dict(value)))


def _construct(payload: JSONObject, source_path: Path) -> ProjectSpec:
    project = ProjectMetadata(**payload["project"])
    spatial_payload = dict(payload["spatial"])
    spatial_payload["space_dimensions_mm"] = tuple(spatial_payload["space_dimensions_mm"])
    spatial = SpatialSpec(**spatial_payload)
    systems = tuple(SystemSpec(**item) for item in payload["systems"])
    asset_type_models: list[AssetTypeSpec] = []
    for item in payload["asset_types"]:
        values = dict(item)
        values["parameters"] = _freeze_mapping(values["parameters"])
        values["exports"] = _freeze_mapping(values["exports"])
        asset_type_models.append(AssetTypeSpec(**values))

    occurrence_models: list[OccurrenceSpec] = []
    for item in payload["occurrences"]:
        values = dict(item)
        for key in ("systems", "origin_mm", "dimensions_mm", "extrusion_axis", "ports"):
            values[key] = tuple(values[key])
        values["port_systems"] = _freeze_mapping(values["port_systems"])
        values["properties"] = _freeze_mapping(values["properties"])
        occurrence_models.append(OccurrenceSpec(**values))

    artifact_models: list[ArtifactSpec] = []
    for item in payload["artifacts"]:
        values = dict(item)
        values["parameters"] = _freeze_mapping(values["parameters"])
        values["exports"] = _freeze_mapping(values["exports"])
        artifact_models.append(ArtifactSpec(**values))
    connection_models: list[ConnectionSpec] = []
    for item in payload["connections"]:
        connection_models.append(
            ConnectionSpec(
                connection_id=item["connection_id"],
                system=item["system"],
                source=EndpointSpec(**item["from"]),
                target=EndpointSpec(**item["to"]),
                name=item["name"],
                realizing_occurrence_id=item.get("realizing_occurrence_id"),
            )
        )
    requirements = RequirementsSpec(
        categories=frozenset(payload["requirements"]["categories"]),
        asset_ids=frozenset(payload["requirements"]["asset_ids"]),
    )
    return ProjectSpec(
        schema_version=payload["schema_version"],
        project=project,
        units=payload["units"],
        spatial=spatial,
        systems=systems,
        asset_types=tuple(asset_type_models),
        occurrences=tuple(occurrence_models),
        artifacts=tuple(artifact_models),
        connections=tuple(connection_models),
        requirements=requirements,
        source_path=source_path,
    )


@lru_cache(maxsize=8)
def _load_cached(
    path_string: str,
    _file_signature: tuple[int, int] | None,
) -> ProjectSpec:
    path = Path(path_string)
    payload = _load_json(path)
    _validate_schema(payload)
    _validate_semantics(payload)
    return _construct(payload, path)


def load_project_spec(path: str | Path = DEFAULT_PROJECT_SPEC_PATH) -> ProjectSpec:
    resolved = Path(path).resolve()
    try:
        stat = resolved.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        signature = None
    return _load_cached(str(resolved), signature)


def clear_project_spec_cache() -> None:
    _load_cached.cache_clear()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "summary"), nargs="?", default="validate")
    parser.add_argument("--project-spec", type=Path, default=DEFAULT_PROJECT_SPEC_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = load_project_spec(args.project_spec)
    except ProjectSpecError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "summary":
        print(json.dumps(project.summary(), indent=2, sort_keys=True))
    else:
        summary = project.summary()
        print(f"ProjectSpec valid: {project.source_path}")
        print(
            f"- {summary['asset_type_count']} asset types, {summary['occurrence_count']} occurrences, "
            f"{summary['artifact_count']} artifacts"
        )
        print(
            f"- {summary['system_count']} systems, {summary['connection_count']} connections, "
            f"{summary['declared_port_count']} declared ports"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
