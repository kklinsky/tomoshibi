"""Tools the AI can call, defined once in a provider-neutral form (docs/DESIGN.md §8)."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    run: Callable[[dict], str]  # returns text (usually JSON) for the model to read


class ToolInputError(ValueError):
    pass


def validate(schema: dict, data: object) -> dict:
    """Small check of a tool's input against its (flat) JSON schema."""
    if not isinstance(data, dict):
        raise ToolInputError("input must be an object")
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in data:
            raise ToolInputError(f"missing {key}")
    for key, value in data.items():
        if key not in props:
            raise ToolInputError(f"unexpected field {key}")
        spec = props[key]
        kind = spec.get("type")
        if kind == "string" and not isinstance(value, str):
            raise ToolInputError(f"{key} must be a string")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolInputError(f"{key} must be one of {spec['enum']}")
    return data
