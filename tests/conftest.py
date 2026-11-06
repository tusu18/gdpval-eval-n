"""Some tests cover earlier pilot iterations (paired_v1/v2, evidence_upgrade_01, evaluation_v2) whose input data
is not published in this repository. When such a test fails only because that input is missing, it is reported
as skipped with the missing path, so `pytest` separates "input not shipped" from real failures."""
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
UNPUBLISHED = [ROOT / p for p in ('data/evidence_upgrade_01', 'data/evaluation_v2', 'data/paired_v1', 'data/paired_v2',
                                  'data/paired_v2_1', 'data/evaluation_v5', 'output/paired_v1', 'docs/evaluation_v2')]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if call.excinfo is None or not call.excinfo.errisinstance(FileNotFoundError):
        return
    fn = str(getattr(call.excinfo.value, 'filename', '') or '')
    if fn and any(fn.startswith(str(p) + os.sep) for p in UNPUBLISHED):
        rep.outcome = 'skipped'
        rep.longrepr = (str(item.path), item.location[1] or 0, 'input from an earlier pilot, not published here: ' + os.path.relpath(fn, ROOT))
