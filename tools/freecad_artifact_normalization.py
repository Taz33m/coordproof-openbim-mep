"""Deterministically normalize artifacts emitted by the FreeCAD desktop build.

FreeCAD and its bundled exporters embed wall-clock timestamps, process-local
object identifiers, and random IFC GUIDs in otherwise stable artifacts.  The
normalizers in this module preserve geometry and model structure while making
those explicitly volatile fields reproducible.  Every transformation validates
the input shape first and publishes with an atomic same-directory replacement.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.validate
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from reproducibility import source_date_epoch, source_timestamp

FCSTD_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/Taz33m/coordproof-openbim-mep/freecad/fcstd",
)
IFC_GUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/Taz33m/coordproof-openbim-mep/freecad/review-ifc",
)
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
FCSTD_ARCHIVE_COMMENT = b"FreeCAD Document"
MAX_FCSTD_MEMBERS = 1000
MAX_FCSTD_MEMBER_BYTES = 10 * 1024 * 1024
MAX_FCSTD_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FCSTD_COMPRESSION_RATIO = 1000
REVIEW_BUILDING_LINK = (
    "IfcRelAggregates|BuildingLink|IfcBuilding|Building_MechanicalLab|"
    "IfcBuildingStorey|Storey_MechanicalLevel_01"
)
REQUIRED_REVIEW_HIERARCHY = frozenset(
    {
        "IfcRelAggregates|ProjectLink|IfcProject|Project_CoordProof_MechanicalRoom|"
        "IfcSite|Site_OpenBIM_Testbed",
        "IfcRelAggregates|SiteLink|IfcSite|Site_OpenBIM_Testbed|"
        "IfcBuilding|Building_MechanicalLab",
        REVIEW_BUILDING_LINK,
        "IfcRelAggregates|StoreyLink|IfcBuildingStorey|Storey_MechanicalLevel_01|"
        "IfcSpace|Space_MechanicalRoom_001",
    }
)

_STEP_FILE_NAME_RE = re.compile(
    r"^FILE_NAME\('(?P<name>[^']*)','(?P<timestamp>[^']*)'",
    flags=re.MULTILINE,
)
_IFC_FILE_NAME_RE = re.compile(
    r"^FILE_NAME\('(?P<name>[^']*)','(?P<timestamp>[^']*)'",
    flags=re.MULTILINE,
)
_FCSTD_OBJECT_RE = re.compile(
    r'(<Object type="(?P<type>[^"]+)" name="(?P<name>[^"]+)" id=")'
    r'(?P<id>[^"]+)(" />)'
)


class ArtifactNormalizationError(RuntimeError):
    """Raised when an artifact cannot be normalized without guessing."""


def _source_date_epoch() -> int:
    try:
        return source_date_epoch()
    except ValueError as exc:
        raise ArtifactNormalizationError(str(exc)) from exc


def _source_timestamp() -> str:
    try:
        return source_timestamp(_source_date_epoch())
    except ValueError as exc:
        raise ArtifactNormalizationError("SOURCE_DATE_EPOCH is outside the supported range") from exc


def _atomic_write_bytes(
    path: Path,
    payload: bytes,
    *,
    validator: Callable[[Path], None] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode = path.stat().st_mode if path.exists() else None
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if original_mode is not None:
            os.chmod(temporary, original_mode)
        if validator is not None:
            validator(temporary)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_exactly_once(
    pattern: re.Pattern[str],
    replacement: str,
    text: str,
    *,
    field: str,
) -> str:
    normalized, count = pattern.subn(replacement, text)
    if count != 1:
        raise ArtifactNormalizationError(f"expected exactly one {field}, found {count}")
    return normalized


def normalize_step_header(path: Path) -> None:
    """Normalize the STEP FILE_NAME path and timestamp atomically."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactNormalizationError(f"could not read STEP artifact {path}") from exc
    if not text.startswith("ISO-10303-21;") or "END-ISO-10303-21;" not in text[-256:]:
        raise ArtifactNormalizationError(f"invalid ISO-10303 STEP envelope: {path}")

    replacement = f"FILE_NAME('{path.name}','{_source_timestamp()}'"
    normalized = _replace_exactly_once(
        _STEP_FILE_NAME_RE,
        replacement,
        text,
        field="STEP FILE_NAME header",
    )
    _atomic_write_bytes(path, normalized.encode("utf-8"))


