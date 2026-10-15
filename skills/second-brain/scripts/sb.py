#!/usr/bin/env python3
"""세컨드 브레인(Obsidian PARA 볼트) 보조 도구 — Python 3.9+, 표준 라이브러리만 사용.

날짜·템플릿 치환·점검처럼 틀리기 쉬운 기계적 작업만 맡는다. 노트 내용 판단은 하지 않는다.

  python sb.py init <새 볼트 폴더>          스타터 볼트를 만들고 그 경로를 설정에 저장
  python sb.py setup <기존 볼트 폴더>        이미 있는 볼트 경로를 설정에 저장
  python sb.py where                         지금 쓰는 볼트·설정 경로
  python sb.py today [--date YYYY-MM-DD]     오늘 날짜·ISO 주차·일일/주간 노트 경로와 존재 여부
  python sb.py render <템플릿> [--title T]    Templater 구문을 실제 값으로 바꾼 본문 출력
  python sb.py new <종류> [제목] [--date D] [--dry-run]
                                             템플릿으로 새 노트 생성(같은 이름이 있으면 거부)
                                             종류: daily weekly project fix note inbox resource
  python sb.py tasks [--older N]             일일 노트·진행 중 프로젝트의 미완료 할 일
  python sb.py stale [--days 14]             N일 넘게 수정되지 않은 active 프로젝트
  python sb.py tags                          쓰고 있는 태그와 개수
  python sb.py backlinks <노트 이름>          그 노트를 [[링크]]하는 파일 목록
  python sb.py lint [파일...]                 형식·링크·잔여 Templater·비밀정보 점검(기본: 볼트 전체)

볼트 위치: 환경변수 SECOND_BRAIN > ~/.second-brain/config.json의 "vault" 순서로 찾는다.
config.json 선택 키: folders(종류별 폴더), exclude(열지 않을 폴더, 볼트 또는 Obsidian 루트 기준),
  read_outside(backlinks·lint가 읽어도 되는 볼트 밖 폴더, 볼트 기준 "../폴더"), today_sources, utc_offset.
개인 설정(config.json, local.md)은 ~/.second-brain/에 두어 Claude Code·Codex 설치가 함께 쓴다
(환경변수 SECOND_BRAIN_HOME으로 위치를 바꿀 수 있다).
"""
import argparse
import datetime as dt
import functools
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


_REAL_PATHS = {}


def real_path(path, known=None):
    key = _norm(path)
    if key not in _REAL_PATHS:
        try:
            _REAL_PATHS[key] = os.path.normcase(known) if known is not None else _norm(os.path.realpath(key))
        except (OSError, RuntimeError):
            _REAL_PATHS[key] = None
    return _REAL_PATHS[key]


SKILL_DIR = Path(real_path(__file__) or os.path.abspath(__file__)).parent.parent
STARTER = SKILL_DIR / "assets" / "starter-vault"
HOME_DIR = Path(os.environ.get("SECOND_BRAIN_HOME") or Path.home() / ".second-brain").expanduser()
CONFIG = HOME_DIR / "config.json"
LOCAL = HOME_DIR / "local.md"
KST = dt.timezone(dt.timedelta(hours=9))  # 기본 Asia/Seoul. config.json의 utc_offset으로 바꿀 수 있다.

KINDS = {  # 종류: (템플릿, 기본 폴더) — config.json "folders"로 폴더를 바꿀 수 있다
    "daily": ("Daily", "10_Daily"),
    "weekly": ("Weekly", "10_Daily/Weekly"),
    "project": ("Project", "20_Projects"),
    "fix": ("Fix", "40_Resources/해결 기록"),
    "resource": ("Resource", "40_Resources/참고 자료"),
    "note": ("Note", "50_Notes"),
    "inbox": ("Inbox", "00_Inbox"),
}
# 볼트에 템플릿 파일이 없을 때만 쓰는 기본 구조
BUILTIN = {
    "Resource": '---\ntype: resource\ntags: []\ncreated: <% tp.date.now("YYYY-MM-DDTHH:mm") %>\n---\n'
                "# <% tp.file.title %>\n\n## 요약\n- \n\n## 원본\n- \n",
}
FOLDERS = ["00_Inbox", "10_Daily/Weekly", "20_Projects", "30_Areas", "40_Resources/해결 기록",
           "40_Resources/참고 자료", "50_Notes", "90_Archive", "99_System/Templates", "99_System/Routines"]
