"""Lightweight checks for benchmark reporting; no benchmark fixture is created."""
import argparse
from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("benchmark_sb", Path(__file__).with_name("benchmark_sb.py"))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_temporary_paths_are_redacted_with_windows_variants(self):
        root = r"C:\Users\PrivateName\Temp\sb-benchmark-123"
        output = root + r"\vault\note.md " + root.upper().replace("\\", "/") + "/settings"
        self.assertEqual(benchmark.redact_output(output, root),
                         r"<tmp>\vault\note.md <tmp>/settings")
        self.assertEqual(benchmark.redact_output("/tmp/unique/vault", "/tmp/unique"),
                         "<tmp>/vault")

    def test_invalid_ref_has_actionable_error_without_traceback(self):
        error = io.StringIO()
        with patch.object(benchmark, "git", side_effect=subprocess.CalledProcessError(128, "git")):
            with redirect_stderr(error), self.assertRaises(SystemExit) as result:
                benchmark.validate_refs(argparse.ArgumentParser(), ["missing-ref"])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("--refs", error.getvalue())
        self.assertIn("missing-ref", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
