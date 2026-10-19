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
                                             종류: daily weekly project fix note inbox resource repo check
  python sb.py tasks [--older N]             일일 노트·진행 중 프로젝트의 미완료 할 일
  python sb.py stale [--days 14]             N일 넘게 수정되지 않은 active 프로젝트
  python sb.py tags                          쓰고 있는 태그와 개수
  python sb.py backlinks <노트 이름>          그 노트를 [[링크]]하는 파일 목록
  python sb.py lint [파일...]                 형식·링크·잔여 Templater·비밀정보·남은 충돌 표시 점검(기본: 볼트 전체)
  python sb.py index [--quiet]               99_System/색인.md(폴더별 노트 목록·한 줄 요약)를 다시 만든다(바뀐 게 있을 때만 씀)
  python sb.py log <ingest|query|lint> <제목> [--source S] [--pages 노트...] [--note M]
                                             99_System/브레인 로그.md 끝에 작업 기록 한 건을 덧붙인다

볼트 위치: 환경변수 SECOND_BRAIN > ~/.second-brain/config.json의 "vault" 순서로 찾는다.
config.json 선택 키: folders(종류별 폴더), exclude(열지 않을 폴더, 볼트 또는 Obsidian 루트 기준),
  read_outside(backlinks·lint·render가 읽어도 되는 볼트 밖 폴더, 볼트 기준 "../폴더"), today_sources, utc_offset.
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
    """읽기 경계 비교용 키. 생성·저장·표시에는 display_path를 쓴다."""
    key = _norm(path)
    if key not in _REAL_PATHS:
        try:
            _REAL_PATHS[key] = os.path.normcase(known) if known is not None else _norm(os.path.realpath(key))
        except (OSError, RuntimeError):
            _REAL_PATHS[key] = None
    return _REAL_PATHS[key]


def display_path(path):
    absolute = os.path.abspath(Path(path).expanduser())
    try:
        return Path(os.path.realpath(absolute))
    except (OSError, RuntimeError):
        return Path(absolute)


SKILL_DIR = display_path(__file__).parent.parent
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
    "repo": ("Repo", "40_Resources/저장소"),
    "check": ("Check", "00_Inbox"),  # 점검 결과(사용자 결정 대기 체크리스트) — 제목 "YYYY-MM-DD 점검 결과"
}
# 볼트에 템플릿 파일이 없을 때만 쓰는 기본 구조
BUILTIN = {
    "Resource": '---\ntype: resource\ntags: []\ncreated: <% tp.date.now("YYYY-MM-DDTHH:mm") %>\n---\n'
                "# <% tp.file.title %>\n\n## 요약\n- \n\n## 원본\n- \n",
    # 저장소 노트(/init-project). 템플릿 파일을 볼트에 두지 않는다(켜진 Templater가 새 템플릿 파일을 실행해 망가뜨릴 수 있다).
    "Repo": '---\ntype: repo\narea:\ntags: []\ncreated: <% tp.date.now("YYYY-MM-DDTHH:mm") %>\n---\n'
            "# <% tp.file.title %>\n\n> \n\n## 개요\n\n## 위치\n\n## 스택\n\n## 기능\n\n## 구조와 흐름\n\n"
            "## 현재 상태\n\n## 주요 결정\n\n## 다음 할 일\n\n## 관련\n",
    # 점검 결과("세컨드 브레인 점검"이 만든다). 처리는 /inbox 에서만, 무인 루틴은 건드리지 않는다.
    "Check": '---\ntype: check\ntags: []\ncreated: <% tp.date.now("YYYY-MM-DDTHH:mm") %>\n---\n'
             "# <% tp.file.title %>\n\n"
             "> 🤖 세컨드 브레인 점검에서 사용자 결정이 필요한 항목이다. `/inbox`에서 하나씩 정한다. "
             "정한 항목은 `- [x]`로 바꾸고 줄 끝에 `→ 결정: 내용 (YYYY-MM-DD)`를 단다. 무인 루틴은 이 파일을 처리하지 않는다.\n\n"
             "## 결정 대기\n\n## 웹으로 채울 빈칸\n\n## 처리 결과\n",
}
FOLDERS = ["00_Inbox", "10_Daily/Weekly", "20_Projects", "30_Areas", "40_Resources/해결 기록",
           "40_Resources/참고 자료", "50_Notes", "90_Archive", "99_System/Templates", "99_System/Routines"]
TYPES = {"inbox", "daily", "weekly", "project", "area", "resource", "fix", "note", "system", "journal", "dream", "repo",
         "check"}
INDEX_NOTE = ("99_System", "색인.md")
LOG_NOTE = ("99_System", "브레인 로그.md")
LOG_KINDS = ("ingest", "query", "lint")
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