TYPES = {"inbox", "daily", "weekly", "project", "area", "resource", "fix", "note", "system"}
SKIP_DIRS = {".obsidian", ".trash", ".git", ".tmp.driveupload", ".tmp.drivedownload", "node_modules"}
SECRET_NAME = re.compile(r"(?i)토큰|비번|비밀번호|(?<![a-z])(?:password|passwd|token|secret|credential)s?(?![a-z])"
                         r"|\.env$|\.pem$|\.key$")
SECRET_WORD = re.compile(r"(?i)토큰|비번|비밀번호|(?<![a-z])(?:password|passwd|token|secret|credential)s?(?![a-z])")
BAD_NAME = re.compile(r'[/\\:*?"<>|]')
BAD_TITLE = re.compile(r'[/\\:*?"<>|#^\[\]]')  # 파일 이름 금지 문자 + Obsidian 링크를 깨는 # ^ [ ]
SECRET = re.compile(
    r"(?i)(password|passwd|pwd|비밀번호|api[_-]?key|secret|token)\s*[:=]\s*\S{4,}"
    r"|glpat-[0-9A-Za-z_\-]{10,}|gh[pousr]_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z_\-]{20,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8-sig"))  # 메모장이 붙이는 BOM 허용
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        sys.exit(f"설정 파일 형식 오류: {CONFIG} ({e})")
    except UnicodeDecodeError:
        sys.exit(f"설정 파일을 UTF-8로 다시 저장하세요(PowerShell Out-File·Set-Content 기본값은 UTF-8이 아님): {CONFIG}")


CFG = load_config()
if "utc_offset" in CFG:
    KST = dt.timezone(dt.timedelta(hours=float(CFG["utc_offset"])))


def save_config(**kw):
    cfg = load_config()
    cfg.update(kw)
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


VAULT_FOR_EXCLUDE = None  # exclude 해석 기준(볼트). resolve_vault가 정한다.


def resolve_vault():
    global VAULT_FOR_EXCLUDE
    raw = os.environ.get("SECOND_BRAIN") or CFG.get("vault")
    if not raw:
        me = Path(os.path.abspath(__file__))
        sys.exit("볼트 경로가 설정되지 않았습니다.\n"
                 f'  새로 만들기: python "{me}" init <폴더>\n'
                 f'  기존 볼트:   python "{me}" setup <폴더>   (또는 환경변수 SECOND_BRAIN)')
    vault = Path(os.path.abspath(Path(raw).expanduser()))
    actual = real_path(vault)
    if actual is None:
        sys.exit(f"볼트 실제 경로를 확인할 수 없습니다(읽지 않음): {vault}")
    try:
        exists = vault.is_dir()
    except OSError:
        exists = False
    if not exists:
        sys.exit(f"볼트 폴더가 없습니다: {vault}")
    VAULT_FOR_EXCLUDE = vault
    if excluded(vault, obsidian_root(vault), actual):
        sys.exit(f"제외된 볼트 폴더입니다(읽지 않음): {vault}")
    return vault


@functools.lru_cache(maxsize=None)
def obsidian_root(vault):
    """[[경로/링크]]의 기준인 Obsidian 볼트 루트: .obsidian이 있는 가장 가까운 상위 폴더."""
    for p in [vault, *vault.parents]:
        try:
            if (p / ".obsidian").is_dir():
                return p
        except OSError:
            continue
    return vault