def _replace_fcstd_property(
    document: str,
    *,
    property_name: str,
    value_element: str,
    value: str,
) -> str:
    pattern = re.compile(
        rf'(<Property name="{re.escape(property_name)}"[^>]*>\s*'
        rf'<{value_element} value=")[^"]*("/>)'
    )
    return _replace_exactly_once(
        pattern,
        rf"\g<1>{value}\2",
        document,
        field=f"FCStd {property_name} property",
    )


def _validate_fcstd_members(
    names: list[str],
    payloads: dict[str, bytes],
    *,
    expected_shape_members: int,
    expected_empty_shape_members: frozenset[str],
) -> None:
    if len(names) != len(set(names)):
        raise ArtifactNormalizationError("FCStd archive contains duplicate member names")
    if names.count("Document.xml") != 1:
        raise ArtifactNormalizationError("FCStd archive must contain exactly one Document.xml")
    if names[0] != "Document.xml":
        raise ArtifactNormalizationError("FCStd Document.xml must be the first archive member")
    for name in names:
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or "\\" in name:
            raise ArtifactNormalizationError(f"unsafe FCStd archive member: {name}")
        if not payloads[name] and name not in expected_empty_shape_members:
            raise ArtifactNormalizationError(f"empty FCStd archive member: {name}")
    shape_members = [name for name in names if name.endswith(".Shape.brp")]
    if len(shape_members) != expected_shape_members:
        raise ArtifactNormalizationError(
            "unexpected FCStd shape-member count: "
            f"expected {expected_shape_members}, found {len(shape_members)}"
        )
    empty_shape_members = {name for name in shape_members if not payloads[name]}
    if empty_shape_members != expected_empty_shape_members:
        raise ArtifactNormalizationError(
            "unexpected empty FCStd shape members: "
            f"expected {sorted(expected_empty_shape_members)}, "
            f"found {sorted(empty_shape_members)}"
        )
    try:
        document_root = ET.fromstring(payloads["Document.xml"])
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ArtifactNormalizationError(
            "FCStd Document.xml is not valid UTF-8 XML"
        ) from exc
    objects_parent = document_root.find("Objects")
    if objects_parent is None:
        raise ArtifactNormalizationError("FCStd Document.xml has no Objects element")
    declared_names = [element.attrib.get("name") for element in objects_parent.findall("Object")]
    shape_member_set = set(shape_members)
    expected_shape_order = [
        f"{name}.Shape.brp"
        for name in declared_names
        if isinstance(name, str) and f"{name}.Shape.brp" in shape_member_set
    ]
    if shape_members != expected_shape_order:
        raise ArtifactNormalizationError(
            "FCStd shape members must follow Document.xml object declaration order"
        )


