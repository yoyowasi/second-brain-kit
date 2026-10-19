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

    def test_init_and_setup_preserve_path_case(self):
        target = self.root / "MixedCaseParent" / "MyBrainVault"
        output = self.sb("init", str(target))
        self.assertIn(str(target), output)
        self.assertIn("MixedCaseParent", [p.name for p in self.root.iterdir()])
        self.assertIn("MyBrainVault", [p.name for p in target.parent.iterdir()])
        config = json.loads((self.settings / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["vault"], str(target))
        existing = self.root / "ExistingMixedCase"
        existing.mkdir()
        self.assertIn(str(existing), self.sb("setup", str(existing)))
        config = json.loads((self.settings / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["vault"], str(existing))

    @unittest.skipUnless(os.name == "nt", "Windows trailing-dot normalization")
    def test_trailing_dot_sibling_cannot_alias_external_junction(self):
        outside = self.root / "outside-dot-fixture"
        outside.mkdir()
        note = outside / "OutsideDot.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n"
                        "tags: [outside-dot-tag]\n---\n[[Home]]\n", encoding="utf-8")
        link = self.vault / "J_out"
        self.directory_link(outside, link)
        raw = "\\\\?\\" + str(self.vault / "J_out.")
        os.mkdir(raw)
        self.addCleanup(os.rmdir, raw)
        with open(raw + "\\OutsideDot.md", "w", encoding="utf-8") as stream:
            stream.write("[[Home]]\n")
        self.addCleanup(os.unlink, raw + "\\OutsideDot.md")
        for command in (("tags",), ("backlinks", "Home"), ("lint",),
                        ("new", "inbox", "OutsideDot", "--dry-run")):
            with self.subTest(command=command):
                output = self.sb(*command, forbidden_reads=[note])
                self.assertNotIn("outside-dot-tag", output)
                if command[0] != "new":
                    self.assertNotIn("OutsideDot.md", output)
        source = self.vault / "00_Inbox/NameProbe.md"
        source.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
                          "[[OutsideDot]]\n", encoding="utf-8")
        self.assertIn("깨진 링크 [[OutsideDot]]",
                      self.sb("lint", str(source), exit_code=1, forbidden_reads=[note]))

    def test_outside_root_below_secret_metadata_ancestor_matches_name_index(self):
        obsidian = self.root / "obsidian"
        (obsidian / ".obsidian").mkdir(parents=True)
        moved = obsidian / "Brain"
        self.vault.rename(moved)
        self.vault = moved
        self.env["SECOND_BRAIN"] = str(moved)
        outside = obsidian / "secret-parent/Shared"
        outside.mkdir(parents=True)
        note = outside / "SharedAllowed.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n"
                        "tags: [shared-allowed]\n---\n[[Home]]\n", encoding="utf-8")
        self.configure(read_outside=[str(outside)])
        self.assertIn("SharedAllowed.md\t볼트 밖", self.sb("backlinks", "Home"))
        self.assertIn("점검(지정한 파일) 1개, 문제 0건", self.sb("lint", str(note)))
        source = moved / "00_Inbox/SharedSource.md"
        source.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n"
                          "[[SharedAllowed]]\n", encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", str(source)))

    def test_render_distinguishes_unapproved_and_excluded_templates(self):
        templates = self.vault / "99_System/Templates"
        moved = self.root / "SharedTemplates"
        templates.rename(moved)
        self.directory_link(moved, templates)
        output = self.sb("render", "Daily", exit_code=1)
        self.assertIn("읽기 허용 범위 밖", output)
        self.assertIn("read_outside", output)
        self.configure(read_outside=[str(moved)])
        self.assertIn("type: daily", self.sb("render", "Daily", "--title", "2026-10-15"))
        self.configure(read_outside=[str(moved)], exclude=[str(moved / "Daily.md")])
        self.assertIn("제외된 템플릿", self.sb("render", "Daily", exit_code=1))

    def test_name_index_accepts_only_readable_linked_files(self):
        # A DirEntry spy exercises linked-file handling without Windows symlink privileges.
        obsidian, _ = self.linked_vault()
        folder = self.vault / "00_Inbox"
        linked = folder / "LinkedFile.md"
        linked.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[Home]]\n", encoding="utf-8")
        source = folder / "LinkedSource.md"
        source.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n[[LinkedFile]]\n", encoding="utf-8")
        bootstrap = '''
            import os, runpy, sys
            original = os.scandir
            class Entry:
                def __init__(self, entry): self.entry = entry
                def __getattr__(self, key): return getattr(self.entry, key)
                def is_symlink(self): return self.name == "LinkedFile.md" or self.entry.is_symlink()
            class Entries:
                def __init__(self, entries): self.entries = entries
                def __iter__(self): return self
                def __next__(self): return Entry(next(self.entries))
                def __enter__(self): self.entries.__enter__(); return self
                def __exit__(self, *args): return self.entries.__exit__(*args)
                def close(self): self.entries.close()
            os.scandir = lambda path: Entries(original(path))
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        self.assertIn("문제 0건", self.sb("lint", str(source), bootstrap=bootstrap))
        self.configure(exclude=["00_Inbox/LinkedFile.md"])
        self.assertIn("깨진 링크 [[LinkedFile]]", self.sb("lint", str(source), exit_code=1,
                      bootstrap=bootstrap, forbidden_reads=[linked]))
        self.configure(exclude=[])
        outside = obsidian / "LinkedOutside.md"
        outside.write_text("[[Home]]\n", encoding="utf-8")
        redirect = '''
            original_realpath = os.path.realpath
            def realpath(path, *args, **kwargs):
                if os.path.basename(path).casefold() == "linkedfile.md":
                    return __OUTSIDE__
                return original_realpath(path, *args, **kwargs)
            os.path.realpath = realpath
        '''.replace("__OUTSIDE__", repr(str(outside)))
        redirected = bootstrap.replace("            sys.argv = sys.argv[1:]",
                                       redirect.strip("\n") + "\n            sys.argv = sys.argv[1:]")
        self.assertIn("깨진 링크 [[LinkedFile]]", self.sb("lint", str(source), exit_code=1,
                      bootstrap=redirected, forbidden_reads=[linked, outside]))

    def test_failed_entry_does_not_skip_later_siblings(self):
        (self.vault / "20_Projects/BadEntry").mkdir()
        survivor = self.project("Survivor")
        survivor.write_text(survivor.read_text(encoding="utf-8").replace(
            "status: active", "status: active\ntags: [survivor-tag]") + "[[Home]]\n",
            encoding="utf-8")
        expected_lint_summary = self.sb("lint").splitlines()[-1]
        bootstrap = '''
            import os, runpy, sys
            original = os.scandir
            class Entry:
                def __init__(self, entry): self.entry = entry
                def __getattr__(self, key): return getattr(self.entry, key)
                def stat(self, *args, **kwargs):
                    if self.name == "BadEntry":
                        print("injected-entry-stat-error")
                        raise FileNotFoundError("entry disappeared")
                    return self.entry.stat(*args, **kwargs)
            class Entries:
                def __init__(self, entries): self.entries = iter(entries)
                def __iter__(self): return self
                def __next__(self): return Entry(next(self.entries))
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def close(self): pass
            def scandir(path):
                with original(path) as scan:
                    entries = sorted(scan, key=lambda entry: (entry.name != "BadEntry", entry.name))
                return Entries(entries)
            os.scandir = scandir
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for command, expected in ((("tags",), "survivor-tag\t1"),
                                  (("backlinks", "Home"), "Survivor.md"),
                                  (("lint",), expected_lint_summary)):
            with self.subTest(command=command):
                output = self.sb(*command, bootstrap=bootstrap)
                self.assertIn("injected-entry-stat-error", output)
                self.assertIn(expected, output)

    def test_template_access_denied_reports_reason(self):
        bootstrap = '''
            import os, runpy, sys
            from pathlib import Path
            original = getattr(Path, "METHOD")
            def blocked(path, *args, **kwargs):
                if path.name == "Daily.md" and path.parent.name == "Templates":
                    print("injected-template-permission-error")
                    raise PermissionError("template denied")
                return original(path, *args, **kwargs)
            setattr(Path, "METHOD", blocked)
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for method in ("read_text", "exists"):
            with self.subTest(method=method):
                output = self.sb("render", "Daily", "--title", "2026-10-15",
                                 exit_code=1 if method == "read_text" else 0,
                                 bootstrap=bootstrap.replace("METHOD", method))
                if method == "read_text":
                    self.assertIn("injected-template-permission-error", output)
                    self.assertIn("템플릿을 읽을 수 없습니다", output)
                else:
                    self.assertNotIn("injected-template-permission-error", output)
                    self.assertIn("type: daily", output)

    def test_unreadable_vault_reports_reason(self):
        bootstrap = '''
            import os, runpy, sys
            original = os.scandir
            def scandir(path):
                if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.environ["SECOND_BRAIN"]):
                    print("injected-vault-permission-error")
                    raise PermissionError("vault denied")
                return original(path)
            os.scandir = scandir
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for command in (("tags",), ("lint",), ("tasks",), ("new", "inbox", "Denied")):
            with self.subTest(command=command):
                output = self.sb(*command, exit_code=1, bootstrap=bootstrap)
                self.assertIn("injected-vault-permission-error", output)
                self.assertIn("볼트 폴더를 읽을 수 없습니다", output)

        stat_bootstrap = '''
            import os, runpy, sys
            from pathlib import Path
            def deny_root(original):
                def checked(path, *args, **kwargs):
                    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.environ["SECOND_BRAIN"]):
                        print("injected-vault-stat-denied")
                        raise PermissionError("vault stat denied")
                    return original(path, *args, **kwargs)
                return checked
            Path.is_dir = deny_root(Path.is_dir)
            Path.exists = deny_root(Path.exists)
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        for command in (("tags",), ("setup", str(self.vault)), ("init", str(self.vault))):
            with self.subTest(stat_command=command):
                output = self.sb(*command, exit_code=1, bootstrap=stat_bootstrap)
                self.assertIn("injected-vault-stat-denied", output)
                self.assertIn("볼트 폴더를 읽을 수 없습니다", output)

    def test_whole_lint_skips_note_disappearing_after_snapshot(self):
        note = self.vault / "00_Inbox/Vanished.md"
        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n", encoding="utf-8")
        bootstrap = '''
            import runpy, sys
            from pathlib import Path
            original = Path.read_text
            def read_text(path, *args, **kwargs):
                if path.name == "Vanished.md":
                    print("injected-disappearing-note")
                    path.unlink(missing_ok=True)
                    raise FileNotFoundError("note vanished")
                return original(path, *args, **kwargs)
            Path.read_text = read_text
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        output = self.sb("lint", bootstrap=bootstrap)
        self.assertIn("injected-disappearing-note", output)
        self.assertIn("읽을 수 없는 파일(건너뜀)", output)
        self.assertIn("문제 0건", output)
        self.assertFalse(note.exists())

        note.write_text("---\ntype: inbox\ncreated: 2026-10-01T09:00\n---\n", encoding="utf-8")
        presence_bootstrap = '''
            import runpy, sys
            from pathlib import Path
            original = Path.is_file
            def is_file(path):
                if path.name == "Vanished.md":
                    print("injected-missing-after-snapshot")
                    path.unlink(missing_ok=True)
                    return False
                return original(path)
            Path.is_file = is_file
            sys.argv = sys.argv[1:]
            runpy.run_path(sys.argv[0], run_name="__main__")
        '''
        output = self.sb("lint", bootstrap=presence_bootstrap)
        self.assertIn("injected-missing-after-snapshot", output)
        self.assertIn("읽을 수 없는 파일(건너뜀)", output)
        self.assertIn("문제 0건", output)
        self.assertFalse(note.exists())

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
                output = self.sb(*command)
                self.assertNotIn("Broken/", output)
                if command[0] == "lint":
                    self.assertIn("문제 0건", output)
                elif command[0] == "backlinks":
                    self.assertIn("백링크 없음", output)
                elif command[0] == "new":
                    self.assertIn("Broken Link Safe", output)
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
        for command in (("tags",), ("lint",), ("backlinks", "Missing")):
            with self.subTest(command=command):
                doomed.mkdir(exist_ok=True)
                output = self.sb(*command, bootstrap=bootstrap)
                self.assertIn("removed-directory-before-stat", output)
                self.assertFalse(doomed.exists())
                if command[0] == "lint":
                    self.assertIn("문제 0건", output)
                elif command[0] == "backlinks":
                    self.assertIn("백링크 없음", output)

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
        outside = self.vault / "99_System/render-payload.md"
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

    def test_index_lists_notes_and_rewrites_only_on_change(self):
        fix = self.vault / "40_Resources/해결 기록/로그인 오류.md"
        fix.write_text("---\ntype: fix\narea: \"[[업무]]\"\ntags: [db]\ncreated: 2026-10-01T09:00\n---\n"
                       "# 로그인 오류\n\n## 현상\n- 로그인 버튼이 `반응` 없음\n", encoding="utf-8")
        self.assertIn("색인 갱신", self.sb("index"))
        index = self.vault / "99_System/색인.md"
        text = index.read_text(encoding="utf-8")
        self.assertIn("## 40_Resources/해결 기록 (1)", text)
        self.assertIn("- 로그인 오류 (`#db`) — 로그인 버튼이 반응 없음", text)
        self.assertNotIn("## 99_System", text)
        self.assertIn("색인 변경 없음", self.sb("index"))
        self.assertEqual(self.sb("index", "--quiet").strip(), "색인: 변경 없음")
        self.assertEqual(index.read_text(encoding="utf-8"), text)
        self.assertIn("문제 0건", self.sb("lint"))

    def test_log_appends_entries_and_refuses_secrets(self):
        out = self.sb("log", "ingest", "자료 A", "--source", "https://example.com/a",
                      "--pages", "노트 A", "[[노트 B]]", "--note", "메모")
        self.assertRegex(out, r"logged: ## \[\d{4}-\d{2}-\d{2}\] ingest \| 자료 A")
        self.sb("log", "lint", "점검")
        log = self.vault / "99_System/브레인 로그.md"
        text = log.read_text(encoding="utf-8")
        self.assertEqual(text.count("# 브레인 로그\n"), 1)
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("## [")]), 2)
        self.assertIn("- 원본: https://example.com/a\n- 고친 노트: [[노트 A]], [[노트 B]]\n- 메모: 메모\n", text)
        self.assertIn("종류는", self.sb("log", "answer", "질문", exit_code=1))
        self.assertIn("비밀정보", self.sb("log", "query", "조사", "--note", "password=hunter22", exit_code=1))
        self.assertEqual(log.read_text(encoding="utf-8"), text)

    def test_new_repo_note_uses_builtin_template_and_feeds_tasks(self):
        self.assertIn("created:", self.sb("new", "repo", "shop-web"))
        note = self.vault / "40_Resources/저장소/shop-web.md"
        text = note.read_text(encoding="utf-8")
        self.assertIn("type: repo", text)
        self.assertNotIn("<%", text)
        for heading in ("## 개요", "## 구조와 흐름", "## 주요 결정", "## 다음 할 일", "## 관련"):
            self.assertIn(heading, text)
        note.write_text(text.replace("## 다음 할 일\n", "## 다음 할 일\n- [ ] 배포 스크립트 정리\n"), encoding="utf-8")
        self.assertIn("[[shop-web]]\t저장소\t배포 스크립트 정리", self.sb("tasks"))
        self.assertNotIn("배포 스크립트 정리", self.sb("tasks", "--older", "1"))

    def test_lint_flags_conflicts_and_accepts_hook_notes(self):
        note = self.vault / "50_Notes/어긋난 주장.md"
        note.write_text("---\ntype: note\ntags: []\ncreated: 2026-10-01T09:00\n---\n# 어긋난 주장\n"
                        "[[업무]]\n> 충돌: 문서는 3회, 코드는 5회\n```\n> 충돌: 코드 안 예시\n```\n", encoding="utf-8")
        out = self.sb("lint", str(note), exit_code=1)
        self.assertIn("남은 충돌 표시: 문서는 3회, 코드는 5회", out)
        self.assertNotIn("코드 안 예시", out)
        journal = self.vault / "10_Daily/Journal/2026-10-16 세션.md"
        journal.parent.mkdir(parents=True)
        journal.write_text("---\ntype: journal\ntags: []\ncreated: 2026-10-16T09:05\n---\n# 2026-10-16 세션\n\n"
                           "← [[2026-10-16]] · 자동 일지\n\n- 09:05 [shop-web] 요약\n", encoding="utf-8")
        dream = self.vault / "00_Inbox/2026-10-16 dream 규칙 제안.md"
        dream.write_text("---\ntype: dream\ntags: []\ncreated: 2026-10-16T09:05\n---\n"
                         "# 2026-10-16 dream 규칙 제안\n\n## 1. 추가 · 전역\n- 규칙: r\n", encoding="utf-8")
        self.assertIn("점검(지정한 파일) 2개, 문제 0건", self.sb("lint", str(journal), str(dream)))

    def test_links_from_system_notes_do_not_rescue_orphans(self):
        lonely = self.vault / "50_Notes/외딴 생각.md"
        lonely.write_text("---\ntype: note\ntags: []\ncreated: 2026-10-01T09:00\n---\n# 외딴 생각\n본문\n", encoding="utf-8")
        (self.vault / "99_System/브레인 로그.md").write_text(
            "---\ntype: system\ntags: []\ncreated: 2026-10-01T09:00\n---\n# 브레인 로그\n\n"
            "## [2026-10-01] ingest | x\n- 고친 노트: [[외딴 생각]]\n", encoding="utf-8")
        self.assertIn("고아 노트", self.sb("lint", str(lonely), exit_code=1))

    def test_new_check_note_uses_builtin_template_and_refuses_same_name(self):
        self.assertIn("created:", self.sb("new", "check", "2026-10-19 점검 결과"))
        note = self.vault / "00_Inbox/2026-10-19 점검 결과.md"
        text = note.read_text(encoding="utf-8")
        self.assertRegex(text, r"^---\ntype: check\ntags: \[\]\ncreated: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}\n---\n")
        self.assertIn("# 2026-10-19 점검 결과\n", text)
        self.assertIn("`/inbox`", text)
        guide = next(line for line in text.splitlines() if line.startswith("> 🤖 세컨드 브레인 점검에서"))
        self.assertIn("`추천대로: A2, A4`", guide)  # 추천 일괄 수락 안내도 같은 인용 한 줄에 있다
        self.assertIn("무인 루틴은 이 파일을 처리하지 않는다.", guide)
        self.assertNotIn("<%", text)
        self.assertLess(text.index("## 결정 대기"), text.index("## 웹으로 채울 빈칸"))
        self.assertLess(text.index("## 웹으로 채울 빈칸"), text.index("## 처리 결과"))
        self.assertIn("이미 있습니다", self.sb("new", "check", "2026-10-19 점검 결과", exit_code=1))
        self.assertIn("created:", self.sb("new", "check", "2026-10-19 점검 결과 2"))
        self.assertIn("점검(지정한 파일) 1개, 문제 0건", self.sb("lint", str(note)))  # 링크가 없어도 고아가 아니다

    def test_links_from_check_and_dream_notes_do_not_rescue_orphans(self):
        lonely = self.vault / "50_Notes/외딴 생각.md"
        lonely.write_text("---\ntype: note\ntags: []\ncreated: 2026-10-01T09:00\n---\n# 외딴 생각\n본문\n", encoding="utf-8")
        check = self.vault / "00_Inbox/2026-10-19 점검 결과.md"
        check.write_text("---\ntype: check\ntags: []\ncreated: 2026-10-19T10:00\n---\n# 2026-10-19 점검 결과\n\n"
                         "## 결정 대기\n- [ ] [A1] [[외딴 생각]] — 고아 노트 · 선택지: 연결 / 보관\n", encoding="utf-8")
        dream = self.vault / "00_Inbox/2026-10-19 dream 규칙 제안.md"
        dream.write_text("---\ntype: dream\ntags: []\ncreated: 2026-10-19T09:05\n---\n# 2026-10-19 dream 규칙 제안\n\n"
                         "## 1. 추가 · 전역\n- 근거: [[외딴 생각]]\n", encoding="utf-8")
        out = self.sb("lint", str(lonely), str(check), str(dream), exit_code=1)
        self.assertIn("외딴 생각.md\t고아 노트", out)
        self.assertIn("점검(지정한 파일) 3개, 문제 1건", out)
        inbox = self.vault / "00_Inbox/메모.md"
        inbox.write_text("---\ntype: inbox\ntags: []\ncreated: 2026-10-19T10:00\n---\n[[외딴 생각]]\n", encoding="utf-8")
        self.assertIn("문제 0건", self.sb("lint", str(lonely)))  # 다른 노트의 링크는 그대로 연결로 친다

    def test_index_counts_only_pending_decisions_of_check_notes(self):
        (self.vault / "00_Inbox/2026-10-19 점검 결과.md").write_text(
            "---\ntype: check\ntags: []\ncreated: 2026-10-19T10:00\n---\n# 2026-10-19 점검 결과\n\n"
            "> 결정 대기 2항목(지적 3건을 묶음)\n\n## 결정 대기\n\n### A. 상태\n"
            "- [ ] [A1] [[x]] — 문제\n- [x] [A2] [[y]] — 문제 → 결정: 닫기 (2026-10-19)\n- [ ] [A3] [[z]] — 문제\n\n"
            "## 웹으로 채울 빈칸\n- 조사 항목\n\n## 처리 결과\n- [ ] 이 줄은 세지 않는다\n", encoding="utf-8")
        self.sb("index")
        text = (self.vault / "99_System/색인.md").read_text(encoding="utf-8")
        self.assertIn("- 2026-10-19 점검 결과 — 결정 대기 2건\n", text)

    def test_index_pending_decisions_skip_deferred_items_like_session_reminder(self):
        body = ("---\ntype: check\ntags: []\ncreated: 2026-10-19T10:00\n---\n# 2026-10-19 점검 결과\n\n"
                "## 결정 대기\n\n### A. 상태\n"
                "- [ ] [A1] [[x]] — 문제 · 추천: 닫기\n"
                "- [ ] [A2] [[y]] — 문제 → 보류: 자료를 기다림 (2026-10-19)\n\n"
                "### B. 분류\n"
                "- [ ] [B1] [[z]] — 문제 · 추천: 업무로\n"
                "- [x] [B2] [[w]] — 문제 → 결정: 닫기 (2026-10-19)\n"
                "- [ ] [B3] [[v]] — 문제 → 보류: 다음 점검에서 (2026-10-19)\n\n"
                "## 처리 결과\n- [ ] 이 줄은 세지 않는다\n")
        (self.vault / "00_Inbox/2026-10-19 점검 결과.md").write_text(body, encoding="utf-8")
        (self.vault / "00_Inbox/2026-10-20 점검 결과.md").write_bytes(
            body.replace("2026-10-19 점검", "2026-10-20 점검").replace("\n", "\r\n").encode("utf-8"))
        self.sb("index")
        text = (self.vault / "99_System/색인.md").read_text(encoding="utf-8")
        self.assertIn("- 2026-10-19 점검 결과 — 결정 대기 2건\n", text)  # ### 묶음을 지나도 절 안이고, → 보류는 뺀다
        self.assertIn("- 2026-10-20 점검 결과 — 결정 대기 2건\n", text)  # CRLF 파일도 같다
        probe = ("import runpy, sys\n"
                 "count = runpy.run_path(sys.argv[1])['pending_decisions']\n"
                 "print(count(sys.argv[2].replace('\\n', '\\r\\n')), count(sys.argv[2]))\n")
        result = subprocess.run([sys.executable, "-c", probe, str(SCRIPT), body], capture_output=True,
                                env=self.env, cwd=self.root)
        self.assertEqual(result.stdout.decode("utf-8").split(), ["2", "2"], result.stderr.decode("utf-8", "replace"))

    def test_today_shows_journal_path(self):
        out = self.sb("today", "--date", "2026-10-16")
        self.assertRegex(out, r"journal: .*2026-10-16 세션\.md  exists=False")


if __name__ == "__main__":
    unittest.main()