def under(path, root):
    return root is not None and (path == root or path.startswith(root.rstrip(os.sep) + os.sep))


def relative_path(path, root):
    try:
        return Path(os.path.relpath(path, root))
    except ValueError:  # 서로 다른 Windows 드라이브
        return path


@functools.lru_cache(maxsize=None)
def read_roots(vault):
    return (vault, *(Path(os.path.abspath(vault / x)) for x in CFG.get("read_outside", [])))


@functools.lru_cache(maxsize=None)
def access_rules(vault):
    obsidian = obsidian_root(vault)
    roots = tuple((_norm(p), real_path(p)) for p in read_roots(vault))
    boundaries = set()
    for base in {vault, obsidian}:
        for item in CFG.get("exclude", []):
            path = base / item
            boundaries.add(_norm(path))
            actual = real_path(path)
            if actual is not None:
                boundaries.add(actual)
    return roots, tuple(boundaries), (_norm(obsidian), real_path(obsidian))


def bad_parts(relative):
    parts = relative.strip(os.sep).split(os.sep) if relative else []
    return (any(p in SKIP_DIRS or SECRET_WORD.search(p) for p in parts)
            or bool(parts and SECRET_NAME.search(parts[-1])))


def excluded(path, root, actual=None, names_only=False):
    vault = VAULT_FOR_EXCLUDE or root
    actual = real_path(path) if actual is None else actual
    if actual is None:
        return True
    roots, boundaries, metadata = access_rules(vault)
    logical = _norm(path)
    if any(under(candidate, boundary) for candidate in (logical, actual) for boundary in boundaries):
        return True
    for index, candidate in enumerate((logical, actual)):
        primary = roots[0][index]
        if under(candidate, primary):
            if bad_parts(candidate[len(primary):]):
                return True
            continue  # 볼트 이름과 볼트 위쪽 폴더 이름은 비밀 이름 검사 대상이 아니다.
        for pair in roots[1:]:
            anchor = pair[index]
            if under(candidate, anchor):
                if bad_parts(os.path.basename(anchor) + candidate[len(anchor):]):
                    return True
        if names_only and under(candidate, metadata[index]):
            if bad_parts(candidate[len(metadata[index]):]):
                return True
    return False


def readable(path, root, actual=None, names_only=False):
    actual = real_path(path) if actual is None else actual
    if actual is None:
        return False
    roots, _, metadata = access_rules(VAULT_FOR_EXCLUDE or root)
    allowed = any(under(actual, pair[1]) for pair in roots)
    if names_only:
        allowed = allowed or under(actual, metadata[1])
    return allowed and not excluded(path, root, actual, names_only)


def walk_files(base, root, recursive=True, names_only=False, suffix=None):
    actual_base = real_path(base)
    if actual_base is None or not readable(base, root, actual_base, names_only):
        return
    pending = [(base, actual_base)]
    while pending:
        folder, actual_folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        directory = entry.is_dir(follow_symlinks=False)
                        if not directory and suffix:
                            name = entry.name.casefold()
                            if name == suffix or not name.endswith(suffix):
                                continue
                        info = entry.stat(follow_symlinks=False)
                        linked = entry.is_symlink() or (os.name == "nt" and
                                 info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT)
                        if linked and (directory or names_only):
                            continue
                        if not directory and not entry.is_file():
                            continue
                    except OSError:
                        continue
                    path = Path(entry.path)
                    # 비연결 항목은 검사한 부모의 실제 경로를 재사용한다.
                    actual = real_path(path, None if linked else os.path.join(actual_folder, entry.name))
                    if actual is None or not readable(path, root, actual, names_only):
                        continue
                    if directory:
                        if recursive:
                            pending.append((path, actual))
                    else:
                        yield path
        except OSError:
            continue


def note_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def now():
    return dt.datetime.now(KST)