def _normalize_fcstd_document(
    payload: bytes,
    *,
    artifact_identity: str,
    expected_object_count: int,
) -> bytes:
    try:
        document = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        root = ET.fromstring(document)
    except (UnicodeDecodeError, ET.ParseError, DefusedXmlException) as exc:
        raise ArtifactNormalizationError("FCStd Document.xml is not valid UTF-8 XML") from exc

    objects_parent = root.find("Objects")
    if objects_parent is None:
        raise ArtifactNormalizationError("FCStd Document.xml has no Objects element")
    object_elements = list(objects_parent.findall("Object"))
    if len(object_elements) != expected_object_count:
        raise ArtifactNormalizationError(
            "unexpected FCStd object count: "
            f"expected {expected_object_count}, found {len(object_elements)}"
        )
    object_names = [element.attrib.get("name") for element in object_elements]
    if any(not name for name in object_names) or len(object_names) != len(set(object_names)):
        raise ArtifactNormalizationError("FCStd object names must be non-empty and unique")
    object_ids = [element.attrib.get("id") for element in object_elements]
    if any(not value for value in object_ids) or len(object_ids) != len(set(object_ids)):
        raise ArtifactNormalizationError("FCStd object identifiers must be non-empty and unique")
    known_ids = set(object_ids)
    for element in root.iter():
        for attribute, value in element.attrib.items():
            is_declaration = element in object_elements and attribute == "id"
            is_identifier_reference = attribute.casefold() in {
                "id",
                "objectid",
                "object_id",
                "ref",
            }
            if not is_declaration and is_identifier_reference and value in known_ids:
                raise ArtifactNormalizationError(
                    "FCStd object identifier is referenced outside its declaration; "
                    "refusing to renumber"
                )

    timestamp = f"{_source_timestamp()}Z"
    document = _replace_fcstd_property(
        document,
        property_name="CreationDate",
        value_element="String",
        value=timestamp,
    )
    document = _replace_fcstd_property(
        document,
        property_name="LastModifiedDate",
        value_element="String",
        value=timestamp,
    )
    stable_uuid = uuid.uuid5(FCSTD_UUID_NAMESPACE, artifact_identity)
    document = _replace_fcstd_property(
        document,
        property_name="Uid",
        value_element="Uuid",
        value=str(stable_uuid),
    )

    declaration_count = 0

    def replace_object_id(match: re.Match[str]) -> str:
        nonlocal declaration_count
        declaration_count += 1
        return f"{match.group(1)}{declaration_count}{match.group(5)}"

    document = _FCSTD_OBJECT_RE.sub(replace_object_id, document)
    if declaration_count != expected_object_count:
        raise ArtifactNormalizationError(
            "FCStd XML object declarations did not match the parsed object count"
        )
    try:
        ET.fromstring(document)
    except (ET.ParseError, DefusedXmlException) as exc:  # pragma: no cover
        raise ArtifactNormalizationError("normalized FCStd Document.xml is invalid") from exc
    return document.encode("utf-8")


