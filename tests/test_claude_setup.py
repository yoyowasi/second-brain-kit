import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/claude_setup.py"
OTHER = {"type": "command", "command": "echo other", "timeout": 5}


def brain_groups(settings):
    return [(event, group) for event, groups in settings["hooks"].items() for group in groups
            if any("brain-" in h.get("command", "") for h in group["hooks"])]


class ClaudeSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="claude-setup-test-")
        self.addCleanup(temporary.cleanup)
        self.claude = Path(temporary.name) / ".claude"
        self.claude.mkdir()
        self.settings = self.claude / "settings.json"
        self.claude_md = self.claude / "CLAUDE.md"

    def run_setup(self, *args, exit_code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, "--claude-dir", str(self.claude)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def backups(self):
        return sorted(p.name for p in self.claude.glob("*.bak-*"))

    def test_install_is_idempotent_and_keeps_other_settings(self):
        stale = {"hooks": [{"type": "command", "command": 'python "$HOME/.claude/hooks/brain-dream.py"', "timeout": 10}]}
        self.settings.write_text(json.dumps({
            "model": "opus",
            "hooks": {"SessionStart": [{"hooks": [OTHER]}, stale, stale],  # 중복 등록된 옛 brain 그룹
                      "PreToolUse": [{"matcher": "Bash", "hooks": [OTHER]}]}}), encoding="utf-8")
        self.claude_md.write_bytes("# 내 지침\r\n- 원래 줄".encode("utf-8"))

        first = self.run_setup("install", "--python", "python3")
        self.assertIn("settings.json: 갱신", first)
        self.assertIn("CLAUDE.md: 갱신", first)
        self.assertEqual(len(self.backups()), 2)
        settings = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["hooks"]["PreToolUse"], [{"matcher": "Bash", "hooks": [OTHER]}])
        self.assertIn({"hooks": [OTHER]}, settings["hooks"]["SessionStart"])
        groups = brain_groups(settings)
        self.assertEqual([event for event, _ in groups], ["SessionStart", "SessionEnd"])
        start = [h["command"] for h in groups[0][1]["hooks"]]
        self.assertEqual(start, ['python3 "$HOME/.claude/hooks/brain-lint-reminder.py"',
                                 'python3 "$HOME/.claude/hooks/brain-dream.py"'])
        self.assertTrue(all(h["timeout"] == 10 for _, g in groups for h in g["hooks"]))
        md = self.claude_md.read_bytes().decode("utf-8")
        self.assertTrue(md.startswith("# 내 지침\r\n- 원래 줄\r\n\r\n<!-- brain:start -->\r\n"))
        self.assertEqual(md.count("<!-- brain:start -->"), 1)
        self.assertIn("# 배운 규칙 (dream)\r\n", md)
        self.assertIn("<!-- dream-last-id: 0 -->\r\n<!-- brain:end -->\r\n", md)
        self.assertNotIn("\n", md.replace("\r\n", ""))
        for name in ("brain_common.py", "brain-journal.py", "brain-dream.py", "brain-lint-reminder.py"):
            self.assertTrue((self.claude / "hooks" / name).is_file(), name)
        for skill in ("inbox", "init-project"):
            self.assertTrue((self.claude / "skills" / skill / "SKILL.md").is_file(), skill)

        settings_before, md_before = self.settings.read_bytes(), self.claude_md.read_bytes()
        second = self.run_setup("install", "--python", "python3")
        self.assertIn("settings.json: 변경 없음", second)
        self.assertIn("CLAUDE.md: 변경 없음", second)
        self.assertEqual(self.settings.read_bytes(), settings_before)
        self.assertEqual(self.claude_md.read_bytes(), md_before)
        self.assertEqual(len(self.backups()), 2)

        third = self.run_setup("install", "--python", "python")  # 명령이 바뀌면 그 그룹만 다시 쓴다
        self.assertIn("settings.json: 갱신", third)
        settings = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(len(brain_groups(settings)), 2)
        self.assertTrue(brain_groups(settings)[0][1]["hooks"][0]["command"].startswith("python \"$HOME"))

    def test_install_creates_missing_files(self):
        out = self.run_setup("install")
        self.assertIn("settings.json: 만듦", out)
        self.assertIn("CLAUDE.md: 만듦", out)
        self.assertEqual(self.backups(), [])
        self.assertEqual(len(brain_groups(json.loads(self.settings.read_text(encoding="utf-8")))), 2)
        self.assertTrue(self.claude_md.read_text(encoding="utf-8").startswith("<!-- brain:start -->\n"))

    def test_existing_brain_block_is_left_alone(self):
        text = "# 지침\n<!-- brain:start -->\n# 배운 규칙 (dream)\n- [L01] 내 규칙\n<!-- dream-last-id: 1 -->\n<!-- brain:end -->\n"
        self.claude_md.write_text(text, encoding="utf-8")
        self.assertIn("brain 구역이 이미 있음", self.run_setup("install"))
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), text)

    def test_invalid_settings_are_not_touched(self):
        for text, reason in (('{"hooks": {,}', "읽지 못해"), ('{"hooks": {"SessionStart": {"hooks": []}}}', "hooks.SessionStart 이 목록이 아님"),
                             ('{"hooks": []}', "객체가 아님")):
            with self.subTest(text=text):
                self.settings.write_text(text, encoding="utf-8")
                out = self.run_setup("install", exit_code=1)
                self.assertIn("고치지 않았습니다", out)
                self.assertIn(reason, out)
                self.assertEqual(self.settings.read_text(encoding="utf-8"), text)
                self.assertEqual(self.backups(), [])
                self.assertFalse(self.claude_md.exists())  # settings 에서 멈추면 CLAUDE.md 도 건드리지 않는다

    def test_warns_when_claude_dir_is_not_home(self):
        out = self.run_setup("install")  # 시험의 --claude-dir 은 임시 폴더라 늘 다르다
        self.assertIn('주의: settings.json 의 hook 명령은 "$HOME/.claude/hooks/..."', out)
        self.assertIn(str(self.claude / "hooks"), out)

    def test_remove_drops_only_brain_hooks(self):
        self.settings.write_text(json.dumps({"hooks": {"SessionEnd": [{"hooks": [OTHER]}]}}), encoding="utf-8")
        self.run_setup("install")
        out = self.run_setup("remove")
        self.assertIn("settings.json: 갱신", out)
        self.assertIn("brain:start", out)
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")),
                         {"hooks": {"SessionEnd": [{"hooks": [OTHER]}]}})
        self.assertIn("<!-- brain:start -->", self.claude_md.read_text(encoding="utf-8"))
        self.assertIn("변경 없음", self.run_setup("remove"))


if __name__ == "__main__":
    unittest.main()
