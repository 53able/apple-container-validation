#!/usr/bin/env python3
"""manifestとresume時のattemptログを1回だけ読み、検証とハッシュに同じバイト列を使う契約のテスト。"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import subprocess
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
RUN_MATRIX_TESTS = load(ROOT / "tests" / "test_run_matrix.py", "acv_read_once_run_matrix_tests")


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


def job_manifest() -> dict:
    return {
        "image": {"tag": "example:1"},
        "defaults": {"timeoutSeconds": 10, "retries": 0},
        "mounts": [],
    }


def recording_open(targets: dict[Path, str]):
    """Path.openをラップし、対象パスごとに開いたモードを記録するpatchと記録先を返す。"""
    opened: dict[str, list[str]] = {name: [] for name in targets.values()}
    original_open = pathlib.Path.open

    def counting_open(self, *args, **kwargs):
        name = targets.get(Path(self).resolve())
        if name is not None:
            opened[name].append(args[0] if args else kwargs.get("mode", "r"))
        return original_open(self, *args, **kwargs)

    return mock.patch.object(pathlib.Path, "open", counting_open), opened


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
            open_patch, opened = recording_open({target: "manifest"})
            modes = opened["manifest"]
            argv = ["run-matrix.py", str(path), "--run-id", "run", "--dry-run", "--results-dir", str(results)]
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                RUNNER.shutil, "which", return_value="/bin/container"
            ), mock.patch.object(RUNNER, "run_capture", side_effect=capture), open_patch, mock.patch.object(
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


class ResumeAttemptLogReadOnceTests(unittest.TestCase):
    def test_resume_reads_each_attempt_log_once(self):
        fixture = RUN_MATRIX_TESTS.ResumeResultTests()
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            result_path = fixture.seed_resume_result(run_root)
            job_root = result_path.parent
            open_patch, opened = recording_open({
                (job_root / name).resolve(): name
                for name in ("stdout.log", "stderr.log", "attempts/1/stdout.log", "attempts/1/stderr.log")
            })
            with open_patch:
                existing, status, *_ = RUNNER._verify_resume_result(
                    fixture.manifest(), fixture.case(), 1, "test-run",
                    run_root, run_root, job_root, result_path,
                )
        self.assertEqual("oracle-pass", status)
        self.assertEqual("resume-case-r1", existing["jobId"])
        for name, modes in opened.items():
            with self.subTest(log=name):
                self.assertEqual(["rb"], modes)

    def test_fresh_attempt_logs_are_reread_once_after_write(self):
        # 回帰防止用（変更前後とも通る）: 新規実行で書いたattemptログを、書き込み後にディスクから
        # ちょうど1回（0回ではない）読み直してsha256を取る不変条件を固定する。
        test_manifest = job_manifest()
        case = {
            "id": "fresh-case", "group": "target", "description": "description",
            "relation": "support", "criterionIds": ["criterion"], "command": ["true"],
            "oracle": {"exitCode": 0, "stdoutContains": ["ok"]},
        }

        def completed_capture(args, **kwargs):
            if args[:2] == ["container", "run"]:
                return mock.Mock(returncode=0, stdout="ok\n", stderr="note\n")
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            attempt_root = run_root / "jobs" / "fresh-case-r1" / "attempts" / "1"
            open_patch, opened = recording_open({
                (attempt_root / name).resolve(): name for name in ("stdout.log", "stderr.log")
            })
            with mock.patch.object(RUNNER, "run_capture", side_effect=completed_capture), open_patch:
                result = RUNNER.execute_job(test_manifest, case, 1, "run", run_root, run_root, False)
            attempt = result["attempts"][0]
            self.assertEqual("oracle-pass", result["status"])
            self.assertEqual(
                hashlib.sha256((attempt_root / "stdout.log").read_bytes()).hexdigest(),
                attempt["stdoutSha256"],
            )
            self.assertEqual(
                hashlib.sha256((attempt_root / "stderr.log").read_bytes()).hexdigest(),
                attempt["stderrSha256"],
            )
        for name, modes in opened.items():
            with self.subTest(log=name):
                self.assertEqual(["rb"], modes)

    def test_timeout_crlf_log_oracle_matches_on_resume(self):
        test_manifest = job_manifest()
        case = {
            "id": "crlf-case", "group": "target", "description": "description",
            "relation": "support", "criterionIds": ["criterion"], "command": ["true"],
            "oracle": {"exitCode": 0, "stdoutContains": ["A\nB"]}, "retries": 0,
        }

        def timeout_capture(args, **kwargs):
            if args[:2] == ["container", "run"]:
                raise subprocess.TimeoutExpired(args, 1, output=b"A\r\nB", stderr=b"")
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            with mock.patch.object(RUNNER, "run_capture", side_effect=timeout_capture), mock.patch.object(
                RUNNER.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="", stderr="")
            ):
                fresh = RUNNER.execute_job(test_manifest, case, 1, "run", run_root, run_root, False)
            job_root = run_root / "jobs" / "crlf-case-r1"
            self.assertEqual(b"A\r\nB", (job_root / "attempts" / "1" / "stdout.log").read_bytes())
            self.assertEqual("timeout", fresh["status"])
            persisted = json.loads((job_root / "result.json").read_text(encoding="utf-8"))
            self.assertIn("stdoutContains[0] failed", persisted["oracleFailures"])
            with mock.patch.object(RUNNER, "run_capture", side_effect=AssertionError("resume must not run")):
                resumed = RUNNER.execute_job(
                    test_manifest, case, 1, "run", run_root, run_root, False,
                    persist_resume_rebind=False,
                )
        self.assertEqual(fresh["oracleFailures"], resumed["oracleFailures"])
        self.assertEqual("timeout", resumed["status"])


if __name__ == "__main__":
    unittest.main()