def iso_week(d):
    y, w, _ = d.isocalendar()
    monday = d - dt.timedelta(days=d.weekday())
    return f"{y}-W{w:02d}", monday, monday + dt.timedelta(days=6)


def fmt(moment_fmt, value):
    """moment.js 형식 중 템플릿이 쓰는 토큰만 변환."""
    out = moment_fmt
    for tok, py in (("YYYY", "%Y"), ("MM", "%m"), ("DD", "%d"), ("HH", "%H"), ("mm", "%M")):
        out = out.replace(tok, py)
    return value.strftime(out)


def parse_week(title):
    m = re.fullmatch(r"(\d{4})-W(\d{2})", title)
    if not m:
        sys.exit(f"주간 노트 제목은 YYYY-Www 형식이어야 합니다: {title}")
    return dt.date.fromisocalendar(int(m[1]), int(m[2]), 1)


def render(vault, template_name, title):
    if any(part in template_name for part in ("/", "\\", "..")):
        sys.exit("템플릿 이름에 경로 구분자나 '..'를 쓸 수 없습니다.")
    path = vault / "99_System" / "Templates" / f"{template_name}.md"
    if path.exists():
        if not readable(path, obsidian_root(vault)):
            sys.exit(f"제외된 템플릿 경로입니다(읽지 않음): {path}")
        text = note_text(path)
        if text is None:
            sys.exit(f"템플릿을 읽을 수 없습니다: {path}")
    elif template_name in BUILTIN:
        text = BUILTIN[template_name]
    else:
        sys.exit(f"템플릿이 없습니다: {path}")
    current = now()

    def title_date():
        try:
            return dt.date.fromisoformat(title)
        except ValueError:
            sys.exit(f"이 템플릿은 제목이 YYYY-MM-DD여야 합니다: {title}")

    def repl(m):
        expr = m[1].strip()
        if expr == "tp.file.title":
            return title
        g = re.fullmatch(r'tp\.date\.now\("([^"]+)",\s*(-?\d+),\s*tp\.file\.title,\s*"YYYY-MM-DD"\)', expr)
        if g:
            return fmt(g[1], title_date() + dt.timedelta(days=int(g[2])))
        g = re.fullmatch(r'tp\.date\.now\("([^"]+)"(?:,\s*(-?\d+))?\)', expr)
        if g:
            return fmt(g[1], current + dt.timedelta(days=int(g[2] or 0)))
        g = re.fullmatch(r'moment\(tp\.file\.title,\s*"GGGG-\[W\]WW",\s*true\)\.(startOf|endOf)\("isoWeek"\)\.format\("([^"]+)"\)', expr)
        if g:
            monday = parse_week(title)
            return fmt(g[2], monday if g[1] == "startOf" else monday + dt.timedelta(days=6))
        sys.exit(f"처리할 수 없는 Templater 구문: {expr} — 템플릿이 바뀌었으면 sb.py를 갱신하세요.")

    out = re.sub(r"<%[*_-]?(.*?)[_-]?%>", repl, text)
    if "<%" in out:
        sys.exit("Templater 구문이 남았습니다. 파일을 쓰지 마세요.")
    return out


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    fm, key = {}, None
    for line in m[1].splitlines():
        kv = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        item = re.match(r"^\s+-\s+(.+)$", line)
        if kv:
            key = kv[1]
            fm[key] = unquote(kv[2])
        elif item and key:  # YAML 목록(tags 등)
            prev = fm.get(key)
            fm[key] = (prev if isinstance(prev, list) else []) + [unquote(item[1])]
    return fm


def notes(vault):
    yield from walk_files(vault, obsidian_root(vault), suffix=".md")


def strip_code(text):
    return re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", text, flags=re.S))


LINK = re.compile(r"!?\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")


def links_of(text):
    return [m.strip() for m in LINK.findall(strip_code(text))]


