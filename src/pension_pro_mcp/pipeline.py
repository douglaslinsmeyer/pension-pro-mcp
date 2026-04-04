"""Pluggable response pipeline for transforming MCP tool outputs.

Add transform functions to the pipeline to modify all API tool responses.
Each transform receives the response data and returns the transformed version.
Transforms are applied in order.
"""

import functools
from collections.abc import Callable
from typing import Any


Transform = Callable[[Any], Any]


class ResponsePipeline:
    """An ordered chain of response transforms applied to tool outputs."""

    def __init__(self) -> None:
        self._transforms: list[Transform] = []

    def add(self, transform: Transform) -> None:
        """Append a transform to the pipeline."""
        self._transforms.append(transform)

    def apply(self, data: Any) -> Any:
        """Run all transforms in order on the given data."""
        for transform in self._transforms:
            data = transform(data)
        return data

    def wrap(self, fn: Callable) -> Callable:
        """Decorator that applies the pipeline to an async function's return value."""
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            return self.apply(result)
        return wrapper


# --- Built-in transforms ---


def unwrap_paginated(obj: Any) -> Any:
    """Unwrap paginated responses, extracting just the Values list."""
    if isinstance(obj, dict) and "Values" in obj and "TotalCount" in obj:
        return [unwrap_paginated(item) for item in obj["Values"]]
    if isinstance(obj, dict):
        return {k: unwrap_paginated(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [unwrap_paginated(item) for item in obj]
    return obj


def strip_nulls(obj: Any) -> Any:
    """Recursively remove keys with null, empty string, or empty list values."""
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None and v != "" and v != []}
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj]
    return obj


def build_default_pipeline() -> ResponsePipeline:
    """Create the standard response pipeline with default transforms."""
    pipeline = ResponsePipeline()
    pipeline.add(unwrap_paginated)
    pipeline.add(strip_nulls)
    return pipeline
