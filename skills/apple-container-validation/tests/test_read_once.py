#!/usr/bin/env python3
"""manifestを1回だけ読み、検証とハッシュに同じバイト列を使う契約のテスト。"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load(ROOT / "scripts" / "run-matrix.py", "acv_read_once_runner")
VALIDATOR = load(ROOT / "scripts" / "validate-manifest.py", "acv_read_once_validator")


def manifest() -> dict:
    return {
        "version": 1, "slug": "read-once", "claim": "claim", "hypothesis": "hypothesis",
        "falsificationCriteria": [{"id": "criterion", "description": "criterion description"}],
        "image": {"tag": "example:1"}, "defaults": {"maxConcurrency": 1}, "mounts": [],
        "cases": [{
            "id": "case", "group": "target", "description": "description", "relation": "falsify",
            "criterionIds": ["criterion"], "command": ["true"], "oracle": {"exitCode": 0},
        }],
    }


def capture(args, **kwargs):
    if args == ["container", "--version"]:
        return mock.Mock(returncode=0, stdout="container 1\n", stderr="")
    if args == ["container", "system", "status"]:
        return mock.Mock(returncode=0, stdout="running\n", stderr="")
    if args[:3] == ["container", "image", "inspect"]:
        return mock.Mock(returncode=0, stdout="{}", stderr="")
    raise AssertionError(args)


class ManifestReadOnceTests(unittest.TestCase):
    def test_runner_reads_manifest_bytes_once_and_hashes_same_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            path = base / "manifest.json"
            path.write_text(json.dumps(manifest()), encoding="utf-8")
            target = path.resolve()
            results = base / "results"
            modes: list[str] = []
            original_open = pathlib.Path.open

            def counting_open(self, *args, **kwargs):
                mode = args[0] if args else kwargs.get("mode", "r")
                if Path(self).resolve() == target:
                    modes.append(mode)
                return original_open(self, *args, **kwargs)

            argv = ["run-matrix.py", str(path), "--run-id", "run", "--dry-run", "--results-dir", str(results)]
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                RUNNER.shutil, "which", return_value="/bin/container"
            ), mock.patch.object(RUNNER, "run_capture", side_effect=capture), mock.patch.object(
                pathlib.Path, "open", counting_open
            ), mock.patch.object(
                RUNNER, "sha256_file", wraps=RUNNER.sha256_file
            ) as hashed, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = RUNNER.main()
            self.assertEqual(0, code, stderr.getvalue())
            # 自己検査: pathlibの実装変更で数え漏れた場合に偽陽性で通らないようにする。
            self.assertGreaterEqual(len(modes), 1)
            self.assertEqual(1, modes.count("rb"), modes)
            self.assertEqual(1, modes.count("r"), modes)
            self.assertEqual(2, len(modes), modes)
            hashed_paths = [Path(call.args[0]).resolve() for call in hashed.call_args_list]
            self.assertNotIn(target, hashed_paths)
            run_manifest = json.loads((results / "run" / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), run_manifest["manifestSha256"])

    def test_load_validated_manifest_matches_validate_manifest(self):
        invalid = manifest()
        invalid["version"] = 2
        inputs = {
            "valid": json.dumps(manifest()).encode("utf-8"),
            "errors": json.dumps(invalid).encode("utf-8"),
            "invalid-json": b"{",
            "non-utf8": b"\xff\xfe{}",
            "lone-surrogate": b'{"value": "\\ud800"}',
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = {}
            for name, raw in inputs.items():
                paths[name] = base / f"{name}.json"
                paths[name].write_bytes(raw)
            paths["missing"] = base / "missing.json"
            paths["directory"] = base / "directory"
            paths["directory"].mkdir()
            for name, path in paths.items():
                with self.subTest(name=name):
                    try:
                        expected = VALIDATOR.validate_manifest(path)
                    except ValueError as exc:
                        with self.assertRaises(ValueError) as caught:
                            VALIDATOR.load_validated_manifest(path)
                        self.assertIs(type(exc), type(caught.exception))
                        self.assertEqual(str(exc), str(caught.exception))
                        continue
                    actual = VALIDATOR.load_validated_manifest(path)
                    self.assertEqual(4, len(actual))
                    self.assertEqual(expected, actual[:3])
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), actual[3])
            self.assertEqual([], VALIDATOR.validate_manifest(paths["valid"])[1])
            self.assertTrue(VALIDATOR.validate_manifest(paths["errors"])[1])
            for name in ("invalid-json", "non-utf8", "lone-surrogate", "missing", "directory"):
                with self.subTest(raises=name), self.assertRaises(ValueError):
                    VALIDATOR.validate_manifest(paths[name])


if __name__ == "__main__":
    unittest.main()
