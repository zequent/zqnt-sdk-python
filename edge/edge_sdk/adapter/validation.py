"""
Command params against the command's input JSON Schema, checked once before the handler runs.

Struct carries every number as a double, so ``3`` arrives as ``3.0``; where the schema says
``integer`` an integral double becomes an ``int`` here, once, for every adapter. NaN is a number:
the platform sends it for an omitted coordinate. A required property that is NaN counts as missing.

The subset covered is what command schemas use: type, properties, required, additionalProperties,
items, enum, const, minimum/maximum (and exclusive), minLength/maxLength, minItems/maxItems.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TYPES = ("object", "array", "string", "number", "integer", "boolean", "null")
_SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "description",
        "title",
        "default",
        "format",
        "examples",
        "$schema",
        "$id",
    }
)


class SchemaError(ValueError):
    """The schema itself is malformed."""


@dataclass
class ValidationResult:
    params: dict
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def message(self) -> str:
        return "; ".join(self.errors)


def validate_params(schema: dict | None, params: dict | None) -> ValidationResult:
    """Coerce *params* to *schema* and collect every violation. No schema: anything goes."""
    params = dict(params or {})
    if not schema:
        return ValidationResult(params, [])
    errors: list[str] = []
    try:
        coerced = _validate(schema, params, "params", errors)
    except SchemaError:
        logger.warning("Command schema is malformed; params passed on unchecked", exc_info=True)
        return ValidationResult(params, [])
    return ValidationResult(coerced if isinstance(coerced, dict) else params, errors)


def check_schema(schema: Any, path: str = "schema") -> list[str]:
    """Problems with a schema as a schema (unknown types, wrong keyword shapes)."""
    problems: list[str] = []
    if not isinstance(schema, dict):
        return [f"{path} must be an object"]
    types = schema.get("type")
    for t in types if isinstance(types, list) else [types] if types is not None else []:
        if t not in _TYPES:
            problems.append(f"{path}.type: unknown type {t!r}")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        problems.append(f"{path}.properties must be an object")
    else:
        for name, sub in properties.items():
            problems.extend(check_schema(sub, f"{path}.properties.{name}"))
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
        problems.append(f"{path}.required must be a list of property names")
    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        problems.extend(check_schema(additional, f"{path}.additionalProperties"))
    elif not isinstance(additional, bool):
        problems.append(f"{path}.additionalProperties must be a boolean or a schema")
    if "items" in schema:
        problems.extend(check_schema(schema["items"], f"{path}.items"))
    if "enum" in schema and not isinstance(schema["enum"], list):
        problems.append(f"{path}.enum must be a list")
    unknown = sorted(set(schema) - _SUPPORTED_KEYWORDS)
    if unknown:
        problems.append(f"{path}: keywords not checked by the SDK: {', '.join(unknown)}")
    return problems


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _matches(value: Any, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    if isinstance(value, bool):
        return False
    if t == "integer":
        return isinstance(value, int)
    if t == "number":
        return isinstance(value, (int, float))
    raise SchemaError(f"unknown type {t!r}")


def _coerce(value: Any, types: list[str]) -> Any:
    if "integer" in types and isinstance(value, float) and value.is_integer():
        return int(value)
    if "number" in types and isinstance(value, str) and value in ("NaN", "Infinity", "-Infinity"):
        return float(value)
    return value


def _validate(schema: dict, value: Any, path: str, errors: list[str]) -> Any:
    raw_type = schema.get("type")
    types = raw_type if isinstance(raw_type, list) else [raw_type] if raw_type else []
    value = _coerce(value, types)

    if types and not any(_matches(value, t) for t in types):
        errors.append(f"{path} must be {' or '.join(types)}, got {_describe(value)}")
        return value

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path} must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {', '.join(repr(v) for v in schema['enum'])}")

    if isinstance(value, (int, float)) and not isinstance(value, bool) and not _is_nan(value):
        _check_bounds(schema, value, path, errors)
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path} must be at least {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path} must be at most {schema['maxLength']} characters")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path} needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path} takes at most {schema['maxItems']} items")
        items = schema.get("items")
        if isinstance(items, dict):
            value = [_validate(items, item, f"{path}[{i}]", errors) for i, item in enumerate(value)]
    if isinstance(value, dict):
        value = _validate_object(schema, value, path, errors)
    return value


def _validate_object(schema: dict, value: dict, path: str, errors: list[str]) -> dict:
    properties: dict = schema.get("properties", {})
    result = dict(value)
    for name in schema.get("required", []):
        if name not in value or value[name] is None or _is_nan(value[name]):
            errors.append(f"{path}.{name} is required")
    for name, item in value.items():
        if name in properties:
            result[name] = _validate(properties[name], item, f"{path}.{name}", errors)
            continue
        additional = schema.get("additionalProperties", True)
        if additional is False:
            errors.append(f"{path}.{name} is not a known parameter")
        elif isinstance(additional, dict):
            result[name] = _validate(additional, item, f"{path}.{name}", errors)
    return result


def _check_bounds(schema: dict, value: float, path: str, errors: list[str]) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path} must be >= {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path} must be <= {schema['maximum']}")
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        errors.append(f"{path} must be > {schema['exclusiveMinimum']}")
    if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
        errors.append(f"{path} must be < {schema['exclusiveMaximum']}")


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def example_params(schema: dict | None) -> dict:
    """A minimal params object that satisfies *schema* (required properties only)."""
    value = _example(schema or {"type": "object"})
    return value if isinstance(value, dict) else {}


def _example(schema: dict) -> Any:
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    raw_type = schema.get("type")
    t = raw_type[0] if isinstance(raw_type, list) and raw_type else raw_type
    if t == "object" or (t is None and "properties" in schema):
        properties = schema.get("properties", {})
        return {name: _example(properties.get(name, {})) for name in schema.get("required", [])}
    if t == "array":
        return [_example(schema.get("items", {})) for _ in range(schema.get("minItems", 0))]
    if t == "string":
        return "x" * max(1, schema.get("minLength", 1))
    if t == "integer":
        return int(schema.get("minimum", 0))
    if t == "number":
        return float(schema.get("minimum", 0.0))
    if t == "boolean":
        return False
    return None
