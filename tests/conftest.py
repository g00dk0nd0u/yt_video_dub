from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def load_script():
    def load(name: str):
        path = SCRIPTS / name
        spec = importlib.util.spec_from_file_location(f"test_{name.replace('.', '_')}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load
