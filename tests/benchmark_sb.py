"""Isolated CLI benchmark: python tests/benchmark_sb.py > benchmark.json.

Each version uses the same temporary vault, settings, and command arguments.
No existing vault/settings are accessed. Results include one warmup and medians.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[1]
SKILL = Path("skills/second-brain")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, stderr=subprocess.PIPE)


def redact_output(value, temporary):
    pattern = r"[\\/]".join(re.escape(part) for part in re.split(r"[\\/]", str(temporary)))
    return re.sub(pattern, "<tmp>", value, flags=re.IGNORECASE)


def validate_refs(parser, refs):
    for ref in refs:
        if ref == "worktree":
            continue
        try:
            git("rev-parse", "--verify", f"{ref}^{{commit}}")
            git("cat-file", "-e", f"{ref}:{SKILL.as_posix()}/scripts/sb.py")
        except (subprocess.CalledProcessError, OSError):
            parser.error(f"Cannot benchmark ref {ref!r}; fetch it or choose existing refs with --refs REF worktree")


def snapshot(ref, destination):
    script = destination / SKILL / "scripts/sb.py"
    script.parent.mkdir(parents=True)
    if ref == "worktree":
        script.write_bytes((REPO / SKILL / "scripts/sb.py").read_bytes())
        shutil.copytree(REPO / SKILL / "assets", destination / SKILL / "assets")
        revision = "worktree@" + git("rev-parse", "HEAD").decode().strip()
    else:
        revision = git("rev-parse", ref).decode().strip()
        script.write_bytes(git("show", f"{ref}:{SKILL.as_posix()}/scripts/sb.py"))
        files = git("ls-tree", "-rz", "--name-only", ref,
                    (SKILL / "assets").as_posix()).decode("utf-8").split("\0")
        for name in files:
            if not name:
                continue
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git("show", f"{ref}:{name}"))
    return script, revision


def run(script, args, fixture, env, capture=False):
    start = time.perf_counter()
    try:
        result = subprocess.run([sys.executable, str(script), *args], cwd=fixture,
                                env=env, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=180)
        record = {"seconds": time.perf_counter() - start,
                  "returncode": result.returncode, "timeout": False}
        if capture:
            record["stdout"] = redact_output(result.stdout.decode("utf-8", errors="replace"), fixture)
        if result.stderr:
            record["stderr"] = redact_output(result.stderr.decode("utf-8", errors="replace"), fixture)
        return record
    except subprocess.TimeoutExpired:
        return {"seconds": time.perf_counter() - start,
                "returncode": None, "timeout": True}


def verify(command, warmup, vault):
    output = warmup.get("stdout", "")
    if command.startswith("lint_"):
        match = re.search(r"점검\(.+?\) (\d+)개, 문제 (\d+)건", output)
        checked = int(match[1]) if match else None
        passed = bool(match and int(match[2]) == 0 and
                      (checked >= 2000 if command == "lint_all" else checked == 1))
        return {"passed": passed, "checked": checked}
    if command == "tags":
        return {"passed": "bench\t2000" in output.splitlines()}
    if command == "backlinks":
        return {"passed": "Bench1999.md" in output}
    return {"passed": "[dry-run]" in output and
            not (vault / "00_Inbox/Benchmark Preview.md").exists()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", nargs="+", default=["origin/main", "worktree"])
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    validate_refs(parser, args.refs)
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "platform": platform.platform(),
              "repeat": args.repeat, "warmups": 1, "versions": []}
    with tempfile.TemporaryDirectory(prefix="sb-benchmark-") as temporary:
        root = Path(temporary)
        vault, settings = root / "vault", root / "settings"
        env = dict(os.environ, SECOND_BRAIN_HOME=str(settings), SECOND_BRAIN=str(vault),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        versions = [(ref, *snapshot(ref, root / f"version-{i}"))
                    for i, ref in enumerate(args.refs)]
        initialized = run(versions[0][1], ["init", str(vault)], root, env)
        if initialized["returncode"] != 0:
            raise RuntimeError(f"Fixture initialization failed: {initialized}")
        starter_count = len(list(vault.rglob("*.md")))
        folder = vault / "00_Inbox" / "Bench"
        folder.mkdir()
        for index in range(2000):
            title = f"Bench{index:04d}"
            (folder / f"{title}.md").write_text(
                f"---\ntype: inbox\ncreated: 2026-10-15T09:00\ntags: [bench]\n---\n"
                f"# {title}\n[[Bench{(index + 1) % 2000:04d}]]\n", encoding="utf-8")
        for index in range(1000):
            (folder / f"Attachment{index:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        report["fixture"] = {"generated_markdown": 2000, "starter_markdown": starter_count,
                             "total_markdown": 2000 + starter_count, "png": 1000}
        config_path = settings / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        commands = {"lint_all": ["lint"],
                    "lint_one": ["lint", str(folder / "Bench0000.md")],
                    "tags": ["tags"], "backlinks": ["backlinks", "Bench0000"],
                    "new_dry_run": ["new", "inbox", "Benchmark Preview", "--dry-run"]}
        for ref, script, revision in versions:
            version = {"ref": ref, "revision": revision,
                       "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                       "results": []}
            report["versions"].append(version)
            for exclude_count in (0, 5):
                config["exclude"] = [f"Excluded{i}" for i in range(exclude_count)]
                config_path.write_text(json.dumps(config), encoding="utf-8")
                for command, arguments in commands.items():
                    print(f"{ref} exclude={exclude_count} {command}", file=sys.stderr, flush=True)
                    warmup = run(script, arguments, root, env, capture=True)
                    verification = verify(command, warmup, vault)
                    warmup["stdout"] = warmup.get("stdout", "")[:1000]
                    samples = [run(script, arguments, root, env) for _ in range(args.repeat)]
                    version["results"].append({"exclude_count": exclude_count,
                        "command": command, "warmup": warmup, "samples": samples,
                        "verification": verification,
                        "median_seconds": statistics.median(s["seconds"] for s in samples)})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(not r["verification"]["passed"] for v in report["versions"] for r in v["results"]):
        return 1
    if any(s["returncode"] != 0 for v in report["versions"] for r in v["results"]
           for s in [r["warmup"], *r["samples"]]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
