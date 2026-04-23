# tests/conftest.py
# pytest hook registration — must be in conftest.py to be auto-discovered.
import json
import sys


def pytest_sessionfinish(session, exitstatus):
    """Flush accumulated _SCORES dict to /tmp/scores.json after all tests."""
    # Import the scores dict from test_state (already loaded by pytest)
    try:
        from test_state import _SCORES, SCORES_FILE, weights as _W
    except ImportError:
        # fallback path
        try:
            import importlib, pathlib, sys as _sys
            spec = importlib.util.spec_from_file_location(
                "test_state", "/tests/test_state.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _SCORES = mod._SCORES
            SCORES_FILE = mod.SCORES_FILE
            _W = mod.weights
        except Exception as e:
            print(f"[conftest] ERROR importing test_state: {e}", file=sys.stderr)
            return

    total = sum(_W[k] * _SCORES.get(k, 0.0) for k in _W)
    _SCORES["total"] = round(total, 4)
    try:
        with open(SCORES_FILE, "w") as f:
            json.dump(_SCORES, f, indent=2)
        print(f"\n[conftest] scores written to {SCORES_FILE}: {_SCORES}", file=sys.stderr)
    except Exception as e:
        print(f"[conftest] ERROR writing scores: {e}", file=sys.stderr)
