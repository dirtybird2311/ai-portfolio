"""
Runs each test file in its own Python process.

The test files replace pieces of the pipeline with fakes at import time (prices, model replies,
the clock). Loaded together in one process, those fakes leak from one file into the next. Here,
`python -m pytest tests/` runs every file separately, exactly as `python tests/test_x.py` would,
and reports one result per file (the file's own output lists each test that passed).

Set PYTEST_IN_PROCESS=1 to use normal in-process collection for a single file while debugging:
    PYTEST_IN_PROCESS=1 python -m pytest tests/test_ledger.py
"""
import os
import subprocess
import sys

import pytest


class FileFailed(Exception):
    pass


class IsolatedFile(pytest.File):
    def collect(self):
        yield IsolatedRun.from_parent(self, name=self.path.stem)


class IsolatedRun(pytest.Item):
    def runtest(self):
        r = subprocess.run([sys.executable, str(self.path)], capture_output=True, text=True, timeout=1800,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if r.returncode != 0:
            raise FileFailed((r.stdout[-6000:] + "\n" + r.stderr[-6000:]).strip())

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, FileFailed):
            return f"{self.path.name} failed:\n{excinfo.value}"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, f"{self.path.name} (own process)"


def pytest_pycollect_makemodule(module_path, parent):
    if os.environ.get("PYTEST_IN_PROCESS") == "1":
        return None
    if module_path.name.startswith("test_") and module_path.suffix == ".py":
        return IsolatedFile.from_parent(parent, path=module_path)
    return None
