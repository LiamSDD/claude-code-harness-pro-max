from __future__ import annotations

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PACKAGE_DIR))
BUNDLED = {"skills": "bundled_skills", "agents": "bundled_agents"}


def asset_dir(kind: str) -> str:
    bundled = os.path.join(PACKAGE_DIR, BUNDLED[kind])
    if os.path.isdir(bundled) and any(not n.startswith("_") for n in os.listdir(bundled)):
        return bundled
    return os.path.join(REPO_ROOT, kind)


def template(name: str) -> str:
    return os.path.join(PACKAGE_DIR, "templates", name)