def link_index(root):
    """Obsidian 방식: 파일 이름(확장자 제외) 또는 볼트 루트 기준 경로로 해석."""
    names, paths = set(), set()
    for base in dict.fromkeys((root, *read_roots(VAULT_FOR_EXCLUDE or root))):
        for p in walk_files(base, root, names_only=True):
            rel = relative_path(p, root)
            stem = normalized_link(rel.as_posix())
            names.add(Path(stem).name)
            paths.add(stem)
    return names, paths


def resolves(target, names, paths):
    t = normalized_link(target)
    return t in names or t in paths or any(x.endswith("/" + t) for x in paths)


def folder_of(vault, kind):
    folder = Path(os.path.abspath(vault / CFG.get("folders", {}).get(kind, KINDS[kind][1])))
    actual = real_path(folder)
    if actual is None:
        sys.exit(f"노트 폴더의 실제 경로를 확인할 수 없습니다(읽지 않음): {folder}")
    if not under(actual, real_path(vault)):
        sys.exit(f"노트 폴더는 볼트 안이어야 합니다: {kind} → {folder}")
    if excluded(folder, obsidian_root(vault), actual):
        sys.exit(f"제외된 노트 폴더입니다: {kind} → {folder}")
    return folder


def warn_env():
    if os.environ.get("SECOND_BRAIN"):
        print(f"주의: 환경변수 SECOND_BRAIN({os.environ['SECOND_BRAIN']})이 설정되어 있어 그쪽 볼트가 계속 쓰입니다.")


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        sys.exit(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {text}")


def cmd_init(a):
    if not STARTER.is_dir():
        sys.exit(f"스타터 볼트가 없습니다: {STARTER}")
    actual = real_path(Path(a.folder).expanduser())
    if actual is None:
        sys.exit(f"볼트 실제 경로를 확인할 수 없습니다: {a.folder}")
    target = Path(actual)
    if target.exists() and any(target.rglob("*.md")):
        sys.exit(f"이미 노트가 있는 폴더입니다(덮어쓰지 않음): {target}\n기존 볼트를 쓰려면: python sb.py setup \"{target}\"")
    try:
        for d in FOLDERS:
            (target / d).mkdir(parents=True, exist_ok=True)
        for src in STARTER.rglob("*"):
            if src.is_file() and src.name != ".gitkeep":
                dst = target / src.relative_to(STARTER)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    except OSError as e:
        sys.exit(f"볼트를 만들지 못했습니다: {e}\n"
                 "Windows에서는 경로가 260자를 넘으면 실패할 수 있습니다. 더 짧은 폴더(예: C:\\Notes\\SecondBrain)를 쓰세요.")
    save_config(vault=str(target))
    print(f"볼트를 만들었습니다: {target}")
    warn_env()
    print("다음: Obsidian에서 '폴더를 보관소로 열기'로 이 폴더를 열고, Dataview·Templater 플러그인을 켜세요.")
    print("      (Templater 템플릿 폴더: 99_System/Templates)")


def cmd_setup(a):
    actual = real_path(Path(a.folder).expanduser())
    if actual is None:
        sys.exit(f"볼트 실제 경로를 확인할 수 없습니다: {a.folder}")
    target = Path(actual)
    if not target.is_dir():
        sys.exit(f"폴더가 없습니다: {target}")
    save_config(vault=str(target))
    print(f"볼트 경로를 저장했습니다: {target}")
    warn_env()
    if not (target / "AGENTS.md").exists():
        print(f"주의: AGENTS.md(볼트 규칙)가 없습니다. {STARTER / 'AGENTS.md'} 를 참고해 만들어 두세요.")
    missing = [k for k, (tpl, _) in KINDS.items()
               if tpl not in BUILTIN and not (target / "99_System" / "Templates" / f"{tpl}.md").exists()]
    if missing:
        print(f"주의: 템플릿이 없어 'sb new {missing[0]}' 등이 실패합니다: {', '.join(missing)}")
        print(f"      {STARTER / '99_System' / 'Templates'} 에서 복사하세요(Obsidian을 닫은 상태에서).")


def cmd_where(a):
    vault = resolve_vault()
    print(f"vault: {vault}")
    print(f"obsidian_root: {obsidian_root(vault)}")
    print(f"agents_md: {vault / 'AGENTS.md'}  exists={(vault / 'AGENTS.md').exists()}")
    print(f"config: {CONFIG}  exists={CONFIG.exists()}")
    print(f"local_md: {LOCAL}  exists={LOCAL.exists()}")
    print(f"skill: {SKILL_DIR}")


def cmd_today(a):
    vault = resolve_vault()
    d = parse_date(a.date) if a.date else now().date()
    week, monday, sunday = iso_week(d)
    daily = folder_of(vault, "daily") / f"{d}.md"
    weekly = folder_of(vault, "weekly") / f"{week}.md"
    print(f"date: {d} ({'월화수목금토일'[d.weekday()]})")
    print(f"now: {now():%Y-%m-%dT%H:%M}")
    print(f"iso_week: {week}  start: {monday}  end: {sunday}")
    print(f"prev: {d - dt.timedelta(days=1)}  next: {d + dt.timedelta(days=1)}")
    print(f"daily: {daily}  exists={daily.exists()}")
    print(f"weekly: {weekly}  exists={weekly.exists()}")
    for label, pattern in CFG.get("today_sources", {}).items():  # 예: {"업무 일지": "../업무 일지/%Y-%m-%d.md"}
        p = obsidian_root(vault) / d.strftime(pattern)
        print(f"{label}: {p}  exists={p.exists()}")


def cmd_render(a):
    print(render(resolve_vault(), a.template, a.title or ""), end="")


def cmd_new(a):
    vault = resolve_vault()
    if a.kind not in KINDS:
        sys.exit(f"종류는 {', '.join(KINDS)} 중 하나입니다.")
    template = KINDS[a.kind][0]
    d = parse_date(a.date) if a.date else now().date()
    if a.kind == "daily":
        title = a.title or str(d)
    elif a.kind == "weekly":
        title = a.title or iso_week(d)[0]
    else:
        title = (a.title or "").strip()
        if not title:
            sys.exit("제목이 필요합니다.")
    if BAD_TITLE.search(title):
        sys.exit(f'제목에 / \\ : * ? " < > | # ^ [ ] 를 쓸 수 없습니다(파일 이름·링크가 깨짐): {title}')
    if SECRET_NAME.search(title):
        sys.exit(f"제목에 비밀 파일로 보이는 단어가 있어 검색·점검에서 빠집니다. 다른 말로 바꾸세요(예: 토큰 → 인증): {title}")
    target = folder_of(vault, a.kind) / f"{title}.md"
    same = [p for p in notes(vault) if p.stem.casefold() == title.casefold()]  # Obsidian 링크는 대소문자를 가리지 않는다
    if target.exists() or same:
        sys.exit(f"이미 있습니다(덮어쓰지 않음): {(same or [target])[0]}")
    body = render(vault, template, title)
    if a.dry_run:
        print(f"[dry-run] {target}\n{body}", end="")
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "x", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except OSError as e:
        sys.exit(f"노트를 만들지 못했습니다: {e}\n경로가 너무 길면 제목을 줄이거나 볼트를 더 짧은 경로로 옮기세요.")
    print(f"created: {target}")


OPEN_TASK = re.compile(r"^\s*- \[ \]\s*(\S.*)$")


def cmd_tasks(a):
    vault = resolve_vault()
    root = obsidian_root(vault)
    today = now().date()
    rows = []
    for p in sorted(walk_files(folder_of(vault, "daily"), root, recursive=False, suffix=".md")):
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        text = note_text(p)
        if text is None:
            continue
        for line in text.splitlines():
            m = OPEN_TASK.match(line)
            if m:
                rows.append(((today - d).days, p.stem, m[1]))
    for p in sorted(walk_files(folder_of(vault, "project"), root, recursive=False, suffix=".md")):
        text = note_text(p)
        if text is None:
            continue
        if (frontmatter(text) or {}).get("status") != "active":
            continue
        for line in text.splitlines():
            m = OPEN_TASK.match(line)
            if m:
                rows.append((None, p.stem, m[1]))
    shown = [r for r in rows if a.older is None or (r[0] is not None and r[0] > a.older)]
    for age, src, task in shown:
        print(f"[[{src}]]\t{'프로젝트' if age is None else f'{age}일 전'}\t{task}")
    if not shown:
        print("해당하는 미완료 할 일 없음")


def cmd_stale(a):
    vault = resolve_vault()
    root = obsidian_root(vault)
    limit = now() - dt.timedelta(days=a.days)
    found = False
    for p in sorted(walk_files(folder_of(vault, "project"), root, recursive=False, suffix=".md")):
        text = note_text(p)
        if text is None or (frontmatter(text) or {}).get("status") != "active":
            continue
        try:
            mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, KST)  # updated보다 파일 수정 시각이 정확하다
        except OSError:
            continue
        if mtime < limit:
            found = True
            print(f"[[{p.stem}]]\t최근 수정 {mtime:%Y-%m-%d}")
    if not found:
        print(f"{a.days}일 넘게 손대지 않은 active 프로젝트 없음")


