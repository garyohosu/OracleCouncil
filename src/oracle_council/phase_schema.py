from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any

_PHASES = ("respond", "claim_extract", "verify", "criticize", "synthesize", "audit")
_KEYS = {"type", "properties", "required", "additionalProperties", "enum", "items", "minLength", "maxLength", "minItems", "maxItems"}


class SchemaValidationError(ValueError):
    def __init__(self, message: str, summary: str) -> None:
        super().__init__(message)
        self.summary = summary


def _check_schema(schema: Any) -> None:
    if not isinstance(schema, dict) or set(schema) - _KEYS:
        raise ValueError("unsupported or malformed phase schema")
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError("phase object schema must be closed")
        for child in schema.get("properties", {}).values():
            _check_schema(child)
    if "items" in schema:
        _check_schema(schema["items"])


@lru_cache(maxsize=None)
def _schema(phase: str) -> dict[str, Any]:
    if phase not in _PHASES:
        raise ValueError(f"unknown phase: {phase}")
    value = json.loads(files("oracle_council.schemas").joinpath(f"{phase}.json").read_text(encoding="utf-8"))
    _check_schema(value)
    return value


def get_phase_schema(phase: str) -> dict[str, Any]:
    return deepcopy(_schema(phase))


def _typename(value: Any) -> str:
    if value is None: return "null"
    if isinstance(value, bool): return "boolean"
    if isinstance(value, dict): return "object"
    if isinstance(value, list): return "array"
    if isinstance(value, str): return "string"
    if isinstance(value, (int, float)): return "number"
    return "unknown"


def _matches(value: Any, expected: str) -> bool:
    return {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str), "number": isinstance(value, (int, float)) and not isinstance(value, bool), "boolean": isinstance(value, bool), "null": value is None}.get(expected, False)


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    field = path.rsplit(".", 1)[-1].split("[", 1)[0] or "output"
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches(value, item) for item in expected):
            raise SchemaValidationError(f"{path} must be one of {expected}", f"invalid type for field: {field}; expected {expected[0]}; actual {_typename(value)}")
    elif expected and not _matches(value, expected):
        raise SchemaValidationError(f"{path} must be {expected}", f"invalid type for field: {field}; expected {expected}; actual {_typename(value)}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path} has an invalid enum value: {value!r}", f"invalid enum for field: {field}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0): raise SchemaValidationError(f"{path} is too short", f"string too short for field: {field}")
        if len(value) > schema.get("maxLength", 2**31): raise SchemaValidationError(f"{path} is too long", f"string too long for field: {field}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0): raise SchemaValidationError(f"{path} has too few items", f"too few items for field: {field}")
        if len(value) > schema.get("maxItems", 2**31): raise SchemaValidationError(f"{path} has too few items", f"too few items for field: {field}")
        for index, item in enumerate(value): _validate(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value: raise SchemaValidationError(f"missing {key}", f"missing field: {key}")
        properties = schema.get("properties", {})
        for key in value:
            if key not in properties and schema.get("additionalProperties", True) is False:
                raise SchemaValidationError(f"unexpected {key}", f"unexpected field: {key}")
        for key, child in properties.items():
            if key in value: _validate(value[key], child, key)


def validate_phase_schema(phase: str, value: Any) -> dict[str, Any]:
    schema = _schema(phase)
    _validate(value, schema, "output")
    return value