def check_vault_access(vault):
    try:
        with os.scandir(vault) as entries:
            next(entries, None)
    except OSError:
        sys.exit(f"볼트 폴더를 읽을 수 없습니다: {vault}")


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
        sys.exit(f"볼트 폴더를 읽을 수 없습니다: {vault}")
    if not exists:
        sys.exit(f"볼트 폴더가 없습니다: {vault}")
    VAULT_FOR_EXCLUDE = vault
    if excluded(vault, obsidian_root(vault), actual):
        sys.exit(f"제외된 볼트 폴더입니다(읽지 않음): {vault}")
    check_vault_access(vault)
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
        matched = False
        for pair in roots[1:]:
            anchor = pair[index]
            if under(candidate, anchor):
                matched = True
                if bad_parts(os.path.basename(anchor) + candidate[len(anchor):]):
                    return True
        if matched:
            continue
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
                    # Win32 경로에서 다른 이름으로 해석될 수 있는 항목은 열지 않는다.
                    if os.name == "nt" and entry.name.endswith((".", " ")):
                        continue
                    try:
                        directory = entry.is_dir(follow_symlinks=False)
                        if not directory and suffix:
                            name = entry.name.casefold()
                            if name == suffix or not name.endswith(suffix):
                                continue
                        info = entry.stat(follow_symlinks=False)
                        linked = entry.is_symlink() or (os.name == "nt" and
                                 info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT)
                        if linked and directory:
                            continue
                        if not directory and not entry.is_file():
                            continue
                    except OSError:
                        continue
                    path = Path(entry.path)
                    # 비연결 항목은 검사한 부모의 실제 경로를 재사용한다.
                    actual = real_path(path, None if linked else os.path.join(actual_folder, entry.name))
                    if linked and names_only and not readable(path, root, actual):
                        continue
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
    actual = real_path(path)
    if actual is None:
        sys.exit(f"템플릿의 실제 경로를 확인할 수 없습니다(읽지 않음): {path}")
    root = obsidian_root(vault)
    if excluded(path, root, actual) or SECRET_NAME.search(template_name):
        sys.exit(f"제외된 템플릿 경로입니다(읽지 않음): {path}")
    roots, _, _ = access_rules(vault)
    if not any(under(actual, pair[1]) for pair in roots):
        sys.exit(f"템플릿이 읽기 허용 범위 밖입니다: {path}\n"
                 "공유 템플릿 폴더라면 config.json의 read_outside에 추가하세요.")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        if template_name in BUILTIN:
            text = BUILTIN[template_name]
        else:
            sys.exit(f"템플릿이 없습니다: {path}")
    except OSError:
        sys.exit(f"템플릿을 읽을 수 없습니다: {path}")
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
    target = display_path(a.folder)
    try:
        exists = target.exists()
    except OSError:
        sys.exit(f"볼트 폴더를 읽을 수 없습니다: {target}")
    if exists:
        check_vault_access(target)
        if any(target.rglob("*.md")):
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
    target = display_path(a.folder)
    try:
        exists = target.is_dir()
    except OSError:
        sys.exit(f"볼트 폴더를 읽을 수 없습니다: {target}")
    if not exists:
        sys.exit(f"폴더가 없습니다: {target}")
    check_vault_access(target)
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
    journal = vault / "10_Daily" / "Journal" / f"{d} 세션.md"
    print(f"journal: {journal}  exists={journal.exists()}  (hook 자동 일지 — 읽기만)")
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
    repo_rows = []  # 저장소 노트(/init-project)의 '다음 할 일'
    for p in sorted(walk_files(folder_of(vault, "repo"), root, recursive=False, suffix=".md")):
        text = note_text(p)
        if text is None or (frontmatter(text) or {}).get("type") != "repo":
            continue
        repo_rows += [(p.stem, m[1]) for m in map(OPEN_TASK.match, text.splitlines()) if m]
    shown = [r for r in rows if a.older is None or (r[0] is not None and r[0] > a.older)]
    for age, src, task in shown:
        print(f"[[{src}]]\t{'프로젝트' if age is None else f'{age}일 전'}\t{task}")
    if a.older is None:
        for src, task in repo_rows:
            print(f"[[{src}]]\t저장소\t{task}")
        shown += repo_rows
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
                if a.files:
                    missing.append(str(path))
                else:
                    inaccessible.add(path)
        except OSError:
            inaccessible.add(path)
    if missing:
        sys.exit("파일 없음: " + ", ".join(missing))
    names, paths = link_index(root)
    inbound = {}
    contents = {p: None if p in inaccessible else note_text(p) for p in note_paths}
    for p, text in contents.items():
        if p.is_relative_to(vault) and p.relative_to(vault).parts[:1] == ("99_System",):
            continue  # 색인·브레인 로그·템플릿의 링크는 연결로 치지 않는다
        if (frontmatter(text or "") or {}).get("type") in {"check", "dream"}:
            continue  # 점검 결과·dream 제안이 건 링크도 연결로 치지 않는다(고아 노트가 가려지지 않게)
        for t in links_of(text or ""):
            inbound.setdefault(Path(normalized_link(t)).name, set()).add(p.stem)
    issues, checked = [], 0
    for p in files:
        rel = p.relative_to(vault).as_posix() if p.is_relative_to(vault) else str(p)
        if p in inaccessible and not a.files:
            print(f"{rel}\t읽을 수 없는 파일(건너뜀)")
            continue
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
            if not resolves(target, names, paths) and not (is_date and t in {"daily", "weekly", "journal"}):
                issues.append((rel, f"깨진 링크 [[{target}]]"))
        if t not in {"inbox", "daily", "weekly", "system", "journal", "dream", "check", ""} and not out \
                and normalized_link(p.name) not in inbound:
            issues.append((rel, "고아 노트(들어오고 나가는 링크 없음)"))
        for conflict in re.findall(r"^[ \t]*(?:>[ \t]*)+충돌:[ \t]*(.*)$", strip_code(text), re.M):
            issues.append((rel, f"남은 충돌 표시: {conflict.strip()[:60]} — 출처를 확인해 정리하거나 사용자에게 묻기"))
    for rel, msg in issues:
        print(f"{rel}\t{msg}")
    scope = "지정한 파일" if a.files else "볼트 전체"
    print(f"점검({scope}) {checked}개, 문제 {len(issues)}건")
    sys.exit(1 if issues else 0)


