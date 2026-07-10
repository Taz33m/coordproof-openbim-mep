"""Compatibility catalog projected from the authoritative ProjectSpec.

The public ``Asset`` lists remain stable for existing generators and validators.
New code should query :mod:`project_spec` directly when it needs the distinction
between reusable asset types, placed occurrences, and package artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from project_spec import CatalogRecord, load_project_spec


@dataclass(frozen=True)
class Asset:
    asset_id: str
    display_name: str
    category: str
    source_tool: str
    ifc_class: str
    parameters: dict[str, object] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    notes: str = ""


def _legacy_asset(record: CatalogRecord) -> Asset:
    """Project one normalized catalog record onto the legacy public shape."""

    return Asset(
        asset_id=record.asset_id,
        display_name=record.display_name,
        category=record.category,
        source_tool=record.source_tool,
        ifc_class=record.ifc_class,
        parameters=dict(record.parameters),
        exports=dict(record.exports),
        notes=record.notes,
    )


PROJECT_SPEC = load_project_spec()
_CATALOG_RECORDS = PROJECT_SPEC.catalog_records()
_GROUP_BY_ID = {record.asset_id: record.group for record in _CATALOG_RECORDS}

ALL_ASSETS: list[Asset] = [_legacy_asset(record) for record in _CATALOG_RECORDS]


def _group(name: str) -> list[Asset]:
    return [asset for asset in ALL_ASSETS if _GROUP_BY_ID[asset.asset_id] == name]


BIM_ASSETS = _group("bim")
IFC_DETAIL_ASSETS = _group("ifc_detail")
CADQUERY_ASSETS = _group("cadquery")
OPENSCAD_ASSETS = _group("openscad")
DRAWING_ASSETS = _group("drawing")
REPORT_ASSETS = _group("report")

REQUIRED_CATEGORIES = set(PROJECT_SPEC.requirements.categories)
REQUIRED_ASSET_IDS = set(PROJECT_SPEC.requirements.asset_ids)
