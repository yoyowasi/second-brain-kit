"""brain hook 시나리오(brain_hooks_scenario.py)를 별도 프로세스로 돌린다.

시나리오는 환경 변수와 모듈 상태를 바꾸므로 다른 시험과 같은 프로세스에서 돌리지 않는다.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest


SCENARIO = Path(__file__).resolve().with_name("brain_hooks_scenario.py")


class BrainHooksTests(unittest.TestCase):
    def test_scenario(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, str(SCENARIO)], capture_output=True, env=env, timeout=600)
        out = r.stdout.decode("utf-8", "replace")
        failed = [line for line in out.splitlines() if line.startswith("FAIL")]
        summary = next((line for line in out.splitlines() if line.startswith("합계:")), "")
        self.assertEqual(r.returncode, 0, "\n".join(failed) or out[-3000:] + r.stderr.decode("utf-8", "replace")[-3000:])
        self.assertTrue(summary, out[-3000:])


if __name__ == "__main__":
    unittest.main()
