import shutil
import sys
from pathlib import Path

import pytest

from garp import cli

TEMPLATE = Path(cli.__file__).parent / "tools" / "_template.py"


@pytest.fixture
def tools_dir(tmp_path, monkeypatch):
    """Point the CLI at a throwaway tools package containing the template as `echo`."""
    pkg = tmp_path / "fake_tools"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    shutil.copy(TEMPLATE, pkg / "echo.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cli, "TOOLS_DIR", pkg)
    monkeypatch.setattr(cli, "TOOLS_PKG", "fake_tools")
    yield pkg
    for mod in [m for m in sys.modules if m == "fake_tools" or m.startswith("fake_tools.")]:
        del sys.modules[mod]
