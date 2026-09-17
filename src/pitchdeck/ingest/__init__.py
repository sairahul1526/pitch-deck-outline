"""Source ingestion contracts and provenance utilities."""

from .registry import (
    PERMISSION_SCOPES,
    SOURCE_KINDS,
    RegistryError,
    SourceRecord,
    SourceRegistry,
)

__all__ = [
    "PERMISSION_SCOPES",
    "SOURCE_KINDS",
    "RegistryError",
    "SourceRecord",
    "SourceRegistry",
]
