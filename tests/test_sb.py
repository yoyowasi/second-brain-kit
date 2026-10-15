import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/second-brain/scripts/sb.py"


class SecondBrainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="second-brain-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / "vault"
        self.settings = self.root / "settings"
        self.env = dict(os.environ, SECOND_BRAIN_HOME=str(self.settings),
                        SECOND_BRAIN=str(self.vault), PYTHONDONTWRITEBYTECODE="1")
        self.sb("init", str(self.vault))

    def sb(self, *args, exit_code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                                env=self.env, capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, exit_code,
                         f"{args}\n{result.stdout}\n{result.stderr}")
        return result.stdout + result.stderr

    def configure(self, **values):
        path = self.settings / "config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config.update(values)
        path.write_text(json.dumps(config), encoding="utf-8")

    def project(self, title, status="active"):
        path = self.vault / "20_Projects" / f"{title}.md"
        path.write_text(f"---\ntype: project\nstatus: {status}\n"
                        f"created: 2026-10-01T09:00\n---\n# {title}\n"
                        f"- [ ] {title} task\n[[업무]]\n", encoding="utf-8")
        os.utime(path, (946684800, 946684800))
        return path

    def test_starter_lint(self):
        self.assertIn("문제 0건", self.sb("lint"))

    def test_seven_note_kinds(self):
        cases = [("daily", "2026-10-15"), ("weekly", "2026-W42"),
                 ("project", "Test Project"), ("fix", "Test Fix"),
                 ("note", "Test Note"), ("inbox", "Test Inbox"),
                 ("resource", "Test Resource")]
        for kind, title in cases:
            with self.subTest(kind=kind):
                self.sb("new", kind, title)
                paths = list(self.vault.rglob(f"{title}.md"))
                self.assertEqual(len(paths), 1)
                data = paths[0].read_bytes()
                self.assertNotIn(b"<%", data)
                self.assertNotIn(b"\r\n", data)
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertIn(f"type: {kind}", data.decode("utf-8"))

    def test_iso_year_boundary(self):
        output = self.sb("today", "--date", "2027-01-01")
        for expected in ("2026-W53", "2026-12-28", "2027-01-03"):
            self.assertIn(expected, output)
        self.sb("new", "weekly", "--date", "2027-01-01")
        text = (self.vault / "10_Daily/Weekly/2026-W53.md").read_text(encoding="utf-8")
        self.assertIn("start: 2026-12-28", text)
        self.assertIn("end: 2027-01-03", text)

    def test_duplicate_rejected_without_overwrite(self):
        self.sb("new", "inbox", "Unique Title")
        path = self.vault / "00_Inbox/Unique Title.md"
        original = path.read_bytes()
        self.assertIn("이미 있습니다", self.sb("new", "project", "unique title", exit_code=1))
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.vault / "20_Projects/unique title.md").exists())

    def test_existing_vault_init_rejected(self):
        path = self.vault / "Home.md"
        original = path.read_bytes()
        self.sb("init", str(self.vault), exit_code=1)
        self.assertEqual(path.read_bytes(), original)

    def test_dry_run_and_secret_title(self):
        self.sb("new", "inbox", "Preview", "--dry-run")
        self.assertFalse((self.vault / "00_Inbox/Preview.md").exists())
        self.sb("new", "inbox", "API token", exit_code=1)
        self.assertFalse((self.vault / "00_Inbox/API token.md").exists())

    def test_tasks_and_stale_do_not_read_excluded_files(self):
        # Invalid UTF-8 makes any accidental read fail, even without printed contents.
        (self.root / ".obsidian").mkdir()
        for relative in ("10_Daily/2026-10-01.md", "20_Projects/Private.md",
                         "20_Projects/API token.md"):
            (self.vault / relative).write_bytes(b"\xff")
        self.configure(exclude=["10_Daily/2026-10-01.md", "vault/20_Projects/Private.md"])
        self.project("Visible")
        for command in ("tasks", "stale"):
            with self.subTest(command=command):
                output = self.sb(command)
                self.assertIn("[[Visible]]", output)
                for hidden in ("Private", "API token", "2026-10-01"):
                    self.assertNotIn(hidden, output)

    def test_secret_named_project_folder_is_not_read(self):
        folder = self.vault / "secret-projects"
        folder.mkdir()
        (folder / "Unread.md").write_bytes(b"\xff")
        self.configure(folders={"project": "secret-projects"})
        for command in ("tasks", "stale"):
            self.assertNotIn("Unread", self.sb(command))

    def test_outside_folders_rejected_by_all_consumers(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "2026-10-01.md").write_bytes(b"\xff")
        cases = [("inbox", ("new", "inbox", "Escape")),
                 ("daily", ("new", "daily", "2026-10-02")),
                 ("daily", ("tasks",)), ("project", ("tasks",)),
                 ("project", ("stale",)), ("daily", ("today",)),
                 ("weekly", ("today",))]
        for destination in ("../outside", str(outside)):
            for kind, command in cases:
                with self.subTest(destination=destination, kind=kind, command=command):
                    self.configure(folders={kind: destination})
                    self.assertIn("볼트 안", self.sb(*command, exit_code=1))
        self.assertEqual([p.name for p in outside.iterdir()], ["2026-10-01.md"])

    def test_symlink_to_outside_folder_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.vault / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Directory symlink unavailable: {error}")
        self.configure(folders={"inbox": "linked"})
        self.assertIn("볼트 안", self.sb("new", "inbox", "Escape", exit_code=1))
        self.assertFalse((outside / "Escape.md").exists())

    def test_normalized_inside_folder_still_works(self):
        self.configure(folders={"inbox": "00_Inbox/../Custom"})
        self.sb("new", "inbox", "Inside")
        self.assertTrue((self.vault / "Custom/Inside.md").is_file())

    def test_backlinks_normalize_case_and_extension(self):
        links = ["Old", "Old.md", "old", "Folder/OLD.MD#Heading|Alias"]
        for index, link in enumerate(links):
            (self.vault / "00_Inbox" / f"Link {index}.md").write_text(f"[[{link}]]\n", encoding="utf-8")
        for query in ("Old", "old.md", "OLD.MD"):
            with self.subTest(query=query):
                output = self.sb("backlinks", query)
                for index in range(len(links)):
                    self.assertIn(f"Link {index}.md", output)
        self.assertIn("백링크 없음", self.sb("backlinks", "Unrelated"))

    def test_quoted_frontmatter_scalars_and_list_items(self):
        for index, quote in enumerate(("'", '"')):
            title = f"Quoted {index}"
            path = self.project(title, f"{quote}active{quote}")
            text = path.read_text(encoding="utf-8").replace("type: project", f"type: {quote}project{quote}")
            text = text.replace("created:", f"tags:\n  - {quote}tag-{index}{quote}\ncreated:")
            path.write_text(text, encoding="utf-8")
            os.utime(path, (946684800, 946684800))
            with self.subTest(quote=quote):
                self.assertIn(f"{title} task", self.sb("tasks"))
                self.assertIn(f"[[{title}]]", self.sb("stale"))
                self.assertIn("문제 0건", self.sb("lint", str(path)))
                self.assertIn(f"tag-{index}\t1", self.sb("tags"))

    def test_unpaired_quote_is_preserved(self):
        path = self.vault / "00_Inbox/Unpaired.md"
        path.write_text('---\ntype: inbox\ntags: trailing"\ncreated: 2026-10-01T09:00\n---\n', encoding="utf-8")
        self.assertIn('trailing"\t1', self.sb("tags"))


if __name__ == "__main__":
    unittest.main()
