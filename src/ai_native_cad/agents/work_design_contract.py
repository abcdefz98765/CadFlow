"""Focused canonical contract authority for provider-authored Work Design.

This is deliberately a small immutable definition, not a general schema system.
It exists so the provider request, local validator, and repair feedback cannot
drift into separate descriptions of the same Work Design payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkDesignField:
    name: str
    value_type: str
    non_empty: bool = False
    max_length: int | None = None
    min_items: int | None = None
    max_items: int | None = None
    item_type: str | None = None
    item_object: "WorkDesignObject | None" = None
    item_non_empty: bool = False
    item_max_length: int | None = None
    unique_by: str | None = None


@dataclass(frozen=True)
class WorkDesignObject:
    fields: tuple[WorkDesignField, ...]
    additional_fields: bool = False

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def field(self, name: str) -> WorkDesignField:
        for field in self.fields:
            if field.name == name:
                return field
        raise KeyError(name)


RELATION_CONTRACT = WorkDesignObject(
    fields=(
        WorkDesignField("from", "text", non_empty=True, max_length=200),
        WorkDesignField("to", "text", non_empty=True, max_length=200),
        WorkDesignField("description", "text", non_empty=True, max_length=1_000),
    )
)

GENERATED_PART_CONTRACT = WorkDesignObject(
    fields=(
        WorkDesignField("key", "text", non_empty=True, max_length=120),
        WorkDesignField("name", "text", non_empty=True, max_length=200),
        WorkDesignField("role", "text", non_empty=True, max_length=1_000),
        WorkDesignField(
            "interfaces",
            "list",
            min_items=0,
            max_items=24,
            item_type="text",
            item_non_empty=True,
            item_max_length=1_000,
        ),
        WorkDesignField(
            "dependencies",
            "list",
            min_items=0,
            max_items=12,
            item_type="text",
            item_non_empty=True,
            item_max_length=500,
        ),
    )
)

REFERENCE_COMPONENT_CONTRACT = WorkDesignObject(
    fields=(
        WorkDesignField("name", "text", non_empty=True, max_length=200),
        WorkDesignField("role", "text", non_empty=True, max_length=1_000),
        WorkDesignField(
            "interfaces",
            "list",
            min_items=0,
            max_items=24,
            item_type="text",
            item_non_empty=True,
            item_max_length=1_000,
        ),
    )
)

WORK_DESIGN_CONTRACT = WorkDesignObject(
    fields=(
        WorkDesignField("objective", "text", non_empty=True, max_length=2_000),
        WorkDesignField("concept_summary", "text", non_empty=True, max_length=4_000),
        WorkDesignField(
            "generated_parts",
            "list",
            min_items=1,
            max_items=12,
            item_type="object",
            item_object=GENERATED_PART_CONTRACT,
            unique_by="key",
        ),
        WorkDesignField(
            "reference_components",
            "list",
            min_items=0,
            max_items=24,
            item_type="object",
            item_object=REFERENCE_COMPONENT_CONTRACT,
        ),
        WorkDesignField(
            "interfaces",
            "list",
            min_items=0,
            max_items=48,
            item_type="object",
            item_object=RELATION_CONTRACT,
        ),
        WorkDesignField(
            "dependencies",
            "list",
            min_items=0,
            max_items=24,
            item_type="object",
            item_object=RELATION_CONTRACT,
        ),
        WorkDesignField(
            "assumptions",
            "list",
            min_items=0,
            max_items=24,
            item_type="text",
            item_non_empty=True,
            item_max_length=1_000,
        ),
        WorkDesignField(
            "unresolved_questions",
            "list",
            min_items=0,
            max_items=12,
            item_type="text",
            item_non_empty=True,
            item_max_length=1_000,
        ),
        WorkDesignField("assembly_expected", "boolean"),
        WorkDesignField("recommendation", "text", non_empty=True, max_length=1_000),
    )
)


def work_design_fields(object_path: str = "") -> tuple[str, ...]:
    """Return canonical fields for one known Work Design object path."""

    return _object_for_path(object_path).field_names


def work_design_field(field_name: str, object_path: str = "") -> WorkDesignField:
    """Return one immutable canonical field definition."""

    return _object_for_path(object_path).field(field_name)


def work_design_contract_description() -> dict[str, Any]:
    """Return a deterministic provider-safe, machine-readable description."""

    return _describe_object(WORK_DESIGN_CONTRACT)


def _object_for_path(object_path: str) -> WorkDesignObject:
    objects = {
        "": WORK_DESIGN_CONTRACT,
        "generated_parts[]": GENERATED_PART_CONTRACT,
        "reference_components[]": REFERENCE_COMPONENT_CONTRACT,
        "interfaces[]": RELATION_CONTRACT,
        "dependencies[]": RELATION_CONTRACT,
    }
    try:
        return objects[object_path]
    except KeyError as exc:
        raise ValueError(f"unknown Work Design object path: {object_path}") from exc


def _describe_object(contract: WorkDesignObject) -> dict[str, Any]:
    return {
        "type": "object",
        "additional_fields": contract.additional_fields,
        "required_fields": list(contract.field_names),
        "fields": {
            field.name: _describe_field(field)
            for field in contract.fields
        },
    }


def _describe_field(field: WorkDesignField) -> dict[str, Any]:
    description: dict[str, Any] = {"type": field.value_type}
    if field.non_empty:
        description["non_empty"] = True
    if field.max_length is not None:
        description["max_length"] = field.max_length
    if field.value_type == "list":
        description["min_items"] = field.min_items
        description["max_items"] = field.max_items
        if field.item_object is not None:
            description["items"] = _describe_object(field.item_object)
        else:
            item: dict[str, Any] = {"type": field.item_type}
            if field.item_non_empty:
                item["non_empty"] = True
            if field.item_max_length is not None:
                item["max_length"] = field.item_max_length
            description["items"] = item
        if field.unique_by is not None:
            description["unique_by"] = field.unique_by
    return description


__all__ = [
    "GENERATED_PART_CONTRACT",
    "REFERENCE_COMPONENT_CONTRACT",
    "RELATION_CONTRACT",
    "WORK_DESIGN_CONTRACT",
    "WorkDesignField",
    "WorkDesignObject",
    "work_design_contract_description",
    "work_design_field",
    "work_design_fields",
]
