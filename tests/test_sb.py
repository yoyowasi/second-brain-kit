import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
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

    def sb(self, *args, exit_code=0, bootstrap=None, forbidden_reads=()):
        if forbidden_reads:
            guard = textwrap.dedent('''
                import os
                from pathlib import Path
                blocked_reads = {os.path.normcase(os.path.realpath(p)) for p in __DENIED__}
                original_read_text = Path.read_text
                def guarded_read_text(path, *args, **kwargs):
                    actual = os.path.normcase(os.path.realpath(path))
                    if actual in blocked_reads:
                        raise AssertionError("Forbidden note content read: " + str(path))
                    return original_read_text(path, *args, **kwargs)
                Path.read_text = guarded_read_text
                print("content-read-guard-active")
            ''').replace("__DENIED__", repr([str(p) for p in forbidden_reads]))
            runner = bootstrap or '''
                import runpy, sys
                sys.argv = sys.argv[1:]
                runpy.run_path(sys.argv[0], run_name="__main__")
            '''
            bootstrap = guard + "\n" + textwrap.dedent(runner)
        command = ([sys.executable, "-c", textwrap.dedent(bootstrap), str(SCRIPT), *args]
                   if bootstrap else [sys.executable, str(SCRIPT), *args])
        result = subprocess.run(command, cwd=self.root,
                                env=self.env, capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(result.returncode, exit_code,
                         f"{args}\n{result.stdout}\n{result.stderr}")
        output = result.stdout + result.stderr
        if forbidden_reads:
            self.assertIn("content-read-guard-active", output)
        return output

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
        self.addCleanup(self.remove_directory_link, link)

    @staticmethod
    def remove_directory_link(link):
        if os.path.lexists(link):
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()

    def linked_vault(self):
        obsidian = self.root / "obsidian"
        (obsidian / ".obsidian").mkdir(parents=True)
        alias = obsidian / "Brain"
        self.directory_link(self.vault, alias)
        self.env["SECOND_BRAIN"] = str(alias)
        return obsidian, alias

    def test_starter_lint(self):
        dotfile = self.vault / ".md"
        dotfile.write_text("not a Markdown note", encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", forbidden_reads=[dotfile]))

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
        self.assertIn("이미 노트가 있는 폴더", self.sb("init", str(self.vault), exit_code=1))
        self.assertEqual(path.read_bytes(), original)

    def test_dry_run_and_secret_title(self):
        self.sb("new", "inbox", "Preview", "--dry-run")
        self.assertFalse((self.vault / "00_Inbox/Preview.md").exists())
        self.assertIn("비밀 파일", self.sb("new", "inbox", "API token", exit_code=1))
        self.assertFalse((self.vault / "00_Inbox/API token.md").exists())

    def test_tasks_and_stale_do_not_read_excluded_files(self):
        # Guard actual content reads; decoding errors alone are intentionally tolerated.
        (self.root / ".obsidian").mkdir()
        forbidden = []
        for relative in ("10_Daily/2026-10-01.md", "20_Projects/Private.md",
                         "20_Projects/API token.md"):
            path = self.vault / relative
            path.write_bytes(b"\xff")
            forbidden.append(path)
        self.configure(exclude=["10_Daily/2026-10-01.md", "vault/20_Projects/Private.md"])
        self.project("Visible")
        for command in ("tasks", "stale"):
            with self.subTest(command=command):
                output = self.sb(command, forbidden_reads=forbidden)
                self.assertIn("[[Visible]]", output)
                for hidden in ("Private", "API token", "2026-10-01"):
                    self.assertNotIn(hidden, output)

    def test_secret_named_project_folder_is_not_read(self):
        folder = self.vault / "secret-projects"
        folder.mkdir()
        (folder / "Unread.md").write_bytes(b"\xff")
        self.configure(folders={"project": "secret-projects"})
        for command in ("tasks", "stale"):
            output = self.sb(command, exit_code=1, forbidden_reads=[folder / "Unread.md"])
            self.assertIn("제외된 노트 폴더", output)
            self.assertNotIn("Unread", output)

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
                    self.assertIn("볼트 안", self.sb(*command, exit_code=1,
                                  forbidden_reads=[outside / "2026-10-01.md"]))
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
                         str(alias / "99_System/Templates/Daily.md"),
                         forbidden_reads=[self.vault / "00_Inbox/password.md"])
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
                output = self.sb(command, forbidden_reads=[self.vault / "20_Projects/Excluded.md"])
                self.assertIn("[[Visible]]", output)
                self.assertNotIn("Excluded", output)
        self.assertIn("제외된 경로(읽지 않음)",
                      self.sb("lint", str(alias / "20_Projects/Excluded.md"),
                              forbidden_reads=[self.vault / "20_Projects/Excluded.md"]))

    def test_linked_vault_resolves_links_in_obsidian_parent(self):
        obsidian, alias = self.linked_vault()
        self.configure(read_outside=[".."])
        (obsidian / "Parent.md").write_text("# Parent\n", encoding="utf-8")
        note = alias / "00_Inbox/Root Link.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[Parent]]\n",
                        encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", str(note)))

    def test_unapproved_obsidian_parent_links_are_unresolved(self):
        # The parent is now indexed by name, while its contents still require permission.
        obsidian, alias = self.linked_vault()
        (obsidian / "Parent.md").write_bytes(b"\xff")
        note = alias / "00_Inbox/Root Link.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[Parent]]\n",
                        encoding="utf-8")
        forbidden = [obsidian / "Parent.md"]
        self.assertIn("점검(지정한 파일) 1개, 문제 0건",
                      self.sb("lint", str(note), forbidden_reads=forbidden))
        self.assertIn("문제 0건", self.sb("lint", forbidden_reads=forbidden))
        self.assertIn("제외된 경로(읽지 않음)",
                      self.sb("lint", str(obsidian / "Parent.md"), forbidden_reads=forbidden))
        self.sb("tags", forbidden_reads=forbidden)
        self.sb("backlinks", "Root Link", forbidden_reads=forbidden)

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
                    output = self.sb(command, exit_code=1, forbidden_reads=[note])
                    self.assertIn("제외된 노트 폴더", output)
                    self.assertNotIn("blocked-task", output)
                    self.assertNotIn("[[LinkedPayload]]", output)
                self.assertNotIn("blocked-tag", self.sb("tags", forbidden_reads=[note]))
                self.assertIn("백링크 없음", self.sb("backlinks", "BlockedTarget", forbidden_reads=[note]))
                self.assertIn("문제 0건", self.sb("lint", forbidden_reads=[note]))
                for explicit in (note, self.vault / alias_name / note.name):
                    output = self.sb("lint", str(explicit), forbidden_reads=[note])
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
            output = self.sb(command, forbidden_reads=[note])
            self.assertNotIn("ExternalPayload", output)
            self.assertNotIn("external-task", output)
        self.assertNotIn("external-tag", self.sb("tags", forbidden_reads=[note]))
        self.assertIn("백링크 없음", self.sb("backlinks", "ExternalTarget", forbidden_reads=[note]))
        self.assertIn("문제 0건", self.sb("lint", forbidden_reads=[note]))
        for explicit in (note, link / note.name):
            self.assertIn("점검(지정한 파일) 0개, 문제 0건",
                          self.sb("lint", str(explicit), forbidden_reads=[note]))
        self.configure(folders={"project": "20_Projects/Ext"})
        for command in ("tasks", "stale"):
            self.assertIn("볼트 안", self.sb(command, exit_code=1, forbidden_reads=[note]))
        self.configure(folders={})
        self.sb("new", "inbox", "ExternalPayload", forbidden_reads=[note])
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
                      self.sb("lint", str(source), exit_code=1,
                              forbidden_reads=[outside / "ExternalTarget.md"]))

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
        self.assertIn("점검(지정한 파일) 1개, 문제 0건",
                      self.sb("lint", str(note)))

    def test_directory_loops_are_not_followed(self):
        self.directory_link(self.vault, self.vault / "20_Projects/Loop")
        for command in (("tasks",), ("stale",), ("tags",),
                        ("backlinks", "Missing"), ("lint",)):
            self.sb(*command)
        self.sb("new", "inbox", "Loop Safe")
        self.assertTrue((self.vault / "00_Inbox/Loop Safe.md").is_file())

    def test_broken_directory_link_does_not_crash_commands(self):
        target = self.root / "deleted-target"
        target.mkdir()
        link = self.vault / "20_Projects/Broken"
        self.directory_link(target, link)
        target.rmdir()
        for command in (("tasks",), ("stale",), ("tags",),
                        ("backlinks", "Missing"), ("lint",), ("today",),
                        ("new", "inbox", "Broken Link Safe", "--dry-run")):
            with self.subTest(command=command):
                self.sb(*command)
        self.assertIn("파일 없음", self.sb("lint", str(link), exit_code=1))

    def test_outside_aliases_cannot_bypass_exclusions(self):
        cases = [(self.vault / "Hidden", "Hidden"),
                 (self.vault / "secrets", None),
                 (self.root / "ExternalHidden", str(self.root / "ExternalHidden")),
                 (self.root / "secrets", None)]
        for index, (target, exclusion) in enumerate(cases):
            with self.subTest(target=target):
                target.mkdir()
                alias = self.vault / f"OutsideAlias{index}"
                self.directory_link(target, alias)
                note = target / "BlockedOutside.md"
                # The read spy below rejects content access through both alias and real paths.
                note.write_bytes(b"\xff")
                self.configure(read_outside=[alias.name],
                               exclude=[exclusion] if exclusion else [])
                self.sb("tags", forbidden_reads=[note])
                self.assertIn("백링크 없음", self.sb("backlinks", "BlockedTarget", forbidden_reads=[note]))
                self.assertIn("문제 0건", self.sb("lint", forbidden_reads=[note]))
                for explicit in (note, alias / note.name):
                    output = self.sb("lint", str(explicit), forbidden_reads=[note])
                    self.assertIn("제외된 경로(읽지 않음)", output)
                    self.assertIn("점검(지정한 파일) 0개, 문제 0건", output)
                note.unlink()

    def test_secret_ancestor_and_vault_names_do_not_hide_notes(self):
        secret_parent = self.root / "secret-parent"
        secret_parent.mkdir()
        renamed = secret_parent / "token-vault"
        self.vault.rename(renamed)
        self.vault = renamed
        alias = self.root / "password-alias"
        self.directory_link(self.vault, alias)
        for active_vault in (self.vault, alias):
            with self.subTest(vault=active_vault):
                self.env["SECOND_BRAIN"] = str(active_vault)
                path = self.project("Visible")
                text = path.read_text(encoding="utf-8").replace("status: active", "status: active\ntags: [visible-tag]")
                path.write_text(text, encoding="utf-8")
                self.assertIn("visible-tag\t1", self.sb("tags"))
                self.assertIn("Visible task", self.sb("tasks"))
                self.assertIn("문제 0건", self.sb("lint"))
                self.assertIn("이미 있습니다", self.sb("new", "project", "Visible", exit_code=1))
                self.sb("new", "inbox", "New Allowed", "--dry-run")

    def test_explicitly_excluded_vault_root_reports_reason(self):
        self.configure(exclude=["."])
        for command in (("tags",), ("lint",), ("tasks",),
                        ("stale",), ("today",), ("new", "inbox", "Blocked")):
            with self.subTest(command=command):
                self.assertIn("제외", self.sb(*command, exit_code=1))
        self.assertFalse((self.vault / "00_Inbox/Blocked.md").exists())

    def test_disappearing_directory_is_skipped(self):
        doomed = self.vault / "20_Projects/Disappearing"
        doomed.mkdir()
        bootstrap = '''
            import os, runpy, sys
            from pathlib import Path
            original = os.scandir
            doomed = Path(os.environ["SECOND_BRAIN"]) / "20_Projects/Disappearing"
            class Entries:
                def __init__(self, entries): self.entries = iter(entries)
                def __iter__(self): return self
                def __next__(self): return next(self.entries)
                def __enter__(self): return self
                def __exit__(self, *args): self.close()
                def close(self): pass
            def scandir(path):
                scan = original(path)
                if os.path.abspath(path) != str(doomed.parent):
                    return scan
                with scan:
                    entries = list(scan)
                if doomed.exists():
                    doomed.rmdir()
                    print("removed-directory-before-stat")
                return Entries(entries)
            os.scandir = scandir
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        output = self.sb("tasks", bootstrap=bootstrap)
        self.assertIn("removed-directory-before-stat", output)
        self.assertFalse(doomed.exists())

    def test_unresolvable_outside_roots_are_skipped(self):
        outside = self.root / "unresolvable"
        outside.mkdir()
        (outside / "Unread.md").write_bytes(b"\xff")
        self.configure(read_outside=[str(outside)])
        bootstrap = '''
            import os, runpy, sys
            original = os.path.realpath
            blocked = os.path.normcase(os.path.abspath("unresolvable"))
            def realpath(path, *args, **kwargs):
                if os.path.normcase(os.path.abspath(path)) == blocked:
                    print("injected-realpath-failure")
                    raise ERROR("unresolvable fixture")
                return original(path, *args, **kwargs)
            os.path.realpath = realpath
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for error in ("OSError", "RuntimeError"):
            for command in (("tags",), ("backlinks", "Missing"), ("lint",),
                            ("new", "inbox", "No Outside Read", "--dry-run")):
                with self.subTest(error=error, command=command):
                    self.assertIn("injected-realpath-failure",
                                  self.sb(*command, bootstrap=bootstrap.replace("ERROR", error),
                                          forbidden_reads=[outside / "Unread.md"]))

    def test_unresolvable_vault_root_reports_reason(self):
        bootstrap = '''
            import os, runpy, sys
            original = os.path.realpath
            blocked = os.path.normcase(os.path.abspath(os.environ["SECOND_BRAIN"]))
            def realpath(path, *args, **kwargs):
                if os.path.normcase(os.path.abspath(path)) == blocked:
                    print("injected-realpath-failure")
                    raise ERROR("unresolvable fixture")
                return original(path, *args, **kwargs)
            os.path.realpath = realpath
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for error in ("OSError", "RuntimeError"):
            with self.subTest(error=error):
                output = self.sb("tags", exit_code=1,
                                 bootstrap=bootstrap.replace("ERROR", error))
                self.assertIn("injected-realpath-failure", output)
                self.assertIn("볼트 실제 경로를 확인할 수 없습니다", output)

    def test_inaccessible_explicit_lint_file_is_skipped(self):
        note = self.vault / "00_Inbox/Unread.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n", encoding="utf-8")
        bootstrap = '''
            import os, runpy, sys
            from pathlib import Path
            original = Path.is_file
            blocked = os.path.normcase(os.path.abspath(sys.argv[3]))
            def is_file(path):
                if os.path.normcase(os.path.abspath(path)) == blocked:
                    print("injected-file-permission-error")
                    raise PermissionError("inaccessible fixture")
                return original(path)
            Path.is_file = is_file
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        output = self.sb("lint", str(note), bootstrap=bootstrap, forbidden_reads=[note])
        self.assertIn("injected-file-permission-error", output)
        self.assertIn("제외된 경로(읽지 않음)", output)
        self.assertIn("점검(지정한 파일) 0개, 문제 0건", output)

    def test_parent_name_index_keeps_exclusions_and_skips_links(self):
        obsidian, alias = self.linked_vault()
        (obsidian / "Hidden.md").write_bytes(b"\xff")
        (obsidian / "API token.md").write_bytes(b"\xff")
        hidden = obsidian / "secret-folder"
        hidden.mkdir()
        (hidden / "Private.md").write_bytes(b"\xff")
        external = self.root / "external-parent-index"
        external.mkdir()
        (external / "External.md").write_bytes(b"\xff")
        self.directory_link(external, obsidian / "Linked")
        self.configure(exclude=["Hidden.md"])
        source = alias / "00_Inbox/Source.md"
        prefix = "---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
        forbidden = [obsidian / "Hidden.md", obsidian / "API token.md",
                     hidden / "Private.md", external / "External.md"]
        for target in ("Hidden", "API token", "Private", "External"):
            with self.subTest(target=target):
                source.write_text(prefix + f"[[{target}]]\n", encoding="utf-8")
                self.assertIn(f"깨진 링크 [[{target}]]",
                              self.sb("lint", str(source), exit_code=1, forbidden_reads=forbidden))

    def test_render_rejects_path_traversal(self):
        outside = self.root / "render-payload.md"
        outside.write_text("DO-NOT-PRINT-PAYLOAD", encoding="utf-8")
        for template in ("../../x", "..\\..\\x", "../render-payload", "..", "Daily/../Daily", "Daily\\Daily"):
            with self.subTest(template=template):
                output = self.sb("render", template, exit_code=1)
                self.assertIn("템플릿 이름", output)
                self.assertNotIn("DO-NOT-PRINT-PAYLOAD", output)

    def test_backlinks_deduplicate_overlapping_real_roots(self):
        source = self.project("Only Once")
        source.write_text(source.read_text(encoding="utf-8") + "[[Home]]\n", encoding="utf-8")
        link = self.vault / "Repeated"
        self.directory_link(self.vault / "20_Projects", link)
        self.configure(read_outside=["20_Projects", "Repeated", str(self.vault)])
        output = self.sb("backlinks", "Home")
        self.assertEqual(output.count("Only Once.md"), 1, output)

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
