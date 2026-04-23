"""App version from installed package metadata (``pyproject`` / wheel)."""

from __future__ import annotations

from importlib import metadata


def get_package_version() -> str:
    try:
        return metadata.version("plant-pal")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "0.0.0"


__all__ = ["get_package_version"]