def cmd_tags(a):
    counts = {}
    for p in notes(resolve_vault()):
        if "99_System" in p.parts:
            continue
        text = note_text(p)
        if text is None:
            continue
        tags = (frontmatter(text) or {}).get("tags", [])
        if isinstance(tags, str):
            tags = [unquote(t) for t in tags.strip("[]").split(",") if t.strip()]
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
    for t, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{t}\t{n}")
    if not counts:
        print("태그 없음")


def normalized_link(target):
    target = target.casefold()
    return target[:-3] if target.endswith(".md") else target


def cmd_backlinks(a):
    vault = resolve_vault()
    root = obsidian_root(vault)
    name = normalized_link(a.name)
    hits = []
    candidates = {}
    for base in read_roots(vault):
        for p in walk_files(base, root, suffix=".md"):
            candidates.setdefault(real_path(p), p)
    for p in sorted(candidates.values()):
        text = note_text(p)
        if text is None:
            continue
        targets = [normalized_link(t) for t in links_of(text)]
        if any(t == name or t.endswith("/" + name) for t in targets):
            hits.append(p)
    for p in hits:
        where = "볼트 안" if under(real_path(p), real_path(vault)) else "볼트 밖(고치지 말고 보고)"
        print(f"{relative_path(p, root).as_posix()}\t{where}")
    if not hits:
        print("백링크 없음")


