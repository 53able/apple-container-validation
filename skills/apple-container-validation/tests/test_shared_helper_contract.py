"""Contract tests for validator helpers that run-matrix.py reuses.

run-matrix.py delegates secret-value derivation, symlink-component checks and
pre-parse inheritEnv name extraction to validate-manifest.py. These tests pin
the runner-visible behavior so that a validator-only change cannot silently
weaken the runner's redaction or symlink rejection.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_RUNNER_PATH = Path(__file__).parents[1] / "scripts" / "run-matrix.py"
_SPEC = importlib.util.spec_from_file_location("acv_runner_contract", _RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RUNNER)


class SharedHelperContractTest(unittest.TestCase):
    def test_inherited_values_skip_missing_and_empty_and_sort_longest_first(self) -> None:
        env = {"A": "short", "B": "much-longer-value", "EMPTY": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("MISSING", None)
            values = RUNNER.inherited_values({"A", "B", "EMPTY", "MISSING"})
        self.assertEqual(["much-longer-value", "short"], values)

    def test_symlink_component_detected_at_any_depth(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            (base / "real" / "inner").mkdir(parents=True)
            (base / "link").symlink_to(base / "real")
            self.assertFalse(RUNNER._has_symlink_component(base, Path("real/inner")))
            self.assertTrue(RUNNER._has_symlink_component(base, Path("link/inner")))
            self.assertFalse(RUNNER._has_symlink_component(base, Path("absent/child")))

    def test_preliminary_names_extract_inherit_env_and_ignore_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            good = Path(raw) / "m.json"
            good.write_text(json.dumps({"cases": [{"inheritEnv": ["TOKEN_X"]}]}), encoding="utf-8")
            bad = Path(raw) / "bad.json"
            bad.write_text('{"s": "\\ud800"}', encoding="utf-8")
            names = RUNNER._VALIDATOR._preliminary_names(["--run-id", str(bad), str(good)])
        self.assertIn("TOKEN_X", names)


if __name__ == "__main__":
    unittest.main()
