"""세컨드 브레인 설치 — second-brain 스킬 복사, Claude Code 쪽 hook·전용 스킬 복사와 settings.json·전역 CLAUDE.md 고치기.
Python 3.9+, 표준 라이브러리만.

  python tools/claude_setup.py install [--python CMD] [--claude-dir DIR] [--home DIR] [--codex] [--antigravity] [--all]
      second-brain 스킬 복사(Claude Code, 옵션으로 Codex·Antigravity), hook·전용 스킬 복사,
      settings.json 에 hook 등록, CLAUDE.md 에 brain 구역 추가
  python tools/claude_setup.py remove [--claude-dir DIR] [--home DIR]
      settings.json 에서 brain hook 등록만 뺀다(파일·CLAUDE.md 는 그대로)

여러 번 실행해도 결과가 같다(멱등). 고칠 것이 있을 때만 원본을 `<파일>.bak-<날짜시각>` 으로 남기고 쓴다.
대상 폴더는 기본 ~/.claude 다. install.ps1·install.sh 가 --claude-dir·--home 을 넘겨 부른다.
Codex(~/.agents/skills)·Antigravity(~/.gemini/config/skills)에는 second-brain 스킬만 복사한다.
hook·/inbox·/init-project·settings.json·CLAUDE.md 는 Claude Code 전용이다.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys

KIT = Path(__file__).resolve().parents[1]
HOOK_FILES = ("brain_common.py", "brain-journal.py", "brain-dream.py", "brain-lint-reminder.py")
SKILLS = ("inbox", "init-project")
SKILL = "second-brain"
SKIP_NAMES = ("local.md", "config.json")  # 개인 설정은 ~/.second-brain 에 둔다. 키트 안에 실수로 있어도 복사하지 않는다
# 이벤트마다 hook 그룹 하나. 그룹 안 순서대로 돈다(안내 줄을 먼저 내고, 오래 걸리는 dream 은 떼어 낸 프로세스로).
EVENTS = {"SessionStart": ("brain-lint-reminder.py", "brain-dream.py"), "SessionEnd": ("brain-journal.py",)}
BLOCK_START, BLOCK_END = "<!-- brain:start -->", "<!-- brain:end -->"


def is_brain(hook):
    command = hook.get("command", "") if isinstance(hook, dict) else ""
    return any(name in command for names in EVENTS.values() for name in names)


def has_brain(group):
    inner = group.get("hooks") if isinstance(group, dict) else None
    return isinstance(inner, list) and any(is_brain(h) for h in inner)


def canonical(python, names):
    return {"hooks": [{"type": "command", "command": f'{python} "$HOME/.claude/hooks/{name}"', "timeout": 10}
                      for name in names]}


def strip_brain(hooks):
    """brain hook 만 뺀다. 그 때문에 빈 그룹·빈 이벤트가 되면 그것도 뺀다(원래 비어 있던 것은 둔다)."""
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if not has_brain(group):
                kept.append(group)
                continue
            rest = [h for h in group["hooks"] if not is_brain(h)]
            if rest:
                kept.append(dict(group, hooks=rest))
        if kept or not groups:
            hooks[event] = kept
        else:
            del hooks[event]


def backup(path):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target, n = path.with_name(f"{path.name}.bak-{stamp}"), 2
    while target.exists():
        target, n = path.with_name(f"{path.name}.bak-{stamp}-{n}"), n + 1
    shutil.copy2(path, target)
    return target


def write_atomic(path, data):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save(path, before, data, label):
    if before is not None and data == before:
        print(f"{label}: 변경 없음 ({path})")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = backup(path) if path.exists() else None
    write_atomic(path, data)
    print(f"{label}: {'갱신' if saved else '만듦'} ({path})" + (f" — 백업 {saved.name}" if saved else ""))


def load_settings(path):
    if not path.exists():
        return None, {}
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as e:
        sys.exit(f"settings.json 을 읽지 못해 고치지 않았습니다({e}): {path}\n"
                 "JSON 형식을 고친 뒤 다시 실행하세요.")
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        sys.exit(f"settings.json 모양이 예상과 달라 고치지 않았습니다(최상위·hooks 가 객체가 아님): {path}")
    odd = [event for event, groups in data.get("hooks", {}).items() if not isinstance(groups, list)]
    if odd:  # 이벤트 값은 hook 그룹 목록이어야 한다. 아니면 어디에 넣을지 알 수 없으니 손대지 않는다.
        sys.exit(f"settings.json 모양이 예상과 달라 고치지 않았습니다(hooks.{odd[0]} 이 목록이 아님): {path}")
    return raw, data


def dump(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def configure_settings(claude, python):
    path = claude / "settings.json"
    raw, data = load_settings(path)
    hooks = data.setdefault("hooks", {})
    wanted = {event: canonical(python, names) for event, names in EVENTS.items()}
    present = {event: [g for g in hooks.get(event, []) if has_brain(g)] if isinstance(hooks.get(event), list) else []
               for event in EVENTS}
    others = [g for event, groups in hooks.items() if event not in EVENTS and isinstance(groups, list)
              for g in groups if has_brain(g)]
    if not others and all(present[event] == [wanted[event]] for event in EVENTS):  # 이미 그대로면 순서도 건드리지 않는다
        print(f"settings.json: 변경 없음 ({path})")
        return
    strip_brain(hooks)
    for event, group in wanted.items():
        hooks.setdefault(event, []).append(group)
    save(path, raw, dump(data), "settings.json")


def configure_claude_md(claude):
    path = claude / "CLAUDE.md"
    block = (KIT / "tools" / "brain-claude-md.md").read_text(encoding="utf-8")
    raw = path.read_bytes() if path.exists() else None
    text = raw.decode("utf-8-sig", errors="replace") if raw is not None else ""
    if BLOCK_START in text:
        print(f"CLAUDE.md: 변경 없음 — brain 구역이 이미 있음 ({path})")
        return
    newline = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith("\n"):
        text += newline
    text += (newline if text.strip() else "") + block.replace("\n", newline)
    head = b"\xef\xbb\xbf" if raw and raw.startswith(b"\xef\xbb\xbf") else b""  # BOM 이 있던 파일은 그대로
    save(path, raw, head + text.encode("utf-8"), "CLAUDE.md")


def copy_files(claude):
    hooks = claude / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for name in HOOK_FILES:
        shutil.copyfile(KIT / "hooks" / name, hooks / name)
    print(f"Installed: {hooks} ({', '.join(HOOK_FILES)})")
    for skill in SKILLS:
        dst = claude / "skills" / skill
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KIT / "skills" / skill / "SKILL.md", dst / "SKILL.md")
        print(f"Installed: {dst}")


def skill_targets(claude, home, codex=False, antigravity=False):
    targets = [claude / "skills" / SKILL]
    if codex:  # Codex 사용자 스킬 폴더
        targets.append(home / ".agents" / "skills" / SKILL)
    if antigravity:  # Antigravity 사용자 스킬 폴더
        targets.append(home / ".gemini" / "config" / "skills" / SKILL)
    return targets


def copy_skill(dst):
    src = KIT / "skills" / SKILL
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if not path.is_file() or path.name in SKIP_NAMES or "__pycache__" in rel.parts:
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst / rel)
    print(f"Installed: {dst}")


def main():
    ap = argparse.ArgumentParser(description="세컨드 브레인 설치(second-brain 스킬, Claude Code hook·전용 스킬·settings.json·CLAUDE.md)")
    ap.add_argument("action", choices=("install", "remove"))
    ap.add_argument("--python", default="python", help='hook 을 돌릴 명령(기본 python, macOS·Linux 는 보통 python3)')
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"),
                    help="Claude Code 설정 폴더(기본 ~/.claude). 설치 스크립트는 $HOME/.claude 를 넘긴다")
    ap.add_argument("--home", default=str(Path.home()), help="Codex·Antigravity 스킬 폴더의 기준 홈 폴더(기본 ~)")
    ap.add_argument("--codex", action="store_true", help="second-brain 스킬을 ~/.agents/skills 에도 복사")
    ap.add_argument("--antigravity", action="store_true", help="second-brain 스킬을 ~/.gemini/config/skills 에도 복사")
    ap.add_argument("--all", action="store_true", help="--codex --antigravity 와 같다(Claude Code 는 늘 설치)")
    a = ap.parse_args()
    claude, home = Path(a.claude_dir), Path(a.home)
    if a.action == "install":
        for dst in skill_targets(claude, home, a.codex or a.all, a.antigravity or a.all):
            copy_skill(dst)
        copy_files(claude)
        configure_settings(claude, a.python)
        configure_claude_md(claude)
        try:
            same = claude.resolve() == (Path.home() / ".claude").resolve()
        except OSError:
            same = False
        if not same:  # 등록한 명령은 어느 PC 에서나 통하도록 $HOME/.claude/hooks 를 가리킨다
            print(f'주의: settings.json 의 hook 명령은 "$HOME/.claude/hooks/..." 를 가리키는데 hook 파일은 {claude / "hooks"} 에 '
                  "복사했습니다. Claude Code 가 이 폴더를 설정 폴더로 쓰면(CLAUDE_CONFIG_DIR) settings.json 의 경로를 그 폴더로 직접 고치세요.")
        return
    path = claude / "settings.json"
    raw, data = load_settings(path)
    before = dump(data)
    strip_brain(data.get("hooks", {}))
    if raw is None or dump(data) == before:
        print(f"settings.json: 변경 없음 — brain hook 등록 없음 ({path})")
    else:
        save(path, raw, dump(data), "settings.json")
    print("남은 것(필요하면 직접 지운다): "
          f"{claude / 'hooks'}의 brain_common.py·brain-*.py·brain-*.log, {claude / 'skills'}의 inbox·init-project, "
          f"{home / '.second-brain' / 'state'}(대기열·상태), "
          f"{claude / 'CLAUDE.md'}의 {BLOCK_START} ~ {BLOCK_END} 구역(승인한 규칙이 들어 있어 자동으로 지우지 않는다)")
    copies = [str(p) for p in skill_targets(claude, home, True, True) if p.is_dir()]
    if copies:  # remove 는 hook 등록만 뺀다. 스킬 사본은 Codex·Antigravity 것도 직접 지운다
        print(f"second-brain 스킬 사본(스킬까지 모두 지울 때): {', '.join(copies)}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
