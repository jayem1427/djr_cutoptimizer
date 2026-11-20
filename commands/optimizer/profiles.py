"""
Limit profiles as a JSON file in the user's app-data folder. The palette's localStorage
may not persist in Fusion, so the page reads and writes these through Python.
Pure Python, no adsk import.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile


def data_dir() -> str:
    if sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'djr_cutoptimizer')


def profiles_path(folder: str | None = None) -> str:
    return os.path.join(folder or data_dir(), 'limit_profiles.json')


def load(folder: str | None = None) -> dict:
    try:
        with open(profiles_path(folder), encoding='utf-8') as f:
            data = json.load(f)
        items = data.get('items') if isinstance(data, dict) else None
        return items if isinstance(items, dict) else {}
    except (OSError, ValueError):
        return {}


def save(items: dict, folder: str | None = None) -> None:
    if not isinstance(items, dict):
        raise ValueError('items must be an object')
    path = profiles_path(folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # write-then-rename so a crash never leaves a half-written file
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'items': items}, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