def cmd_lint(a):
    vault = resolve_vault()
    root = obsidian_root(vault)
    note_paths = list(notes(vault))
    files = [Path(os.path.abspath(f)) for f in a.files] if a.files else note_paths
    missing, inaccessible = [], set()
    for path in files:
        try:
            if not path.is_file():
                missing.append(str(path))
        except OSError:
            inaccessible.add(path)
    if missing:
        sys.exit("파일 없음: " + ", ".join(missing))
    names, paths = link_index(root)
    inbound = {}
    contents = {p: None if p in inaccessible else note_text(p) for p in note_paths}
    for p, text in contents.items():
        for t in links_of(text or ""):
            inbound.setdefault(Path(normalized_link(t)).name, set()).add(p.stem)
    issues, checked = [], 0
    for p in files:
        rel = p.relative_to(vault).as_posix() if p.is_relative_to(vault) else str(p)
        if p in inaccessible or not readable(p, root):
            print(f"{rel}\t제외된 경로(읽지 않음)")
            continue
        if rel.startswith("99_System/") or p.name in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}:
            if a.files:
                print(f"{rel}\t건너뜀(점검 대상 아님: 템플릿·규칙 파일은 sb new로 노트를 만들어 그 노트를 점검)")
            continue
        text = contents[p] if p in contents else note_text(p)
        if text is None:
            print(f"{rel}\t읽을 수 없는 파일(건너뜀)")
            continue
        checked += 1
        fm = frontmatter(text)
        if fm is None:
            issues.append((rel, "frontmatter 없음"))
            fm = {}
        head = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
        for key in re.findall(r"^(\w+):\s*\[\[", head[1] if head else "", re.M):
            issues.append((rel, f"frontmatter '{key}'의 [[링크]]에 따옴표 필요(예: {key}: \"[[노트]]\")"))
        t = fm.get("type", "")
        if fm and t not in TYPES:
            issues.append((rel, f"type 값 이상: '{t}'"))
        if fm and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", str(fm.get("created", ""))):
            issues.append((rel, f"created 형식 이상: '{fm.get('created', '')}'"))
        if t == "project" and fm.get("status") not in {"active", "done", "paused"}:
            issues.append((rel, f"project status 이상: '{fm.get('status', '')}'"))
        h1 = re.search(r"^# (.+)$", text, re.M)
        if h1 and t not in {"weekly", "system"} and h1[1].strip() != p.stem:
            issues.append((rel, f"제목(H1) '{h1[1].strip()}' ≠ 파일 이름"))
        if BAD_NAME.search(p.stem):
            issues.append((rel, "파일 이름에 금지 문자"))
        if "<%" in text or "[[undefined]]" in text or "undefined" in fm.values():
            issues.append((rel, "Templater 잔여 구문 또는 'undefined'"))
        if SECRET.search(text):
            issues.append((rel, "비밀정보로 보이는 문자열 — 확인 후 [비밀정보 제거됨]으로 교체"))
        out = links_of(text)
        for target in out:
            # 일일 노트의 날짜 링크(어제·내일)는 아직 없는 날짜를 가리킬 수 있다
            is_date = re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized_link(target))
            if not resolves(target, names, paths) and not (is_date and t in {"daily", "weekly"}):
                issues.append((rel, f"깨진 링크 [[{target}]]"))
        if t not in {"inbox", "daily", "weekly", "system", ""} and not out and normalized_link(p.name) not in inbound:
            issues.append((rel, "고아 노트(들어오고 나가는 링크 없음)"))
    for rel, msg in issues:
        print(f"{rel}\t{msg}")
    scope = "지정한 파일" if a.files else "볼트 전체"
    print(f"점검({scope}) {checked}개, 문제 {len(issues)}건")
    sys.exit(1 if issues else 0)


def main():
    ap = argparse.ArgumentParser(description="세컨드 브레인 볼트 보조 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("folder"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("setup"); s.add_argument("folder"); s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("where"); s.set_defaults(fn=cmd_where)
    s = sub.add_parser("today"); s.add_argument("--date"); s.set_defaults(fn=cmd_today)
    s = sub.add_parser("render"); s.add_argument("template"); s.add_argument("--title"); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("new"); s.add_argument("kind"); s.add_argument("title", nargs="?"); s.add_argument("--date"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("tasks"); s.add_argument("--older", type=int); s.set_defaults(fn=cmd_tasks)
    s = sub.add_parser("stale"); s.add_argument("--days", type=int, default=14); s.set_defaults(fn=cmd_stale)
    s = sub.add_parser("tags"); s.set_defaults(fn=cmd_tags)
    s = sub.add_parser("backlinks"); s.add_argument("name"); s.set_defaults(fn=cmd_backlinks)
    s = sub.add_parser("lint"); s.add_argument("files", nargs="*"); s.set_defaults(fn=cmd_lint)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