def normalize_fcstd(
    path: Path,
    *,
    artifact_identity: str,
    expected_object_count: int,
    expected_shape_members: int,
    expected_empty_shape_members: Iterable[str] = (),
) -> None:
    """Canonicalize volatile FCStd ZIP/XML metadata without touching BREP payloads."""

    if not zipfile.is_zipfile(path):
        raise ArtifactNormalizationError(f"FCStd is not a valid ZIP archive: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FCSTD_MEMBERS:
                raise ArtifactNormalizationError("FCStd archive has too many members")
            if any(info.flag_bits & 1 for info in infos):
                raise ArtifactNormalizationError("FCStd archive contains encrypted members")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                raise ArtifactNormalizationError("FCStd archive contains symlink members")
            if any(info.file_size > MAX_FCSTD_MEMBER_BYTES for info in infos):
                raise ArtifactNormalizationError("FCStd archive member exceeds size limit")
            if sum(info.file_size for info in infos) > MAX_FCSTD_TOTAL_BYTES:
                raise ArtifactNormalizationError("FCStd archive exceeds uncompressed size limit")
            if any(
                info.file_size / max(info.compress_size, 1) > MAX_FCSTD_COMPRESSION_RATIO
                for info in infos
            ):
                raise ArtifactNormalizationError(
                    "FCStd archive member has suspicious compression ratio"
                )
            names = [info.filename for info in infos]
            for name in names:
                parts = name.split("/")
                if (
                    not name
                    or "\\" in name
                    or any(ord(character) < 32 for character in name)
                    or any(
                        part in {"", ".", ".."}
                        or re.fullmatch(r"[A-Za-z0-9._-]+", part) is None
                        for part in parts
                    )
                ):
                    raise ArtifactNormalizationError(f"unsafe FCStd archive member: {name}")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ArtifactNormalizationError(f"FCStd CRC failure in {bad_member}")
            if archive.comment != FCSTD_ARCHIVE_COMMENT:
                raise ArtifactNormalizationError(
                    "unexpected FCStd archive comment: " + repr(archive.comment)
                )
            if any(info.compress_type != zipfile.ZIP_DEFLATED for info in infos):
                raise ArtifactNormalizationError("FCStd members must use DEFLATE compression")
            payloads = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArtifactNormalizationError(f"could not read FCStd archive {path}") from exc

    _validate_fcstd_members(
        names,
        payloads,
        expected_shape_members=expected_shape_members,
        expected_empty_shape_members=frozenset(expected_empty_shape_members),
    )
    payloads["Document.xml"] = _normalize_fcstd_document(
        payloads["Document.xml"],
        artifact_identity=artifact_identity,
        expected_object_count=expected_object_count,
    )

    temporary: Path | None = None
    original_mode = path.stat().st_mode
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.comment = FCSTD_ARCHIVE_COMMENT
            for name in names:
                info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info,
                    payloads[name],
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ArtifactNormalizationError("normalized FCStd archive failed CRC validation")
        os.chmod(temporary, original_mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _root_object_key(root: ifcopenshell.entity_instance) -> str:
    name = getattr(root, "Name", None)
    if not isinstance(name, str) or not name:
        raise ArtifactNormalizationError(
            f"{root.is_a()} #{root.id()} has no stable non-empty Name"
        )
    return f"{root.is_a()}|{name}"


def _root_reference_keys(items: Iterable[ifcopenshell.entity_instance]) -> str:
    return ",".join(sorted(_root_object_key(item) for item in items))


def _relationship_key(relationship: ifcopenshell.entity_instance) -> str:
    name = getattr(relationship, "Name", None) or ""
    if relationship.is_a("IfcRelAggregates"):
        relating = _root_object_key(relationship.RelatingObject)
        related = _root_reference_keys(relationship.RelatedObjects)
    elif relationship.is_a("IfcRelContainedInSpatialStructure"):
        relating = _root_object_key(relationship.RelatingStructure)
        related = _root_reference_keys(relationship.RelatedElements)
    else:
        raise ArtifactNormalizationError(
            f"unsupported FreeCAD review-IFC relationship: {relationship.is_a()}"
        )
    return f"{relationship.is_a()}|{name}|{relating}|{related}"


def _relationship_fingerprint(relationship: ifcopenshell.entity_instance) -> str:
    owner = getattr(relationship, "OwnerHistory", None)
    owner_id = owner.id() if owner is not None else 0
    description = getattr(relationship, "Description", None) or ""
    return f"{_relationship_key(relationship)}|owner:{owner_id}|description:{description}"


def _duplicate_relationship_ids(
    roots: Iterable[ifcopenshell.entity_instance],
) -> set[int]:
    groups: dict[str, list[int]] = {}
    for root in roots:
        if root.is_a("IfcRelationship"):
            groups.setdefault(_relationship_fingerprint(root), []).append(root.id())
    return {
        entity_id
        for entity_ids in groups.values()
        for entity_id in sorted(entity_ids)[1:]
    }


def _validate_review_hierarchy(
    roots: Iterable[ifcopenshell.entity_instance],
    duplicate_ids: set[int],
    *,
    expected_duplicate_relationship_count: int,
) -> None:
    relationships = [root for root in roots if root.is_a("IfcRelationship")]
    keys = {_relationship_key(relationship) for relationship in relationships}
    missing = sorted(REQUIRED_REVIEW_HIERARCHY - keys)
    if missing:
        raise ArtifactNormalizationError(
            "FreeCAD review IFC is missing required spatial hierarchy: " + ", ".join(missing)
        )
    duplicate_keys = {
        _relationship_key(relationship)
        for relationship in relationships
        if relationship.id() in duplicate_ids
    }
    expected_duplicate_keys = (
        {REVIEW_BUILDING_LINK} if expected_duplicate_relationship_count == 1 else set()
    )
    if duplicate_keys not in (set(), expected_duplicate_keys):
        raise ArtifactNormalizationError(
            "FreeCAD review IFC has an unexpected duplicate relationship: "
            f"expected canonical input or {sorted(expected_duplicate_keys)}, "
            f"found {sorted(duplicate_keys)}"
        )

    containment = [
        relationship
        for relationship in relationships
        if relationship.is_a("IfcRelContainedInSpatialStructure")
    ]
    if len(containment) != 1:
        raise ArtifactNormalizationError(
            "FreeCAD review IFC must have exactly one spatial containment relationship"
        )
    relation = containment[0]
    if _root_object_key(relation.RelatingStructure) != (
        "IfcBuildingStorey|Storey_MechanicalLevel_01"
    ):
        raise ArtifactNormalizationError(
            "FreeCAD review IFC products are not contained by the required storey"
        )
    expected_elements = {
        _root_object_key(root)
        for root in roots
        if root.is_a("IfcProduct") and not root.is_a("IfcSpatialElement")
    }
    actual_elements = {_root_object_key(element) for element in relation.RelatedElements}
    if actual_elements != expected_elements:
        raise ArtifactNormalizationError(
            "FreeCAD review IFC spatial containment does not cover every non-spatial product"
        )


def _ifc_root_keys(
    roots: list[ifcopenshell.entity_instance],
) -> dict[int, str]:
    object_keys = {
        root.id(): _root_object_key(root)
        for root in roots
        if not root.is_a("IfcRelationship")
    }
    if len(object_keys) != len(set(object_keys.values())):
        raise ArtifactNormalizationError(
            "FreeCAD review-IFC object type/name identities must be unique"
        )
    keys = dict(object_keys)
    for root in roots:
        if root.is_a("IfcRelationship"):
            keys[root.id()] = _relationship_key(root)
    if len(keys) != len(set(keys.values())):
        raise ArtifactNormalizationError("FreeCAD review-IFC root identities must be unique")
    return keys


def _normalize_owner_history(text: str, owner_ids: list[int], epoch: int) -> str:
    for owner_id in owner_ids:
        pattern = re.compile(
            rf"^(#{owner_id}=IFCOWNERHISTORY\([^,]+,[^,]+,[^,]+,[^,]+,)"
            rf"([^,]+)(,[^,]+,[^,]+,)([^)]+)(\);)$",
            flags=re.MULTILINE,
        )
        text = _replace_exactly_once(
            pattern,
            rf"\g<1>{epoch}\g<3>{epoch}\g<5>",
            text,
            field=f"IFCOWNERHISTORY #{owner_id}",
        )
    return text


def _ifc_inventory(model: ifcopenshell.file) -> list[tuple[int, str, str | None]]:
    return [
        (root.id(), root.is_a(), getattr(root, "Name", None))
        for root in model.by_type("IfcRoot")
    ]


def normalize_review_ifc(
    path: Path,
    *,
    expected_root_count: int,
    expected_product_count: int,
    expected_duplicate_relationship_count: int = 0,
) -> None:
    """Normalize FreeCAD review-IFC timestamps and IfcRoot GUIDs atomically."""

    try:
        original_text = (
            path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        )
        model = ifcopenshell.open(str(path))
    except (OSError, UnicodeDecodeError, RuntimeError) as exc:
        raise ArtifactNormalizationError(f"could not read FreeCAD review IFC {path}") from exc
    if model.schema != "IFC4":
        raise ArtifactNormalizationError(f"expected IFC4 review model, found {model.schema}")
    roots = list(model.by_type("IfcRoot"))
    products = list(model.by_type("IfcProduct"))
    duplicate_ids = _duplicate_relationship_ids(roots)
    _validate_review_hierarchy(
        roots,
        duplicate_ids,
        expected_duplicate_relationship_count=expected_duplicate_relationship_count,
    )
    canonical_root_count = expected_root_count - expected_duplicate_relationship_count
    raw_shape = (
        len(roots) == expected_root_count
        and len(duplicate_ids) == expected_duplicate_relationship_count
    )
    canonical_shape = len(roots) == canonical_root_count and not duplicate_ids
    if not (raw_shape or canonical_shape):
        raise ArtifactNormalizationError(
            "unexpected review-IFC relationship/root shape: "
            f"expected {expected_root_count} roots with "
            f"{expected_duplicate_relationship_count} duplicate relationship(s), or "
            f"{canonical_root_count} canonical roots; found {len(roots)} roots with "
            f"{len(duplicate_ids)} duplicate relationship(s)"
        )
    if len(products) != expected_product_count:
        raise ArtifactNormalizationError(
            "unexpected review-IFC product count: "
            f"expected {expected_product_count}, found {len(products)}"
        )
    roots = [root for root in roots if root.id() not in duplicate_ids]
    before_inventory = [
        item for item in _ifc_inventory(model) if item[0] not in duplicate_ids
    ]
    root_keys = _ifc_root_keys(roots)

    replacement = f"FILE_NAME('{path.name}','{_source_timestamp()}'"
    normalized = _replace_exactly_once(
        _IFC_FILE_NAME_RE,
        replacement,
        original_text,
        field="review-IFC FILE_NAME header",
    )
    owner_ids = [owner.id() for owner in model.by_type("IfcOwnerHistory")]
    if not owner_ids:
        raise ArtifactNormalizationError("FreeCAD review IFC has no IfcOwnerHistory")
    normalized = _normalize_owner_history(normalized, owner_ids, _source_date_epoch())

    for duplicate_id in sorted(duplicate_ids):
        normalized = _replace_exactly_once(
            re.compile(rf"^#{duplicate_id}=.*;\n?", flags=re.MULTILINE),
            "",
            normalized,
            field=f"duplicate review-IFC relationship #{duplicate_id}",
        )

    for root in roots:
        stable_guid = ifcopenshell.guid.compress(
            uuid.uuid5(IFC_GUID_NAMESPACE, root_keys[root.id()]).hex
        )
        pattern = re.compile(
            rf"^(#{root.id()}={root.is_a().upper()}\()'[^']{{22}}'",
            flags=re.MULTILINE,
        )
        normalized = _replace_exactly_once(
            pattern,
            rf"\g<1>'{stable_guid}'",
            normalized,
            field=f"{root.is_a()} #{root.id()} GlobalId",
        )

    epoch = _source_date_epoch()

    def validate_normalized(candidate: Path) -> None:
        try:
            normalized_model = ifcopenshell.open(str(candidate))
        except RuntimeError as exc:  # pragma: no cover - defensive invariant
            raise ArtifactNormalizationError("normalized review IFC is unreadable") from exc
        after_inventory = _ifc_inventory(normalized_model)
        if before_inventory != after_inventory:
            raise ArtifactNormalizationError(
                "review-IFC root inventory changed during normalization"
            )
        normalized_roots = list(normalized_model.by_type("IfcRoot"))
        if len(normalized_roots) != canonical_root_count:
            raise ArtifactNormalizationError(
                "normalized review-IFC root count is not canonical"
            )
        normalized_guids = [root.GlobalId for root in normalized_roots]
        if len(normalized_guids) != len(set(normalized_guids)):
            raise ArtifactNormalizationError("normalized review-IFC GlobalIds are not unique")
        try:
            for guid in normalized_guids:
                ifcopenshell.guid.expand(guid)
        except Exception as exc:  # pragma: no cover - library exception varies
            raise ArtifactNormalizationError(
                "normalized review-IFC contains an invalid GlobalId"
            ) from exc
        for owner in normalized_model.by_type("IfcOwnerHistory"):
            if owner.CreationDate != epoch or owner.LastModifiedDate != epoch:
                raise ArtifactNormalizationError(
                    "normalized review-IFC owner-history timestamps are not reproducible"
                )
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(normalized_model, logger, express_rules=True)
        errors = [item for item in logger.statements if item.get("level") == "error"]
        if errors:
            message = str(errors[0].get("message", "formal IFC validation error")).splitlines()[0]
            raise ArtifactNormalizationError(
                f"normalized review IFC fails formal validation: {message}"
            )

    _atomic_write_bytes(
        path,
        normalized.encode("utf-8"),
        validator=validate_normalized,
    )
