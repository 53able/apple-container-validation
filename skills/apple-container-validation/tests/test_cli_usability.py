#!/usr/bin/env python3
"""CLI usability: fixed --help usage and value-free argument errors (AC-C1, AC-C2)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
RUNNER_PATH = ROOT / "scripts" / "run-matrix.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate-manifest.py"
SECRET = "acv-probe-SECRET-7f3a"
HELP_PROBE = "acv-help-probe-7f3a"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load(RUNNER_PATH, "acv_cli_usability_runner")
VALIDATOR = load(VALIDATOR_PATH, "acv_cli_usability_validator")


def manifest():
    return {
        "version": 1, "slug": "cli-usability", "claim": "claim", "hypothesis": "hypothesis",
        "falsificationCriteria": [{"id": "criterion", "description": "criterion description"}],
        "image": {"tag": "example:1"}, "defaults": {"maxConcurrency": 1}, "mounts": [],
        "cases": [{
            "id": "falsify-case", "group": "negative", "description": "description",
            "relation": "falsify", "criterionIds": ["criterion"], "command": ["true"],
            "inheritEnv": ["TOKEN"], "oracle": {"stdoutContains": ["payload-marker"]},
        }],
    }


M = "<m>"
S = "<s>"
REQUIRED = "<run-id r>"
# (label, runner argv, validator argv or None, runner expected, validator expected).
# M is the valid manifest, S the secret slot, REQUIRED expands to "--run-id r" for the runner.
# Expected output is an exact single line; a tuple (v310, v314) marks version-specific rows.
TABLE = [
    ("concurrency-x", [M, REQUIRED, "--concurrency", S], None,
     "ERROR: --concurrency: expected a positive integer or auto", None),
    ("concurrency-0", [M, REQUIRED, "--concurrency", "0"], None,
     "ERROR: --concurrency: expected a positive integer or auto", None),
    ("run-id-missing", [M], None, "ERROR: --run-id: required", None),
    ("run-id-no-value", [M, "--run-id"], None, "ERROR: --run-id: expected a value", None),
    ("manifest-missing", [REQUIRED], [], "ERROR: manifest: required", "ERROR: manifest: required"),
    ("bogus-x", [M, REQUIRED, "--bogus", S], [M, "--bogus", S],
     "ERROR: unrecognized option: --bogus", "ERROR: unrecognized option: --bogus"),
    ("bogus-eq", [M, REQUIRED, "--bogus=" + S], [M, "--bogus=" + S],
     "ERROR: unrecognized option: --bogus", "ERROR: unrecognized option: --bogus"),
    ("bogus-dash-secret", [M, REQUIRED, "--bogus", "-" + S], [M, "--bogus", "-" + S],
     "ERROR: unrecognized option: --bogus", "ERROR: unrecognized option: --bogus"),
    ("short-attached", [M, REQUIRED, "-p" + S], [M, "-p" + S],
     "ERROR: unrecognized option", "ERROR: unrecognized option"),
    ("uppercase-long", [M, REQUIRED, "--" + S], [M, "--" + S],
     "ERROR: unrecognized option", "ERROR: unrecognized option"),
    ("flag-with-value", [M, REQUIRED, "--dry-run=" + S], [M, "--json=" + S],
     "ERROR: --dry-run: invalid value", "ERROR: --json: invalid value"),
    ("separator-then-option", [M, REQUIRED, "--", "--" + S], [M, "--", "--" + S],
     "ERROR: unexpected positional argument", "ERROR: unexpected positional argument"),
    ("separator-then-bogus", [M, REQUIRED, "--", "--bogus"], [M, "--", "--bogus"],
     "ERROR: unexpected positional argument", "ERROR: unexpected positional argument"),
    # A token exactly equal to "--" suppresses the unknown-option name even when the
    # unknown option comes before it (pins the has_separator branch in parse_cli).
    ("bogus-before-separator", [M, REQUIRED, "--bogus", "--", "x"], [M, "--bogus", "--", "x"],
     "ERROR: unrecognized option", "ERROR: unrecognized option"),
    ("lowercase-option-before-separator-secret", [M, REQUIRED, "--lowercase-like", "--", S],
     [M, "--lowercase-like", "--", S],
     "ERROR: unrecognized option", "ERROR: unrecognized option"),
    ("extra-positional", [M, REQUIRED, S], [M, S],
     "ERROR: unexpected positional argument", "ERROR: unexpected positional argument"),
    ("ambiguous-prefix", [M, REQUIRED, "--r", S], [M, "--r", S],
     "ERROR: invalid arguments", "ERROR: unrecognized option: --r"),
    # R9 residual risk pinned as behaviour: a lowercase long token is echoed as a name.
    ("lowercase-secret-like", [M, REQUIRED, "--lowercase-secret-like"], [M, "--lowercase-secret-like"],
     "ERROR: unrecognized option: --lowercase-secret-like",
     "ERROR: unrecognized option: --lowercase-secret-like"),
    ("run-id-eq-separator", [M, "--run-id=--"], None,
     ("ERROR: --run-id: expected a value", "ERROR: run-idが不正"), None),
    ("concurrency-eq-separator", [M, REQUIRED, "--concurrency=--"], None,
     ("ERROR: --concurrency: expected a value",
      "ERROR: --concurrency: expected a positive integer or auto"), None),
    # Rule 4 runs after rules 2/3, so 3.10's list value does not mask the unknown option.
    ("run-id-eq-separator-then-bogus", [M, "--run-id=--", "--bogus"], None,
     "ERROR: unrecognized option: --bogus", None),
]
NO_SECRET_ROWS = {"lowercase-secret-like", "run-id-eq-separator", "concurrency-eq-separator",
                  "run-id-eq-separator-then-bogus", "separator-then-bogus", "bogus-before-separator",
                  "concurrency-0",
                  "run-id-missing", "run-id-no-value", "manifest-missing"}


def expand(argv, manifest_path: str, secret: str, *, runner: bool) -> list[str]:
    result: list[str] = []
    for token in argv:
        if token == REQUIRED:
            if runner:
                result.extend(["--run-id", "r"])
            continue
        result.append(token.replace(M, manifest_path).replace(S, secret))
    return result


def expected_for(value):
    if not isinstance(value, tuple):
        return [value]
    v310, v314 = value
    if sys.version_info[:2] == (3, 10):
        return [v310]
    if sys.version_info[:2] == (3, 14):
        return [v314]
    return [v310, v314]


class CliUsabilityTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.manifest_path = Path(self._directory.name) / "manifest.json"
        self.manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")

    def run_cli(self, script: Path, argv: list[str], env_name: str = "TOKEN", secret: str = SECRET):
        env = {key: value for key, value in os.environ.items() if key not in ("TOKEN", "OTHER")}
        env[env_name] = secret
        return subprocess.run(
            [sys.executable, "-I", str(script), *argv], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env, cwd=self._directory.name, check=False,
        )

    def test_fixture_manifest_is_valid(self):
        completed = self.run_cli(VALIDATOR_PATH, [str(self.manifest_path)])
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)

    def test_help_prints_fixed_usage_and_exits_zero(self):
        path = str(self.manifest_path)
        variants = (
            ["--help"],
            ["-h"],
            [path, "--run-id", HELP_PROBE, "--help"],
            ["--help", "--bogus", SECRET],
            [path, "--json", "--help"],
        )
        for script, usage in ((RUNNER_PATH, RUNNER.RUNNER_USAGE), (VALIDATOR_PATH, VALIDATOR.VALIDATOR_USAGE)):
            for argv in variants:
                with self.subTest(script=script.name, argv=argv):
                    completed = self.run_cli(script, argv)
                    self.assertEqual(0, completed.returncode)
                    self.assertEqual(usage + "\n", completed.stdout)
                    self.assertEqual("", completed.stderr)
                    for forbidden in (SECRET, path, HELP_PROBE, self._directory.name):
                        self.assertNotIn(forbidden, completed.stdout + completed.stderr)
        for usage in (RUNNER.RUNNER_USAGE, VALIDATOR.VALIDATOR_USAGE):
            self.assertNotIn(SECRET, usage)
            self.assertNotIn(HELP_PROBE, usage)

    def test_help_after_separator_is_not_help(self):
        completed = self.run_cli(RUNNER_PATH, [str(self.manifest_path), "--run-id", "r", "--", "--help"])
        self.assertEqual(2, completed.returncode)
        self.assertEqual("ERROR: unexpected positional argument\n", completed.stderr)
        completed = self.run_cli(VALIDATOR_PATH, [str(self.manifest_path), "--he"])
        self.assertEqual(2, completed.returncode)
        self.assertEqual("ERROR: unrecognized option: --he\n", completed.stderr)

    def test_argument_errors_name_option_and_kind_only(self):
        path = str(self.manifest_path)
        for label, runner_argv, validator_argv, runner_expected, validator_expected in TABLE:
            cases = [(RUNNER_PATH, expand(runner_argv, path, "X", runner=True), runner_expected)]
            if validator_argv is not None:
                cases.append((VALIDATOR_PATH, expand(validator_argv, path, "X", runner=False), validator_expected))
            for script, argv, expected in cases:
                with self.subTest(row=label, script=script.name):
                    completed = self.run_cli(script, argv)
                    self.assertEqual(2, completed.returncode, completed.stderr)
                    self.assertEqual("", completed.stdout)
                    self.assertIn(completed.stderr, [line + "\n" for line in expected_for(expected)])
                    self.assertNotIn("Traceback", completed.stderr)
            if validator_argv is not None:
                with self.subTest(row=label, script="validator --json"):
                    argv = ["--json", *expand(validator_argv, path, "X", runner=False)]
                    completed = self.run_cli(VALIDATOR_PATH, argv)
                    self.assertEqual(2, completed.returncode)
                    self.assertEqual("", completed.stderr)
                    result = json.loads(completed.stdout)
                    self.assertIs(False, result["valid"])
                    self.assertEqual([validator_expected.removeprefix("ERROR: ")], result["errors"])

    def test_argument_errors_never_echo_values(self):
        path = str(self.manifest_path)
        rows = [row for row in TABLE if row[0] not in NO_SECRET_ROWS]
        self.assertEqual(11, len(rows))
        for label, runner_argv, validator_argv, _, _ in rows:
            invocations = [(RUNNER_PATH, expand(runner_argv, path, SECRET, runner=True))]
            if validator_argv is not None:
                validator_args = expand(validator_argv, path, SECRET, runner=False)
                invocations.append((VALIDATOR_PATH, validator_args))
                invocations.append((VALIDATOR_PATH, ["--json", *validator_args]))
            for script, argv in invocations:
                self.assertTrue(any(SECRET in token for token in argv))
                # (a) inherited via inheritEnv, (b) not inherited: (b) proves the
                # reconstruction itself drops the value, not the redaction layer.
                for env_name in ("TOKEN", "OTHER"):
                    with self.subTest(row=label, script=script.name, argv0=argv[0], env=env_name):
                        completed = self.run_cli(script, argv, env_name)
                        self.assertEqual(2, completed.returncode)
                        self.assertNotIn(SECRET, completed.stdout)
                        self.assertNotIn(SECRET, completed.stderr)
                        self.assertNotIn("Traceback", completed.stderr)

    def test_python310_and_current_argparse_paths_converge(self):
        def runner_parser():
            parser = RUNNER.SilentArgumentParser(add_help=False, exit_on_error=False)
            parser.add_argument("manifest", type=Path, nargs="?")
            parser.add_argument("--run-id")
            parser.add_argument("--concurrency", type=RUNNER._concurrency_arg, default="auto")
            parser.add_argument("--dry-run", action="store_true")
            parser.add_argument("--resume", action="store_true")
            parser.add_argument("--results-dir", type=Path, default=Path("results"))
            return parser

        # 3.10 reports some failures through error() instead of ArgumentError.
        parser = runner_parser()
        with mock.patch.object(
            argparse.ArgumentParser, "parse_known_args",
            side_effect=lambda *a, **k: parser.error("the following arguments are required: " + SECRET),
        ):
            with self.assertRaises(RUNNER.CliArgumentError) as caught:
                parser.parse_cli(["m", "--run-id", SECRET], required=("manifest", "run_id"))
        self.assertEqual("invalid arguments", caught.exception.public_message)
        self.assertNotIn(SECRET, str(caught.exception))

        # 3.10 turns "--opt=--" into an empty list; reproduce that namespace on any version.
        def namespace(**overrides):
            values = {"manifest": Path("m"), "run_id": "r", "concurrency": "auto", "dry_run": False,
                      "resume": False, "results_dir": Path("results")}
            values.update(overrides)
            return argparse.Namespace(**values)

        for overrides, extras, expected in (
            ({"run_id": []}, [], "--run-id: expected a value"),
            ({"concurrency": []}, [], "--concurrency: expected a value"),
            ({"results_dir": []}, [], "--results-dir: expected a value"),
            ({"run_id": []}, ["--bogus"], "unrecognized option: --bogus"),
            ({"run_id": [], "manifest": None}, [], "--run-id: expected a value"),
        ):
            with self.subTest(overrides=overrides, extras=extras):
                parser = runner_parser()
                argv = ["m", "--run-id=--", *extras]
                with mock.patch.object(argparse.ArgumentParser, "parse_known_args",
                                       return_value=(namespace(**overrides), list(extras))):
                    with self.assertRaises(RUNNER.CliArgumentError) as caught:
                        parser.parse_cli(argv, required=("manifest", "run_id"))
                self.assertEqual(expected, caught.exception.public_message)

        # ArgumentError messages outside the whitelist never reach the output.
        parser = runner_parser()
        error = argparse.ArgumentError(parser._option_string_actions["--run-id"], "bad " + SECRET)
        with mock.patch.object(argparse.ArgumentParser, "parse_known_args", side_effect=error):
            with self.assertRaises(RUNNER.CliArgumentError) as caught:
                parser.parse_cli(["m"], required=())
        self.assertEqual("--run-id: invalid value", caught.exception.public_message)


if __name__ == "__main__":
    unittest.main()
