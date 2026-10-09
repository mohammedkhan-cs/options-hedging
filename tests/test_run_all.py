import inspect
import sys

import run_all


def test_run_stage_reports_success_and_failure(tmp_path):
    ok, out = run_all.run_stage("ok", [sys.executable, "-c", "print('hello')"], "hello", cwd=tmp_path)
    assert ok and "hello" in out
    ok, _ = run_all.run_stage("exit code", [sys.executable, "-c", "raise SystemExit(3)"], cwd=tmp_path)
    assert not ok
    ok, _ = run_all.run_stage("missing text", [sys.executable, "-c", "print('x')"], "ALL GOOD", cwd=tmp_path)
    assert not ok


def test_reproducibility_check_flags_only_values_that_are_off():
    actual = {n: e for n, e, _ in run_all.EXPECTED}
    assert run_all.check_reproducibility(actual) == []
    actual["ATM implied vol"] += 0.001
    assert [o[0] for o in run_all.check_reproducibility(actual)] == ["ATM implied vol"]


def test_every_expected_value_has_an_extractor():
    src = inspect.getsource(run_all.actual_values)
    for n, _, _ in run_all.EXPECTED:
        assert f'"{n}"' in src, n