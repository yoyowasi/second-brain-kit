import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


KIT = Path(__file__).resolve().parents[1]
SCRIPT = KIT / "tools/claude_setup.py"
OTHER = {"type": "command", "command": "echo other", "timeout": 5}


def tree(root):
    """폴더 안 파일의 상대 경로 → 내용."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def kit_skill_files():
    return {name for name in tree(KIT / "skills" / "second-brain")
            if "__pycache__" not in name and name.rsplit("/", 1)[-1] not in ("local.md", "config.json")}


def brain_groups(settings):
    return [(event, group) for event, groups in settings["hooks"].items() for group in groups
            if any("brain-" in h.get("command", "") for h in group["hooks"])]


class ClaudeSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="claude-setup-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)  # 가짜 홈 폴더. Codex·Antigravity 스킬도 여기 아래로만 간다
        self.claude = self.home / ".claude"
        self.claude.mkdir()
        self.settings = self.claude / "settings.json"
        self.claude_md = self.claude / "CLAUDE.md"
        self.codex_skill = self.home / ".agents" / "skills" / "second-brain"
        self.antigravity_skill = self.home / ".gemini" / "config" / "skills" / "second-brain"

    def run_setup(self, *args, exit_code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, "--claude-dir", str(self.claude),
                                 "--home", str(self.home)],
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
        skill = self.claude / "skills" / "second-brain"
        self.assertIn(f"Installed: {skill}", out)
        self.assertEqual(set(tree(skill)), kit_skill_files())
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), [".claude"])  # 기본은 Claude Code 만

    def test_antigravity_gets_only_second_brain_skill_and_rerun_is_idempotent(self):
        out = self.run_setup("install", "--antigravity")
        self.assertIn(f"Installed: {self.antigravity_skill}", out)
        files = tree(self.antigravity_skill)
        self.assertEqual(set(files), kit_skill_files())
        for name in ("SKILL.md", "scripts/sb.py", "references/capture.md", "assets/starter-vault/AGENTS.md"):
            self.assertIn(name, files)
        self.assertEqual(files, tree(self.claude / "skills" / "second-brain"))
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), [".claude", ".gemini"])  # Codex 는 안 깐다
        self.assertEqual(sorted(p.name for p in (self.home / ".gemini").iterdir()), ["config"])
        self.assertEqual(sorted(p.name for p in (self.home / ".gemini" / "config").iterdir()), ["skills"])
        self.assertEqual(sorted(p.name for p in self.antigravity_skill.parent.iterdir()), ["second-brain"])

        whole = tree(self.home)
        again = self.run_setup("install", "--antigravity")
        self.assertIn(f"Installed: {self.antigravity_skill}", again)
        self.assertIn("settings.json: 변경 없음", again)
        self.assertEqual(tree(self.home), whole)  # 다시 깔아도 파일·내용이 그대로, 백업도 새로 안 생긴다

    def test_all_installs_three_targets_but_claude_extras_only_in_claude(self):
        out = self.run_setup("install", "--all")
        claude_skill = self.claude / "skills" / "second-brain"
        for skill in (claude_skill, self.codex_skill, self.antigravity_skill):
            self.assertIn(f"Installed: {skill}", out)
            self.assertEqual(tree(skill), tree(claude_skill))
        self.assertEqual(set(tree(claude_skill)), kit_skill_files())
        for skills in (self.codex_skill.parent, self.antigravity_skill.parent):  # inbox·init-project 는 Claude Code 전용
            self.assertEqual(sorted(p.name for p in skills.iterdir()), ["second-brain"])
        self.assertEqual(sorted(p.name for p in (self.claude / "skills").iterdir()), ["inbox", "init-project", "second-brain"])
        for skill in (self.codex_skill, self.antigravity_skill):  # hook·settings.json·CLAUDE.md 도 Claude Code 에만
            top = self.home / skill.relative_to(self.home).parts[0]
            self.assertEqual([p for p in top.rglob("*") if p.is_file() and skill not in p.parents], [])
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), [".agents", ".claude", ".gemini"])

        whole = tree(self.home)
        self.run_setup("install", "--codex", "--antigravity")  # --all 과 같은 결과
        self.assertEqual(tree(self.home), whole)

    def test_skill_copy_skips_personal_files_and_pycache(self):
        spec = importlib.util.spec_from_file_location("claude_setup_under_test", SCRIPT)
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        fake = self.home / "kit"
        for name in ("SKILL.md", "local.md", "config.json", "local.example.md", "scripts/sb.py",
                     "scripts/__pycache__/sb.cpython-39.pyc", "assets/vault/.obsidian/app.json", "assets/vault/local.md"):
            (fake / "skills" / "second-brain" / name).parent.mkdir(parents=True, exist_ok=True)
            (fake / "skills" / "second-brain" / name).write_text(name, encoding="utf-8")
        setup.KIT = fake
        with contextlib.redirect_stdout(io.StringIO()):
            setup.copy_skill(self.antigravity_skill)
        self.assertEqual(sorted(tree(self.antigravity_skill)),
                         ["SKILL.md", "assets/vault/.obsidian/app.json", "local.example.md", "scripts/sb.py"])

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

    def test_remove_names_skill_copies_and_keeps_files(self):
        self.run_setup("install", "--all")
        before = tree(self.home / ".gemini")
        out = self.run_setup("remove")  # remove 는 hook 등록만 뺀다. 스킬 사본은 지우지 않고 위치만 알려 준다
        for skill in (self.claude / "skills" / "second-brain", self.codex_skill, self.antigravity_skill):
            self.assertIn(str(skill), out)
        self.assertEqual(tree(self.home / ".gemini"), before)
        shutil.rmtree(self.home / ".gemini")
        self.assertNotIn(str(self.antigravity_skill), self.run_setup("remove"))

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "install.ps1 은 Windows PowerShell 에서만 시험한다")
    def test_install_ps1_forwards_switches(self):
        # python 을 인자만 찍는 함수로 바꾸고 PATH 에서도 빼서, 실제 설치(~/.claude 쓰기)는 어떤 경우에도 돌지 않는다
        powershell = shutil.which("powershell")
        script = str(KIT / "install.ps1").replace("'", "''")
        env = dict(os.environ, PATH=str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"))
        for switches, flags in (("", []), ("-Codex", ["--codex"]), ("-Antigravity", ["--antigravity"]),
                                ("-All", ["--codex", "--antigravity"]), ("-Codex -All", ["--codex", "--antigravity"])):
            with self.subTest(switches=switches):
                command = ("function python { $args | ForEach-Object { 'ARG ' + $_ }; $global:LASTEXITCODE = 0 }; "
                           f"& '{script}' {switches}")
                result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                args = [line[4:] for line in result.stdout.splitlines() if line.startswith("ARG ")]
                for name in ("install", "--claude-dir", "--home"):
                    self.assertIn(name, args)
                self.assertEqual([a for a in args if a in ("--codex", "--antigravity", "--all")], flags)


if __name__ == "__main__":
    unittest.main()
