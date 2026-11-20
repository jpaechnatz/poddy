"""The lite image installs from uv.lite.lock, the full image from uv.lock.

A bump made in uv.lock only (security fixes for transitive packages such as
aiohttp or certifi) silently skips the lite image, so no package shared by
both lock files may be older in uv.lite.lock.
"""

import tomllib
from pathlib import Path

from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]


def _versions(lock_name: str) -> dict[str, Version]:
    data = tomllib.loads((REPO_ROOT / lock_name).read_text(encoding="utf-8"))
    return {
        package["name"]: Version(package["version"])
        for package in data["package"]
        if "version" in package
    }


def test_lite_lock_is_not_behind_full_lock() -> None:
    full = _versions("uv.lock")
    lite = _versions("uv.lite.lock")

    behind = {
        name: f"uv.lite.lock {lite[name]} < uv.lock {full[name]}"
        for name in sorted(full.keys() & lite.keys())
        if lite[name] < full[name]
    }

    assert not behind, (
        "Apply the bump to uv.lite.lock as well, e.g. "
        "`uv lock --upgrade-package <name>==<version>` against "
        f"pyproject.lite.toml: {behind}"
    )
