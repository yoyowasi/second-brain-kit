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

    def directory_link(self, target, link):
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)

    def linked_vault(self):
        obsidian = self.root / "obsidian"
        (obsidian / ".obsidian").mkdir(parents=True)
        alias = obsidian / "Brain"
        self.directory_link(self.vault, alias)
        self.env["SECOND_BRAIN"] = str(alias)
        return obsidian, alias

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
            self.assertNotIn("Unread", self.sb(command, exit_code=1))

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

    def test_vault_prefix_sibling_rejected(self):
        sibling = self.root / "vault-x"
        sibling.mkdir()
        self.configure(folders={"inbox": "../vault-x"})
        self.assertIn("볼트 안", self.sb("new", "inbox", "Escape", exit_code=1))
        self.assertFalse((sibling / "Escape.md").exists())

    def test_linked_outside_folder_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.vault / "linked"
        self.directory_link(outside, link)
        self.configure(folders={"inbox": "linked"})
        self.assertIn("볼트 안", self.sb("new", "inbox", "Escape", exit_code=1))
        self.assertFalse((outside / "Escape.md").exists())

    def test_linked_vault_lint_preserves_exclusions(self):
        _, alias = self.linked_vault()
        (self.vault / "00_Inbox/password.md").write_bytes(b"\xff")
        output = self.sb("lint", str(alias / "00_Inbox/password.md"),
                         str(alias / "99_System/Templates/Daily.md"))
        self.assertIn("제외된 경로(읽지 않음)", output)
        self.assertIn("건너뜀(점검 대상 아님", output)
        self.assertIn("점검(지정한 파일) 0개, 문제 0건", output)

    def test_linked_vault_keeps_logical_paths_and_obsidian_root(self):
        obsidian, alias = self.linked_vault()
        output = self.sb("where")
        self.assertIn(f"vault: {alias}\n", output)
        self.assertIn(f"obsidian_root: {obsidian}\n", output)
        self.assertIn(str(alias / "00_Inbox/From Alias.md"),
                      self.sb("new", "inbox", "From Alias"))
        self.assertTrue((self.vault / "00_Inbox/From Alias.md").is_file())

    def test_linked_vault_root_excludes_apply_to_tasks_and_stale(self):
        _, alias = self.linked_vault()
        (self.vault / "20_Projects/Excluded.md").write_bytes(b"\xff")
        self.configure(exclude=["Brain/20_Projects/Excluded.md"])
        self.project("Visible")
        for command in ("tasks", "stale"):
            with self.subTest(command=command):
                output = self.sb(command)
                self.assertIn("[[Visible]]", output)
                self.assertNotIn("Excluded", output)
        self.assertIn("제외된 경로(읽지 않음)",
                      self.sb("lint", str(alias / "20_Projects/Excluded.md")))

    def test_linked_vault_resolves_links_in_obsidian_parent(self):
        obsidian, alias = self.linked_vault()
        self.configure(read_outside=[".."])
        (obsidian / "Parent.md").write_text("# Parent\n", encoding="utf-8")
        note = alias / "00_Inbox/Root Link.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[Parent]]\n",
                        encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", str(note)))

    def test_unapproved_obsidian_parent_links_are_unresolved(self):
        obsidian, alias = self.linked_vault()
        (obsidian / "Parent.md").write_text("# Parent\n", encoding="utf-8")
        note = alias / "00_Inbox/Root Link.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[Parent]]\n",
                        encoding="utf-8")
        self.assertIn("깨진 링크 [[Parent]]", self.sb("lint", str(note), exit_code=1))

    def test_excluded_directory_aliases_are_rejected(self):
        (self.root / ".obsidian").mkdir()
        for target_name, alias_name, exclusion in (
                ("Hidden", "Alias", "Hidden"),
                ("Hidden2", "Alias2", "vault/Hidden2"),
                ("Hidden3", "Alias3", "Alias3"),
                ("secrets", "Alias4", None)):
            with self.subTest(target=target_name, exclusion=exclusion):
                target = self.vault / target_name
                target.mkdir()
                self.directory_link(target, self.vault / alias_name)
                note = target / "LinkedPayload.md"
                note.write_text("---\ntype: project\nstatus: active\ntags: [blocked-tag]\n"
                                "created: 2026-10-01T09:00\n---\n# LinkedPayload\n"
                                "- [ ] blocked-task\n[[BlockedTarget]]\n", encoding="utf-8")
                os.utime(note, (946684800, 946684800))
                self.configure(exclude=[exclusion] if exclusion else [],
                               folders={"project": alias_name})
                for command in ("tasks", "stale"):
                    output = self.sb(command, exit_code=1)
                    self.assertNotIn("blocked-task", output)
                    self.assertNotIn("[[LinkedPayload]]", output)
                self.assertNotIn("blocked-tag", self.sb("tags"))
                self.assertIn("백링크 없음", self.sb("backlinks", "BlockedTarget"))
                self.assertIn("문제 0건", self.sb("lint"))
                for explicit in (note, self.vault / alias_name / note.name):
                    output = self.sb("lint", str(explicit))
                    self.assertIn("점검(지정한 파일) 0개, 문제 0건", output)
                # Keep every earlier target excluded during the next subtest.
                note.unlink()

    def test_external_junction_is_not_scanned_or_used_for_duplicates(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.vault / "20_Projects/Ext"
        self.directory_link(outside, link)
        note = outside / "ExternalPayload.md"
        note.write_text("---\ntype: project\nstatus: active\ntags: [external-tag]\n"
                        "created: 2026-10-01T09:00\n---\n# ExternalPayload\n"
                        "- [ ] external-task\n[[ExternalTarget]]\n", encoding="utf-8")
        os.utime(note, (946684800, 946684800))
        for command in ("tasks", "stale"):
            output = self.sb(command)
            self.assertNotIn("ExternalPayload", output)
            self.assertNotIn("external-task", output)
        self.assertNotIn("external-tag", self.sb("tags"))
        self.assertIn("백링크 없음", self.sb("backlinks", "ExternalTarget"))
        self.assertIn("문제 0건", self.sb("lint"))
        for explicit in (note, link / note.name):
            self.assertIn("점검(지정한 파일) 0개, 문제 0건",
                          self.sb("lint", str(explicit)))
        self.configure(folders={"project": "20_Projects/Ext"})
        for command in ("tasks", "stale"):
            self.sb(command, exit_code=1)
        self.configure(folders={})
        self.sb("new", "inbox", "ExternalPayload")
        self.assertTrue((self.vault / "00_Inbox/ExternalPayload.md").is_file())

    def test_link_index_does_not_follow_unapproved_external_junction(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.directory_link(outside, self.vault / "Ext")
        (outside / "ExternalTarget.md").write_text("# ExternalTarget\n", encoding="utf-8")
        source = self.vault / "00_Inbox/Source.md"
        source.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
                          "[[ExternalTarget]]\n", encoding="utf-8")
        self.assertIn("깨진 링크 [[ExternalTarget]]",
                      self.sb("lint", str(source), exit_code=1))

    def test_approved_outside_root_is_read_and_labeled_by_real_location(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.vault / "Ext"
        self.directory_link(outside, link)
        note = outside / "Allowed.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
                        "[[Home]]\n", encoding="utf-8")
        self.configure(read_outside=["Ext"])
        output = self.sb("backlinks", "Home")
        self.assertIn("Allowed.md\t볼트 밖", output)
        self.assertNotIn("Allowed.md\t볼트 안", output)
        self.assertIn("점검(지정한 파일) 1개, 문제 0건",
                      self.sb("lint", str(link / note.name)))

    def test_directory_loops_are_not_followed(self):
        self.directory_link(self.vault, self.vault / "20_Projects/Loop")
        for command in (("tasks",), ("stale",), ("tags",),
                        ("backlinks", "Missing"), ("lint",)):
            self.sb(*command)
        self.sb("new", "inbox", "Loop Safe")
        self.assertTrue((self.vault / "00_Inbox/Loop Safe.md").is_file())

    def test_normalized_inside_folder_still_works(self):
        self.configure(folders={"inbox": "00_Inbox/../Custom"})
        self.sb("new", "inbox", "Inside")
        self.assertTrue((self.vault / "Custom/Inside.md").is_file())

    def test_backlinks_normalize_case_and_extension(self):
        links = ["Old", "Old.md", "old", "Folder/OLD.MD#Heading|Alias"]
        for index, link in enumerate(links):
            (self.vault / "00_Inbox" / f"Link {index}.md").write_text(f"[[{link}]]\n", encoding="utf-8")
        (self.vault / "00_Inbox/Similar.md").write_text("[[Bold]]\n[[Old Notes]]\n", encoding="utf-8")
        for query in ("Old", "old.md", "OLD.MD"):
            with self.subTest(query=query):
                output = self.sb("backlinks", query)
                for index in range(len(links)):
                    self.assertIn(f"Link {index}.md", output)
                self.assertNotIn("Similar.md", output)
        self.assertIn("백링크 없음", self.sb("backlinks", "Unrelated"))

    def test_lint_normalizes_links_and_inbound_names(self):
        target = self.vault / "50_Notes/Old.md"
        target.write_text("---\ntype: note\ncreated: 2026-10-01T09:00\n---\n# Old\n", encoding="utf-8")
        source = self.vault / "00_Inbox/Source.md"
        for link in ("Old.md", "old", "50_notes/OLD.MD"):
            with self.subTest(link=link):
                source.write_text(f"---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[{link}]]\n", encoding="utf-8")
                self.assertIn("문제 0건", self.sb("lint", str(source), str(target)))

    def test_lint_strips_only_one_md_extension(self):
        target = self.vault / "50_Notes/Double.md.md"
        target.write_text("---\ntype: note\ncreated: 2026-10-01T09:00\n---\n# Double.md\n", encoding="utf-8")
        source = self.vault / "00_Inbox/Double Link.md"
        prefix = "---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
        source.write_text(prefix + "[[DOUBLE.MD.MD]]\n", encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", str(source), str(target)))
        source.write_text(prefix + "[[Double.md]]\n", encoding="utf-8")
        self.assertIn("깨진 링크 [[Double.md]]", self.sb("lint", str(source), exit_code=1))

    def test_inline_tags_unquote_each_item(self):
        (self.vault / "00_Inbox/Inline.md").write_text(
            "---\ntype: inbox\ntags: ['alpha', \"beta\"]\ncreated: 2026-10-01T09:00\n---\n", encoding="utf-8")
        (self.vault / "00_Inbox/Block.md").write_text(
            "---\ntype: inbox\ntags:\n  - alpha\n  - beta\ncreated: 2026-10-01T09:00\n---\n", encoding="utf-8")
        rows = dict(line.split("\t") for line in self.sb("tags").splitlines())
        self.assertEqual(rows.get("alpha"), "2")
        self.assertEqual(rows.get("beta"), "2")
        self.assertNotIn("'alpha'", rows)
        self.assertNotIn('"beta"', rows)

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