SUMMARY_SECTION = {"fix": "현상", "project": "목표", "resource": "요약"}


def plain(line):
    line = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", line)
    line = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line)
    line = re.sub(r"^\s*(?:[-*>]\s*)+(?:\[[ xX]\]\s*)?", "", line)
    line = re.sub(r"[`*]+", "", line)  # 밑줄은 남긴다(함수·테이블 같은 식별자에 들어 있다)
    return re.sub(r"\s+", " ", line).strip()


def pending_decisions(text):
    """점검 결과 노트의 `## 결정 대기` 절에 남은 `- [ ]` 항목 수(다른 절의 체크박스는 세지 않는다)."""
    section = re.search(r"^## 결정 대기[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return len(re.findall(r"^- \[ \]", section[1], re.M)) if section else 0


def summary_of(text, kind):
    body = re.sub(r"^---\r?\n.*?\r?\n---\r?\n", "", text, count=1, flags=re.S)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    archived = re.search(r"^> 보관:\s*(.+)$", body, re.M)
    if archived:
        return "보관: " + plain(archived[1])
    head = SUMMARY_SECTION.get(kind)
    if head:
        sec = re.search(rf"^## {re.escape(head)}[^\n]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
        for line in (sec[1].splitlines() if sec else []):
            if plain(line):
                return plain(line)
    for line in body.splitlines():  # 제목(#)·표·내비게이션 줄은 건너뛴다
        s = line.strip()
        if not s or s.startswith(("#", "|", "←", "<!--")) or s in {"-", ">", "- [ ]"}:
            continue
        if plain(s):
            return plain(s)
    return ""


def tags_of(fm):
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [unquote(t) for t in tags.strip("[]").split(",") if t.strip()]
    return [t for t in tags if t]


def cmd_index(a):
    vault = resolve_vault()
    groups, daily = {}, {"일일": [], "주간": [], "세션 일지": []}
    for p in notes(vault):
        rel = p.relative_to(vault)
        top = rel.parts[0] if len(rel.parts) > 1 else ""
        if top == "99_System":
            continue
        text = note_text(p)
        if text is None:
            continue
        if top == "10_Daily":
            sub = rel.parts[1] if len(rel.parts) > 2 else ""
            daily["주간" if sub == "Weekly" else "세션 일지" if sub == "Journal" else "일일"].append(p.stem)
            continue
        fm = frontmatter(text) or {}
        kind = fm.get("type", "")
        meta = [x for x in [fm.get("status") if kind == "project" else ""] if x]
        meta += [f"`#{t}`" for t in tags_of(fm)]  # 코드 안의 #은 Obsidian 태그로 잡히지 않는다
        if kind == "check":
            summary = f"결정 대기 {pending_decisions(text)}건"
        else:
            summary = summary_of(text, kind)[:90] if kind not in {"area", "note", "system", "dream"} else ""
        line = f"- {p.stem}" + (f" ({' '.join(meta)})" if meta else "") + (f" — {summary}" if summary else "")
        folder = rel.parent.as_posix() if top else "(볼트 루트)"
        groups.setdefault(folder, []).append(line)
    out = ["# 색인", "",
           "> 🤖 `sb index`가 만든 볼트 목록이다. 손으로 고치지 않는다(다시 만들면 덮어쓴다).",
           "> 볼트에서 찾을 때 이 파일을 먼저 읽고 `## 폴더` + 노트 이름 + `.md`로 연다. 없으면 볼트 안에서 `rg -il <키워드>`.",
           "STAMP", ""]
    out += [f"## 10_Daily", "- " + " · ".join(
        f"{k} {len(v)}개" + (f"(최근: {', '.join(sorted(v)[-3:][::-1])})" if v else "") for k, v in daily.items()), ""]
    for folder in sorted(groups, key=lambda f: (f == "(볼트 루트)", f)):
        rows = sorted(groups[folder])
        if len(rows) > 50:  # 큰 폴더는 이름만(요약을 빼 색인이 한 번에 읽히게). 하위 폴더로 나눌 때가 됐다는 신호.
            rows = [re.sub(r" — .*$", "", r) for r in rows]
            out += [f"## {folder} ({len(rows)}, 50개가 넘어 이름만 — 하위 폴더로 나눌 것)", *rows, ""]
            continue
        out += [f"## {folder} ({len(rows)})", *rows, ""]
    body = "\n".join(out)
    target = vault.joinpath(*INDEX_NOTE)
    old = note_text(target) if target.exists() else None
    old_fm = frontmatter(old or "") or {}
    created = old_fm.get("created") or f"{now():%Y-%m-%dT%H:%M}"
    stamp = f"> 기준: {now():%Y-%m-%d %H:%M} · 노트 {sum(len(v) for v in groups.values())}개"
    new = f"---\ntype: system\ntags: []\ncreated: {created}\n---\n" + body.replace("STAMP", stamp, 1)
    unstamp = lambda t: re.sub(r"^> 기준: .*$", "", re.sub(r"^---\r?\n.*?\r?\n---\r?\n", "", t or "", count=1, flags=re.S), count=1, flags=re.M)
    if old is not None and unstamp(old) == unstamp(new):
        print("색인: 변경 없음" if a.quiet else f"색인 변경 없음: {target}")
        return
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print("색인: 갱신" if a.quiet else f"색인 갱신: {target}\n{stamp[2:]}")


def cmd_log(a):
    vault = resolve_vault()
    if a.kind not in LOG_KINDS:
        sys.exit(f"종류는 {', '.join(LOG_KINDS)} 중 하나입니다(그냥 찾아서 답만 한 질문은 적지 않는다).")
    title = re.sub(r"\s+", " ", a.title).strip()
    entry = [f"## [{now():%Y-%m-%d}] {a.kind} | {title}"]
    if a.source:
        entry.append(f"- 원본: {a.source}")
    if a.pages:
        entry.append("- 고친 노트: " + ", ".join(p if p.startswith("[[") else f"[[{p}]]" for p in a.pages))
    if a.note:
        entry.append(f"- 메모: {a.note}")
    if any(SECRET.search(x) for x in entry):
        sys.exit("비밀정보로 보이는 문자열이 있어 쓰지 않았습니다. [비밀정보 제거됨]으로 바꿔 다시 실행하세요.")
    target = vault.joinpath(*LOG_NOTE)
    try:  # 없을 때만 머리말을 만든다(다른 세션이 동시에 만들면 그쪽 것을 쓴다)
        with open(target, "x", encoding="utf-8", newline="\n") as f:
            f.write(f"---\ntype: system\ntags: []\ncreated: {now():%Y-%m-%dT%H:%M}\n---\n# 브레인 로그\n\n"
                    "> 추가만 하는 작업 기록. 머리줄 `## [YYYY-MM-DD] ingest|query|lint | 제목` 형식을 지킨다"
                    "(`rg \"^## \\[\" \"99_System/브레인 로그.md\"`로 훑는다). 그냥 찾아서 답만 한 질문은 적지 않는다. 쓰기는 `sb log`로.\n")
    except FileExistsError:
        pass
    try:
        with open(target, "rb") as f:
            f.seek(-1, os.SEEK_END)
            last = f.read(1)
    except OSError:
        last = b"\n"
    prefix = "\n" if last == b"\n" else "\n\n"  # 끝 줄바꿈이 없으면 새 머리줄이 앞 줄에 붙는다
    with open(target, "a", encoding="utf-8", newline="\n") as f:  # 덧붙이기만: 동시에 써도 서로 지우지 않는다
        f.write(prefix + "\n".join(entry) + "\n")
    print(f"logged: {entry[0]}")


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
    s = sub.add_parser("index"); s.add_argument("--quiet", action="store_true"); s.set_defaults(fn=cmd_index)
    s = sub.add_parser("log"); s.add_argument("kind"); s.add_argument("title")
    s.add_argument("--source"); s.add_argument("--pages", nargs="*"); s.add_argument("--note"); s.set_defaults(fn=cmd_log)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
