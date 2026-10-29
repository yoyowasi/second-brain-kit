"""brain hook 시나리오 — 가짜 모델로 일지·dream·리마인더 흐름을 임시 볼트·임시 상태·임시 로그 폴더에서 끝까지 돌린다.

실제 볼트·~/.second-brain·~/.claude·~/.codex 는 읽지도 쓰지도 않는다(CLAUDE_CONFIG_DIR·SECOND_BRAIN_HOME·CODEX_HOME 을
임시 폴더로 바꾼다).
대화 기록은 모두 합성이다. tests/test_brain_hooks.py 가 이 파일을 별도 프로세스로 돌린다.
직접 실행: python tests/brain_hooks_scenario.py   (BRAIN_TEST_KEEP=1 이면 임시 폴더를 남긴다)
모든 확인이 통과하면 종료 코드 0, 하나라도 실패하면 1.
"""
import datetime as _dt
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import uuid
from pathlib import Path

sys.dont_write_bytecode = True  # 저장소의 hooks/ 에 __pycache__ 를 남기지 않는다
ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
SB = ROOT / "skills" / "second-brain" / "scripts" / "sb.py"

T = Path(tempfile.mkdtemp(prefix="brain-test-"))
for d in ("home", "logs", "claude", "vault/00_Inbox", "vault/10_Daily", "vault/30_Areas", "vault/99_System", "proj"):
    (T / d).mkdir(parents=True)
os.environ.update(BRAIN_LOG_DIR=str(T / "logs"), SECOND_BRAIN_HOME=str(T / "home"), BRAIN_DIR=str(T / "vault"),
                  CLAUDE_CONFIG_DIR=str(T / "claude"), CODEX_HOME=str(T / "codex"), PYTHONDONTWRITEBYTECODE="1",
                  PYTHONIOENCODING="utf-8")
for k in ("SECOND_BRAIN", "BRAIN_JOURNAL", "DREAM_FORCE", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_HOST_SCHEDULED_RUN"):
    os.environ.pop(k, None)
sys.path.insert(0, str(HOOKS))
import brain_common as bc  # noqa: E402

# 합성 작업 폴더(OS 에 맞는 경로 모양)
WIN = os.name == "nt"
BASE = "C:\\work" if WIN else "/home/me/work"
WORK = os.path.join(BASE, "shop-web")                  # 라벨 shop-web
SIDE = os.path.join(BASE, "side-tool")                 # 라벨 side-tool
PRIVATE = os.path.join("D:\\Private" if WIN else "/home/me/Private", "이력서")
SCRATCH = (os.path.join("C:\\Users\\me\\AppData\\Roaming", "Claude") if WIN
           else "/Users/me/Library/Application Support/Claude")
SW = os.path.join(SCRATCH, "scratch-workspaces", "abc", "scratch-2026-10-13-454230")


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}")


calls = []


def fake(system, prompt, model="haiku", timeout=0):
    calls.append((system[:12], len(prompt), prompt))
    if "작업 일지" in system:
        return "- \"shop-web 주문 상세(orderDetail) API 인자 누락을 고치고 type-check 를 통과시켰다. password=abcd1234 [[링크]]\""
    return ('설명 앞말\n```json\n{"proposals":[{"action":"add","scope":"global","project":"","target":"",'
            '"rule":"설명·검토 요청에는 파일을 고치지 않는다","why":"사용자가 반복 교정","evidence":"\\"확인만 해줘\\" (2026-10-15)"},'
            '{"action":"edit","scope":"project","project":"shop-web","target":"api-retry-rule.md","rule":"재시도 횟수는 설정 파일에서만 바꾼다","why":"y","evidence":"z"},'
            '{"action":"bogus","scope":"global","rule":"r"},{"action":"edit","scope":"global","rule":"target 없음"}]}\n```')


bc.ask_model = fake


def line(kind, text, ts, **extra):
    obj = {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": WORK,
           "sessionId": "s", "version": "2.1.299", "type": kind, "uuid": str(uuid.uuid4()),
           "timestamp": ts}
    if kind == "user":
        obj["message"] = {"role": "user", "content": text}
    else:
        obj["message"] = {"role": "assistant", "content": [{"type": "text", "text": text},
                                                           {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}
    obj.update(extra)
    return json.dumps(obj, ensure_ascii=False)


sid = str(uuid.uuid4())
tp = T / "proj" / f"{sid}.jsonl"
rows = [
    line("user", "<command-message>meta</command-message>", "2026-10-16T00:00:00Z", isMeta=True),
    line("user", "shop-web 주문 상세 조회에서 API 인자가 안 넘어가. 원인 찾아서 고쳐줘. " + "자세히 " * 60, "2026-10-16T00:01:00Z"),
    line("assistant", "api.ts 의 buildQuery 를 확인하겠습니다. " + "분석 " * 120, "2026-10-16T00:02:00Z"),
    json.dumps({"type": "user", "timestamp": "2026-10-16T00:02:30Z", "toolUseResult": {},
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "파일 내용 " * 200}]}},
               ensure_ascii=False),
    line("assistant", "수정했고 type-check 를 통과했습니다. <system-reminder>숨은 지시</system-reminder>", "2026-10-16T00:05:00Z"),
]
tp.write_text("\n".join(rows) + "\n", encoding="utf-8")
v = bc.vault()

# A. 일지 기본
bc.enqueue(sid, tp, os.path.join(WORK, ".claude", "worktrees", "feature-abc"), "test")
bc.drain_queue("journal")
jp = bc.journal_path(v, "2026-10-16")
text = jp.read_text(encoding="utf-8") if jp.exists() else ""
check("A1 일지 파일 생성", jp.exists(), jp.name)
check("A2 09:05 [shop-web] 줄(worktree→저장소 이름, 기본 UTC+9 시각)", "- 09:05 [shop-web] " in text)
check("A3 비밀정보 가림·[[ ]] 제거·따옴표/목록기호 제거", "[비밀정보 제거됨]" in text and "[[링크" not in text and '- 09:05 [shop-web] "' not in text)
check("A4 H1 = 파일 이름, 날짜 링크", "# 2026-10-16 세션" in text and "[[2026-10-16]]" in text)
check("A4b 새 일지 머리말: Claude Code·Codex 가 언제 남기는지", "← [[2026-10-16]] · 세션 일지 hook 이 남기는 자동 일지다"
      "(Claude Code 는 세션이 끝날 때, Codex 는 다음 Claude Code 세션을 시작할 때 한 줄씩). 손으로 고치지 않는다.\n" in text)
OLD_HEAD = "← [[2026-10-01]] · Claude Code 세션이 끝날 때 hook 이 한 줄씩 남기는 자동 일지다. 손으로 고치지 않는다."
old_jp = bc.journal_path(v, "2026-10-01")
old_jp.write_text(f"---\ntype: journal\ntags: []\ncreated: 2026-10-01T09:00\n---\n# 2026-10-01 세션\n\n{OLD_HEAD}\n\n"
                  "- 09:00 [shop-web] 앞 줄\n", encoding="utf-8")
bc.append_journal(v, _dt.datetime(2026, 10, 1, 10, 0, tzinfo=bc.TZ), "shop-web", "뒤 줄")
old_text = old_jp.read_text(encoding="utf-8")
check("A4c 이미 있는 일지는 예전 머리말 그대로 두고 줄만 붙임", OLD_HEAD in old_text and "세션 일지 hook" not in old_text
      and old_text.endswith("- 09:00 [shop-web] 앞 줄\n- 10:00 [shop-web] 뒤 줄\n"), old_text[-120:])
old_jp.unlink()
st = bc.load_state("journal")[sid]
check("A5 상태: 요약한 줄 수 기록", st["done"] == len(rows), st)
prompt = calls[-1][2]
check("A6 메타·도구결과·system-reminder 빼고 보냄", "meta" not in prompt and "파일 내용" not in prompt and "숨은 지시" not in prompt)
check("A7 대기열 비움", not bc.queue_items())

# B. 이어서 연 세션: 늘어난 부분만, 시각 순서 유지
more = [line("user", "이제 07:30 에 했던 일 말고 다른 것도 정리해줘. " + "추가 " * 300, "2026-10-15T22:30:00Z"),
        line("assistant", "정리했습니다. " + "결과 " * 100, "2026-10-15T22:31:00Z")]
with open(tp, "a", encoding="utf-8") as f:
    f.write("\n".join(more) + "\n")
n_before = len(calls)
bc.enqueue(sid, tp, None, "test")
bc.drain_queue("journal")
p2 = calls[-1][2]
check("B1 이어진 세션은 늘어난 부분만 요약", len(calls) == n_before + 1 and "buildQuery" not in p2 and "추가" in p2)
text = jp.read_text(encoding="utf-8")
idx_a, idx_b = text.find("- 07:31 "), text.find("- 09:05 ")
check("B2 늦게 온 이른 시각 줄이 앞에 끼워짐", 0 < idx_a < idx_b, f"{idx_a} {idx_b}")

# C. 1KB 미만은 건너뛰고 done 유지
with open(tp, "a", encoding="utf-8") as f:
    f.write(line("user", "고마워", "2026-10-16T01:00:00Z") + "\n")
done_before = bc.load_state("journal")[sid]["done"]
bc.enqueue(sid, tp, None, "test")
bc.drain_queue("journal")
check("C1 1KB 미만 건너뜀·done 유지", bc.load_state("journal")[sid]["done"] == done_before)

# D. 예약 작업 세션은 뺌(실제 모양: origin scheduled-trigger + <scheduled-task …>)
rid = str(uuid.uuid4())
rp = T / "proj" / f"{rid}.jsonl"
rp.write_text(line("user", '<scheduled-task name="scheduled-task" file="C:\\x\\SKILL.md">This is an automated run of a scheduled task. 당일 작업 정리 ' + "x " * 600,
                   "2026-10-16T00:00:00Z", origin={"kind": "task-notification", "subkind": "scheduled-trigger"}) + "\n", encoding="utf-8")
n_before = len(calls)
bc.enqueue(rid, rp, None, "test")
bc.drain_queue("journal")
check("D1 예약 작업 세션은 모델을 부르지 않음", len(calls) == n_before and bc.load_state("journal")[rid].get("skip") == "예약 작업 세션")
iid = str(uuid.uuid4())
ip = T / "proj" / f"{iid}.jsonl"
ip.write_text(line("user", "99_System/Routines/퇴근 정리.md 프롬프트를 고쳐줘. " + "설명 " * 400, "2026-10-16T02:00:00Z") + "\n"
              + line("assistant", "고쳤습니다. " + "변경 " * 200, "2026-10-16T02:05:00Z") + "\n", encoding="utf-8")
n_before = len(calls)
bc.enqueue(iid, ip, None, "test")
bc.drain_queue("journal")
check("D2 Routines 를 언급한 사람 세션은 빼지 않음", len(calls) == n_before + 1 and not bc.load_state("journal")[iid].get("skip"))

# D2a. 끝 구분자가 붙은 제외 항목도 그 폴더 자체를 거르고, 이름이 이어지는 옆 폴더는 거르지 않음
bc.CFG["journal_exclude"] = [PRIVATE + os.sep]
check("D2a 제외 폴더 자체·하위는 빼고 옆 폴더는 남김",
      bc.cwd_skip_reason(PRIVATE) == "제외 폴더 세션"
      and bc.cwd_skip_reason(os.path.join(PRIVATE, "x")) == "제외 폴더 세션"
      and bc.cwd_skip_reason(PRIVATE + "2") is None)

# D2b. 따라잡기 항목(cwd 없음)도 기록의 cwd 로 제외 폴더를 판정
bc.CFG["journal_exclude"] = [PRIVATE]
xid = str(uuid.uuid4())
xp = T / "proj" / f"{xid}.jsonl"
xp.write_text("\n".join([line("user", "이력서 고쳐줘 " + "내용 " * 400, "2026-10-16T04:00:00Z", cwd=PRIVATE),
                         line("assistant", "고쳤습니다 " + "답 " * 200, "2026-10-16T04:05:00Z", cwd=PRIVATE)]) + "\n",
              encoding="utf-8")
n_before = len(calls)
bc.enqueue(xid, xp, None, "catch-up")
bc.drain_queue("journal")
check("D2b 따라잡기 항목도 제외 폴더면 모델을 부르지 않음", len(calls) == n_before and bc.load_state("journal")[xid].get("skip") == "제외 폴더 세션")
bc.CFG.pop("journal_exclude")

# D2c. 데스크톱 폴더 없는 대화는 남기고 [폴더 없음] 라벨, 세션 도중 폴더를 옮기면 기록이 저장된 프로젝트 폴더
sid2 = str(uuid.uuid4())
sp2 = T / "proj" / f"{sid2}.jsonl"
sp2.write_text("\n".join([line("user", "스킬 개선해줘 " + "내용 " * 400, "2026-10-16T05:00:00Z", cwd=SW),
                          line("assistant", "개선했습니다 " + "답 " * 200, "2026-10-16T05:05:00Z", cwd=SW)]) + "\n", encoding="utf-8")
bc.enqueue(sid2, sp2, None, "catch-up")
bc.drain_queue("journal")
check("D2c 폴더 없는 대화는 [폴더 없음]으로 기록", "- 14:05 [폴더 없음] " in bc.journal_path(v, "2026-10-16").read_text(encoding="utf-8"))
mv = str(uuid.uuid4())
(T / slug(SIDE)).mkdir(exist_ok=True)
mp = T / slug(SIDE) / f"{mv}.jsonl"  # 기록이 side-tool 프로젝트 폴더에 저장된 세션
mp.write_text("\n".join([line("user", "시작 " + "x " * 10, "2026-10-16T05:10:00Z", cwd=SW),
                         line("user", "중간 " + "y " * 10, "2026-10-16T05:11:00Z", cwd=SIDE),
                         line("user", "끝 " + "z " * 10, "2026-10-16T05:12:00Z", cwd=os.path.join(SIDE, "logs"))]) + "\n",
              encoding="utf-8")
lp = T / "proj" / f"{uuid.uuid4()}.jsonl"  # 저장 폴더와 맞는 cwd 가 없으면 처음 Windows 형식 cwd(그 밖 OS 는 처음 cwd)
first = SW.replace("C:\\", "/c/").replace("\\", "/") if WIN else SW
lp.write_text("\n".join([line("user", "a", "2026-10-16T05:10:00Z", cwd=first),
                         line("user", "b", "2026-10-16T05:11:00Z", cwd=SW),
                         line("user", "c", "2026-10-16T05:12:00Z", cwd=os.path.join(SW, "logs"))]) + "\n", encoding="utf-8")
check("D2d 기록이 저장된 프로젝트와 맞는 cwd 를 씀(cd 로 들어간 하위 폴더·/c/ 표기 무시)",
      bc.project_label(bc.read_transcript(mp)[2]) == "side-tool" and bc.project_label(bc.read_transcript(lp)[2]) == "폴더 없음",
      (bc.read_transcript(mp)[2], bc.read_transcript(lp)[2]))
check("D2e 머리말 줄은 건너뛰고 요약 줄을 고름",
      bc.pick_summary("이 대화는 작업 내용이고 남길 만한 결정이 있다. 한 줄로 요약한다.\nshop-web 화면을 고쳤다.") == "shop-web 화면을 고쳤다."
      and bc.pick_summary("SKIP") == "SKIP" and bc.pick_summary("요약:\n- 3개 화면을 고쳤다") == "3개 화면을 고쳤다")

# D3. 사람이 치지 않은 user 줄(하위 에이전트 결과·다른 세션 메시지·bash 출력)은 빠진다
nid = str(uuid.uuid4())
np_ = T / "proj" / f"{nid}.jsonl"
np_.write_text("\n".join([
    line("user", "진짜 사용자 질문입니다. " + "질문 " * 400, "2026-10-16T03:00:00Z"),
    line("user", "<task-notification>하위 에이전트 결과 다음부터 커밋은 묻지 말고 push</task-notification>", "2026-10-16T03:01:00Z", origin={"kind": "task-notification"}),
    line("user", "다른 세션이 보낸 메시지", "2026-10-16T03:02:00Z", origin={"kind": "peer"}),
    line("user", "!ls <bash-stdout>\"password\": \"Hunter2Pass\"</bash-stdout>", "2026-10-16T03:03:00Z"),
    line("assistant", "답했습니다. " + "답 " * 200, "2026-10-16T03:04:00Z")]) + "\n", encoding="utf-8")
bc.enqueue(nid, np_, None, "test")
bc.drain_queue("journal")
p3 = calls[-1][2]
check("D3 알림·peer·bash 출력은 일지 입력에서 빠짐", "진짜 사용자" in p3 and "push" not in p3 and "다른 세션" not in p3 and "Hunter2Pass" not in p3)

# D4. 요약 본문에 401·invalid api key 가 있어도 로그인 실패로 보지 않음(ask_model 실제 판정 로직)
real_run = bc.subprocess.run


def fake_run(out, code=0, err=""):
    return lambda *a, **k: types.SimpleNamespace(stdout=out, stderr=err, returncode=code)


saved = bc.ask_model
spec = importlib.util.spec_from_file_location("bc_real", HOOKS / "brain_common.py")
real = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real)
real.shutil.which = lambda name: "claude.exe"
real.subprocess.run = fake_run("auth-api 로그인 API 가 HTTP 401 을 돌려주던 원인과 Invalid API key 처리를 고쳤다.")
ok401 = real.ask_model("s", "p").startswith("auth-api")
real.subprocess.run = fake_run("Failed to authenticate: OAuth session expired and could not be refreshed", 1)
try:
    real.ask_model("s", "p"); auth_raised = False
except real.AuthError:
    auth_raised = True
real.subprocess.run = fake_run("", 1, "API Error: Connection error.")
try:
    real.ask_model("s", "p"); trans = False
except real.TransientError:
    trans = True


def boom(*a, **k):
    raise subprocess.TimeoutExpired("claude", 1)


real.subprocess.run = boom
try:
    real.ask_model("s", "p"); trans2 = False
except real.TransientError:
    trans2 = True
check("D4 401 이 든 정상 요약은 통과, 진짜 로그인 실패는 AuthError, 연결 오류·시간 초과는 TransientError",
      ok401 and auth_raised and trans and trans2, (ok401, auth_raised, trans, trans2))


def auth_of(out, code=0):
    real.subprocess.run = fake_run(out, code)
    try:
        real.ask_model("s", "p")
        return False
    except real.AuthError:
        return True


# D4b. 종료 코드 0 인 답은 CLI 문구(Please run /login·authentication_error)가 있을 때만 로그인 실패
SUMMARIES = ["OAuth token 갱신이 실패하던 원인을 찾아 재시도 로직을 고쳤다.", "Not logged in 상태 표시를 고쳤다.",
             "Invalid API key 오류 문구를 바꿨다."]
CLI_AUTH = ["Not logged in · Please run /login", "Invalid API key · Please run /login",
            'API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"OAuth token has expired."}}']
check("D4b 'OAuth token…'으로 시작하는 정상 요약은 통과, CLI 로그인 안내는 종료 코드 0 이어도 AuthError",
      not any(auth_of(s) for s in SUMMARIES) and all(auth_of(s) for s in CLI_AUTH),
      ([auth_of(s) for s in SUMMARIES], [auth_of(s) for s in CLI_AUTH]))
real.subprocess.run = real_run
bc.ask_model = saved

# D5. 일시 오류는 항목을 버리지 않고 tries 도 올리지 않음, 회복 후 처리
tid = str(uuid.uuid4())
tp2 = T / "proj" / f"{tid}.jsonl"
shutil.copy(tp, tp2)


def transient(*a, **k):
    raise bc.TransientError("usage limit reached")


bc.ask_model = transient
for _ in range(4):
    r = bc.drain_queue("journal") if bc.enqueue(tid, tp2, None, "test") else None
item = json.loads((bc.QUEUE / f"{tid}.json").read_text(encoding="utf-8"))
check("D5 일시 오류 4번에도 항목 유지·tries 0·size 미기록", r == "transient" and item["tries"] == 0 and "size" not in bc.load_state("journal").get(tid, {}))
bc.ask_model = fake
bc.drain_queue("journal")
check("D6 회복 후 처리", not (bc.QUEUE / f"{tid}.json").exists() and bc.load_state("journal")[tid]["done"] > 0)

# D7. 일지 쓰기 실패면 done 을 올리지 않음
wid = str(uuid.uuid4())
wp = T / "proj" / f"{wid}.jsonl"
shutil.copy(tp, wp)
orig_append = bc.append_journal
bc.append_journal = lambda *a, **k: (_ for _ in ()).throw(PermissionError("drive lock"))
bc.enqueue(wid, wp, None, "test")
bc.drain_queue("journal")
bc.append_journal = orig_append
st_w = bc.load_state("journal").get(wid, {})
check("D7 쓰기 실패 시 done 0 유지·항목 남음(tries 1)", st_w.get("done", 0) == 0 and json.loads((bc.QUEUE / f"{wid}.json").read_text(encoding="utf-8"))["tries"] == 1)
bc.drain_queue("journal")
check("D8 다음 실행에서 정상 기록", not (bc.QUEUE / f"{wid}.json").exists() and bc.load_state("journal")[wid]["done"] > 0)

# D9. 처리 중 같은 세션이 다시 들어오면 새 항목은 남긴다
rid2 = str(uuid.uuid4())
rp2 = T / "proj" / f"{rid2}.jsonl"
shutil.copy(tp, rp2)
bc.enqueue(rid2, rp2, None, "first")


def reenqueue_then_fake(system, prompt, **k):
    bc.enqueue(rid2, rp2, None, "second")
    return fake(system, prompt)


bc.ask_model = reenqueue_then_fake
bc.drain_queue("journal")
bc.ask_model = fake
check("D9 처리 중 다시 들어온 항목은 지우지 않음", (bc.QUEUE / f"{rid2}.json").exists())
bc.drain_queue("journal")

# D10. OS 잠금: 같은 프로세스 안 두 번째 잠금은 기다리다 시간 초과
with bc.Lock(wait=0):
    try:
        with bc.Lock(wait=1):
            second = True
    except TimeoutError:
        second = False
check("D10 잠금 상호 배제", second is False)
with bc.Lock(wait=1):
    pass
check("D11 풀린 뒤 다시 잡힘", True)

# D12. clean_line 이 이미지·HTML·Templater 를 무력화
cl = bc.clean_line('요약 ![x](https://evil/?d=1) <img src=x> <% tp.file.title %> [[링크]]')
check("D12 이미지·HTML·Templater·위키링크 무력화", "![" not in cl and "<" not in cl and "[[" not in cl, cl)
check("D13 비밀정보 추가 형태", all("[비밀정보 제거됨]" in bc.scrub(s) for s in [
    '"password": "Hunter2Pass"', "sqlcmd -S x -P Sup3rSecret", "DB_PASS=abcd", "glpat-abcdefghij12345", "카드 4111-1111-1111-1111",
    "주민 9001011234567", "폰 010-1234-5678"]) and bc.scrub("mkdir -p dir") == "mkdir -p dir" and bc.scrub("bypass = true") == "bypass = true")


# E. 로그인 실패: 대기열 보존 + 상태 기록 + 알림
def auth_fail(*a, **k):
    raise bc.AuthError("Failed to authenticate: OAuth session expired")


bc.ask_model = auth_fail
eid = str(uuid.uuid4())
ep = T / "proj" / f"{eid}.jsonl"
shutil.copy(tp, ep)
bc.enqueue(eid, ep, None, "test")
bc.drain_queue("journal")
check("E1 로그인 실패 시 대기열 보존", any(p.stem == eid for p in bc.queue_items()))
check("E2 auth 상태 기록", bool(bc.load_state("auth").get("failed_at")))
env = dict(os.environ)
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True, env=env).stdout.decode("utf-8")
check("E3 알림: 점검 권유(lint 기록 없음) + 로그인 안내", "[brain] 세컨드 브레인 점검" in out and "claude auth login" in out, out.count("[brain]"))
out2 = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True, env=env).stdout.decode("utf-8")
check("E4 같은 날 두 번째 세션은 조용함", out2.strip() == "", repr(out2[:80]))
env0 = dict(env, CLAUDE_CODE_SESSION_ATTENDED="0")
bc.save_state("remind", {})
out3 = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True, env=env0).stdout.decode("utf-8")
check("E5 무인 세션은 안내 없음·하루 한 번 표시도 안 씀", out3.strip() == "" and bc.load_state("remind") == {})
bc.ask_model = fake
bc.drain_queue("journal")
check("E6 로그인 회복 후 대기열 처리·auth 상태 지움", not bc.queue_items() and not bc.load_state("auth"))

# F. dream: 합성 대화 기록(임시 projects 폴더)에서 발췌 → 가짜 모델 JSON → 형식 맞는 것만 인박스
bc.PROJECTS = T / "projects"
bc.GLOBAL_MD = T / "CLAUDE.md"
bc.GLOBAL_MD.write_text("# 공통\n<!-- brain:start -->\n# 배운 규칙 (dream)\n<!-- dream-last-id: 0 -->\n<!-- brain:end -->\n", encoding="utf-8")


def _recent(minutes):
    return (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


for cwd_, said in [(WORK, "아니 그게 아니라, 확인만 해줘. 파일은 고치지 마. "), (SIDE, "다음부터 커밋은 내가 할게. ")]:
    (bc.PROJECTS / slug(cwd_) / "memory").mkdir(parents=True, exist_ok=True)
    (bc.PROJECTS / slug(cwd_) / "memory" / "MEMORY.md").write_text("- [기존 규칙](rule.md) — 예시\n", encoding="utf-8")
    (bc.PROJECTS / slug(cwd_) / f"{uuid.uuid4()}.jsonl").write_text("\n".join([
        line("assistant", "api.ts 를 고쳤습니다. " + "설명 " * 100, _recent(90), cwd=cwd_),
        line("user", said + "이유 " * 50, _recent(80), cwd=cwd_),
        line("assistant", "알겠습니다. " + "답 " * 50, _recent(70), cwd=cwd_)]) + "\n", encoding="utf-8")
dream = load("brain-dream")
os.environ["DREAM_FORCE"] = "1"
n_before = len(calls)
dream.daily(v)
files = sorted((v / "00_Inbox").glob("*dream*.md"))
body = files[0].read_text(encoding="utf-8") if files else ""
check("F1 합성 대화 발췌로 모델 1회 호출", len(calls) == n_before + 1, f"prompt {calls[-1][1] if len(calls) > n_before else 0}B")
dprompt = calls[-1][2] if len(calls) > n_before else ""
check("F2 발췌 120KB 이하·현재 규칙·판단 방식 포함", len(dprompt.encode()) < 160 * 1024 and "<현재 규칙>" in dprompt and "<발췌>" in dprompt)
check("F3 인박스 제안 파일(type: dream, H1=이름)", files and "type: dream" in body and f"# {files[0].stem}" in body, files[0].name if files else "")
key = re.escape(slug(WORK))
check("F4 형식 맞는 2개만(bogus·target 없는 edit 제외)", body.count("\n## ") == 2 and "## 1. 추가 · 전역" in body
      and re.search(rf"## 2\. 고치기 · 프로젝트 shop-web( \(memory: {key}\))? · 대상 api-retry-rule\.md", body))
check("F4b shop-web 기록은 메모리 폴더 키가 붙음", f"(memory: {slug(WORK)})" in body,
      body.split("\n## 2.")[1][:80] if "\n## 2." in body else "")
check("F4c 이미 제안됨 블록 포함", "<이미 제안됨>" in dprompt)
check("F5 상태: 오늘 실행 기록", bc.load_state("dream").get("last_run_date") == bc.now().date().isoformat())
n_before = len(calls)
dream.daily(v)
check("F6a 지난 실행 뒤 새 대화가 없으면 모델을 부르지 않음", len(calls) == n_before)
dream.write_inbox(v, dream.parse(fake("x", "")), "dream 규칙 제안", "test")
check("F6b 같은 날 다시 써도 덮어쓰지 않고 새 파일", len(sorted((v / "00_Inbox").glob("*dream*.md"))) == 2)
check("F7 parse: 리스트·단일 객체 답도 받음", len(dream.parse('[{"action":"remove","scope":"global","target":"[L01]"}]')) == 1
      and len(dream.parse('[{"action":"remove","scope":"global","target":"[L01]"},{"action":"add","scope":"global","rule":"r"}]')) == 2)
check("F8 parse: 깨진 JSON 은 빈 목록", dream.parse("SKIP") == [] and dream.parse("{oops") == [])
check("F8b 근거 인용 따옴표·숫자로 시작하는 문장 보존", '"확인만 해줘"' in body and bc.clean_line("3개 화면을 고쳤다") == "3개 화면을 고쳤다"
      and bc.clean_line('1. "요약"') == "요약")
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True,
                     env=dict(os.environ)).stdout.decode("utf-8")
check("F9 알림: dream 제안 대기", "dream 규칙 제안이 2건" in out, out[:100])
check("F9b 점검 결과가 없으면 결정 대기 알림 없음", "점검 결과 결정 대기" not in out and "/inbox 로 먼저" not in out)

# F10. 점검 결과(type: check)의 '결정 대기' 미처리 항목 알림(다른 절의 체크박스는 세지 않음)
(v / "00_Inbox" / "2026-10-19 점검 결과.md").write_text(
    "---\ntype: check\ntags: []\ncreated: 2026-10-19T10:00\n---\n# 2026-10-19 점검 결과\n\n## 결정 대기\n\n### A. 상태\n"
    "- [ ] [A1] [[x]] — 문제\n- [x] [A2] [[y]] — 문제 → 결정: 닫기 (2026-10-19)\n- [ ] [A3] [[z]] — 문제\n"
    "- [ ] [A4] [[w]] — 문제 → 보류: 자료를 기다림 (2026-10-19)\n\n"
    "## 웹으로 채울 빈칸\n- 조사 항목\n\n## 처리 결과\n- [ ] 이 줄은 세지 않는다\n", encoding="utf-8")
bc.save_state("remind", {})
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True,
                     env=dict(os.environ)).stdout.decode("utf-8")
check("F10 알림: 점검 결과 결정 대기 2건(결정 대기 절만 셈, → 보류 항목은 뺌)", "점검 결과 결정 대기가 2건" in out, out[:160])
# F11. 7일 점검 권유(이 볼트는 lint 기록이 없다)에 앞선 점검 결과를 먼저 처리하라는 안내가 붙는다
check("F11 7일 점검 권유에 앞선 결과 먼저 처리 안내", "점검(lint)을 한 번도 하지 않았다" in out and "결정 대기 2건을 /inbox 로 먼저" in out)
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True,
                     env=dict(os.environ)).stdout.decode("utf-8")
check("F11b 같은 날 두 번째 세션은 다시 알리지 않음", "점검 결과 결정 대기" not in out and "점검(lint)" not in out, out[:160])

# I. dream 발췌 묶음: 오래된 것부터 EXCERPT_MAX 묶음, 한 번에 3묶음까지 모델 호출, 남은 말은 다음 실행이 이어서 본다
bc.PROJECTS = T / "projects2"
CHUNK = os.path.join(BASE, "chunk-app")
(bc.PROJECTS / slug(CHUNK)).mkdir(parents=True)
t0 = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0) - _dt.timedelta(hours=5)
stamps = [t0 + _dt.timedelta(minutes=2 * i + 1) for i in range(12)]
iso = "%Y-%m-%dT%H:%M:%SZ"
(bc.PROJECTS / slug(CHUNK) / f"{uuid.uuid4()}.jsonl").write_text("\n".join(
    row for i, s in enumerate(stamps) for row in (
        line("assistant", f"답{i:02d} " + "설명 " * 20, (s - _dt.timedelta(seconds=30)).strftime(iso), cwd=CHUNK),
        line("user", f"[m{i:02d}] 다음부터는 이렇게 해줘 " + "가" * 100, s.strftime(iso), cwd=CHUNK))) + "\n", encoding="utf-8")
(v / "00_Inbox" / f"{bc.now():%Y-%m-%d} dream 규칙 제안 정정.md").write_text(
    "---\ntype: dream\ntags: []\n---\n# x\n\n## 1. 추가 · 전역\n- 규칙: 원래 규칙 문장\n"
    "- 사용자 정정 (2026-10-19): 커밋 메시지는 한국어로 쓴다\n"
    "- 사용자 정정 (2026-10-19): 1 \"폰 010-1234-5678 로 연락\" → 연락처는 적지 않는다\n", encoding="utf-8")
check("I0 이미 제안됨에 사용자 정정 줄도 넣음·시스템 지시에 정정 주제 재제안 금지",
      "사용자 정정 (2026-10-19): 커밋 메시지는 한국어로 쓴다" in dream.proposed_before(v)
      and "원래 규칙 문장" in dream.proposed_before(v) and "사용자 정정" in dream.DREAM_SYSTEM)
# I0b. 보관함 규칙이 6000자를 넘어도 인박스의 정정 줄·보류 규칙은 남고, 줄 중간에서 자르지 않는다
PB = T / "vault-pb"
for d in ("00_Inbox", "90_Archive"):
    (PB / d).mkdir(parents=True)
for k in range(1, 21):  # 지난 20일 동안 하루 5개씩 처리된 제안(규칙 약 70자)
    day = (bc.now().date() - _dt.timedelta(days=k)).isoformat()
    (PB / "90_Archive" / f"{day} dream 규칙 제안.md").write_text("---\ntype: dream\n---\n" + "".join(
        f"## {i}. 추가 · 전역\n- 규칙: {day} 보관 규칙 {i}번 " + "가" * 50 + "\n" for i in range(1, 6)), encoding="utf-8")
(PB / "00_Inbox" / f"{bc.now().date() - _dt.timedelta(days=1)} dream 규칙 제안.md").write_text(
    "---\ntype: dream\n---\n## 1. 추가 · 전역\n- 규칙: PENDING 보류 규칙\n"
    f"- 사용자 정정({bc.now().date()}): 1 \"그건 아니고\" → CORRECTED 방향\n", encoding="utf-8")
pb = dream.proposed_before(PB)
newest = f"{bc.now().date() - _dt.timedelta(days=1)} 보관 규칙 5번"
oldest = f"{bc.now().date() - _dt.timedelta(days=20)} 보관 규칙 1번"
check("I0b 보관함이 넘쳐도 정정·보류 줄은 남김, 보관함은 최근 것부터, 줄 단위로 자름",
      len(pb) <= 6000 and "CORRECTED" in pb and "PENDING" in pb and newest in pb and oldest not in pb
      and all(s.startswith("- (") for s in pb.splitlines()) and pb.index(newest) < pb.index("PENDING"),
      (len(pb), pb[:40]))
bc.save_state("dream", {})
rows_i = dream.collect(time.time() - 2 * 86400)[0]
saved_max = dream.EXCERPT_MAX
dream.EXCERPT_MAX = 2 * len(rows_i[0][2].encode("utf-8"))  # 같은 크기 블록 2개씩 → 6묶음


def P(rule):
    return {"action": "add", "scope": "global", "project": "", "target": "", "rule": rule, "why": "w", "evidence": "e"}


SEQ = [[P("커밋은 사용자가 한다"), P("확인 요청에는 파일을 고치지 않는다")],
       [P("커밋은, 사용자가  한다."), P("설명은 결론부터 쓴다"), P("테스트는 임시 폴더에서만 돌린다")],
       [P("배포는 승인 뒤에만 한다"), P("로그 전체를 읽지 않는다"), P("여섯째 규칙")]]
chunk_calls = []


def chunk_fake(system, prompt, model="haiku", timeout=0):
    chunk_calls.append(prompt)
    return json.dumps({"proposals": SEQ[(len(chunk_calls) - 1) % 3]}, ensure_ascii=False)


bc.ask_model = chunk_fake
inbox_before = set((v / "00_Inbox").glob("*dream*.md"))
dream.daily(v)
new_files = sorted(set((v / "00_Inbox").glob("*dream*.md")) - inbox_before)
ibody = new_files[0].read_text(encoding="utf-8") if new_files else ""
st_i = bc.load_state("dream")
check("I1 12개 말(6묶음) 중 3묶음만 모델 호출", len(rows_i) == 12 and len(dream.chunks(rows_i)) == 6 and len(chunk_calls) == 3,
      (len(rows_i), len(chunk_calls)))
# 셋째 묶음 제안 3개 중 1개만 5개 상한에 들어간다 → 셋째 묶음은 반영하지 않고(제안도 버림) 다음 실행이 다시 본다.
check("I2 제안을 다 받은 마지막 묶음(둘째, [m03])까지만 last_run_utc 로(넘친 셋째 묶음은 다시 봄)",
      st_i.get("last_run_utc") == stamps[3].timestamp() and st_i.get("last_run_date") == bc.now().date().isoformat(), st_i)
check("I3 묶음 순서: 오래된 것부터, 첫 묶음은 [m00][m01]만, 넘긴 [m06]~ 은 보내지 않음",
      "[m00]" in chunk_calls[0] and "[m01]" in chunk_calls[0] and "[m02]" not in chunk_calls[0]
      and "[m05]" in chunk_calls[2] and not any(f"[m{i:02d}]" in c for c in chunk_calls for i in range(6, 12)))
check("I4 제안 합치기: 같은 규칙(문장부호·공백 차이)은 먼저 것만, 5개를 넘긴 셋째 묶음 제안은 하나도 쓰지 않음",
      len(new_files) == 1 and ibody.count("\n## ") == 4 and "커밋은, 사용자가" not in ibody
      and "배포는 승인" not in ibody and "여섯째 규칙" not in ibody
      and ibody.index("커밋은 사용자가 한다") < ibody.index("설명은 결론부터") < ibody.index("테스트는 임시"), ibody[-600:])
check("I5 뒤 묶음의 이미 제안됨에 앞 묶음 제안·사용자 정정 포함",
      "(이번 실행) 커밋은 사용자가 한다" in chunk_calls[1] and "사용자 정정 (2026-10-19)" in chunk_calls[0]
      and "(이번 실행)" not in chunk_calls[0])
check("I5b 이미 제안됨(사용자 정정 줄)도 비밀정보를 가린 뒤 모델로 보냄",
      "010-1234-5678" not in "".join(chunk_calls) and "[비밀정보 제거됨]" in chunk_calls[0])
dlog = (T / "logs" / "brain-dream.log").read_text(encoding="utf-8")
check("I6 넘긴 수와 까닭을 기록·인박스 메타에 표시", "6묶음 중 2묶음만 반영(제안 5개가 차서)" in dlog and "사용자 말 8개는" in dlog
      and "다음 실행으로 넘김 8개" in ibody)
chunk_calls.clear()


def again_fake(system, prompt, model="haiku", timeout=0):
    chunk_calls.append(prompt)
    return json.dumps({"proposals": SEQ[2] if len(chunk_calls) == 1 else []}, ensure_ascii=False)


bc.ask_model = again_fake
inbox_before = set((v / "00_Inbox").glob("*dream*.md"))
dream.daily(v)
st_i2 = bc.load_state("dream")
again = "".join(p.read_text(encoding="utf-8") for p in set((v / "00_Inbox").glob("*dream*.md")) - inbox_before)
check("I7 다음 실행은 넘친 셋째 묶음([m04])부터 다시 보고 그 제안을 씀, 3묶음 뒤([m09])까지 기록",
      len(chunk_calls) == 3 and "[m04]" in chunk_calls[0] and "[m05]" in chunk_calls[0]
      and not any(f"[m{i:02d}]" in "".join(chunk_calls) for i in range(4))
      and "배포는 승인" in again and "여섯째 규칙" in again and st_i2["last_run_utc"] == stamps[9].timestamp(),
      (len(chunk_calls), st_i2))
chunk_calls.clear()
bc.ask_model = lambda system, prompt, **k: (chunk_calls.append(prompt), '{"proposals":[]}')[1]
dream.daily(v)
check("I7b 그다음 실행이 남은 말([m10][m11])을 끝까지 봄", len(chunk_calls) == 1 and "[m10]" in chunk_calls[0]
      and "[m11]" in chunk_calls[0] and bc.load_state("dream")["last_run_utc"] > stamps[-1].timestamp())
chunk_calls.clear()


def fail_second(system, prompt, model="haiku", timeout=0):
    if chunk_calls:
        raise bc.TransientError("usage limit")
    return chunk_fake(system, prompt)


bc.save_state("dream", {})
chunk_calls.clear()
bc.ask_model = fail_second
inbox_before = set((v / "00_Inbox").glob("*dream*.md"))
dream.daily(v)
st_i3 = bc.load_state("dream")
check("I8 둘째 묶음에서 일시 오류: 첫 묶음 제안은 쓰고, 그 뒤부터 1시간 뒤 이어서(last_run_date 미기록)",
      len(set((v / "00_Inbox").glob("*dream*.md")) - inbox_before) == 1
      and st_i3.get("last_run_utc") == stamps[1].timestamp() and "last_run_date" not in st_i3, st_i3)


def seven_fake(system, prompt, model="haiku", timeout=0):
    chunk_calls.append(prompt)
    return json.dumps({"proposals": [P(f"넘침 규칙 {i}번") for i in range(1, 8)]}, ensure_ascii=False)


bc.save_state("dream", {})
chunk_calls.clear()
bc.ask_model = seven_fake
inbox_before = set((v / "00_Inbox").glob("*dream*.md"))
dream.daily(v)
st_i4 = bc.load_state("dream")
over = "".join(p.read_text(encoding="utf-8") for p in set((v / "00_Inbox").glob("*dream*.md")) - inbox_before)
check("I9 첫 묶음 혼자 5개를 넘으면 앞 5개만 쓰고 본 것으로 침, 5개가 차면 다음 묶음은 모델을 부르지 않음",
      len(chunk_calls) == 1 and over.count("\n## ") == 5 and "넘침 규칙 5번" in over and "넘침 규칙 6번" not in over
      and st_i4.get("last_run_utc") == stamps[1].timestamp() and st_i4.get("last_run_date") == bc.now().date().isoformat(),
      (len(chunk_calls), st_i4))


def zero_then_six(system, prompt, model="haiku", timeout=0):
    chunk_calls.append(prompt)
    rules = [] if len(chunk_calls) == 1 else [P(f"둘째 묶음 규칙 {i}번") for i in range(1, 7)]
    return json.dumps({"proposals": rules}, ensure_ascii=False)


# I9b. 앞 묶음 제안이 0개면 다음 묶음 혼자 5개를 넘어도 첫 묶음처럼 앞 5개를 쓰고 본 것으로 친다
bc.save_state("dream", {})
chunk_calls.clear()
bc.ask_model = zero_then_six
inbox_before = set((v / "00_Inbox").glob("*dream*.md"))
log_before = len((T / "logs" / "brain-dream.log").read_text(encoding="utf-8"))
dream.daily(v)
st_i5 = bc.load_state("dream")
second = "".join(p.read_text(encoding="utf-8") for p in set((v / "00_Inbox").glob("*dream*.md")) - inbox_before)
dlog = (T / "logs" / "brain-dream.log").read_text(encoding="utf-8")[log_before:]
check("I9b 앞 묶음 제안 0개 뒤 넘친 묶음은 앞 5개를 쓰고 그 묶음 끝([m03])까지 본 것으로",
      len(chunk_calls) == 2 and second.count("\n## ") == 5 and "둘째 묶음 규칙 5번" in second and "둘째 묶음 규칙 6번" not in second
      and st_i5.get("last_run_utc") == stamps[3].timestamp() and "제안 없음" not in dlog
      and "6묶음 중 2묶음만 반영(제안 5개가 차서)" in dlog, (len(chunk_calls), st_i5, dlog[-300:]))
dream.EXCERPT_MAX = saved_max

# I10. 오래 밀린 dream: 7일보다 오래된 발췌는 건너뛰고 수만 기록한다(밀린 묶음이 끝없이 쌓이지 않게)
bc.PROJECTS = T / "projects3"
OLDP = os.path.join(BASE, "old-app")
(bc.PROJECTS / slug(OLDP)).mkdir(parents=True)
d9 = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0) - _dt.timedelta(days=9)
(bc.PROJECTS / slug(OLDP) / f"{uuid.uuid4()}.jsonl").write_text("\n".join([
    line("user", "[old0] 다음부터는 OLDTEXT 이렇게", (d9).strftime(iso), cwd=OLDP),
    line("user", "[old1] 그리고 OLDTEXT 저렇게", (d9 + _dt.timedelta(minutes=1)).strftime(iso), cwd=OLDP),
    line("user", "[new0] 다음부터는 결론부터 써줘", _recent(60), cwd=OLDP)]) + "\n", encoding="utf-8")
stale = bc.PROJECTS / slug(OLDP) / f"{uuid.uuid4()}.jsonl"  # 9일 전에 끝난 기록: 읽지 않는다
stale.write_text(line("user", "[old2] OLDTEXT", d9.strftime(iso), cwd=OLDP) + "\n", encoding="utf-8")
os.utime(stale, (d9.timestamp(), d9.timestamp()))
bc.save_state("dream", {"last_run_utc": time.time() - 10 * 86400})
chunk_calls.clear()
bc.ask_model = lambda system, prompt, **k: (chunk_calls.append(prompt), '{"proposals":[]}')[1]
dream.daily(v)
dlog = (T / "logs" / "brain-dream.log").read_text(encoding="utf-8")
check("I10 7일보다 오래된 발췌는 건너뛰고 수만 기록, 최근 말만 모델에",
      dream.DREAM_MAX_DAYS == 7 and len(chunk_calls) == 1 and "[new0]" in chunk_calls[0] and "OLDTEXT" not in chunk_calls[0]
      and "7일보다 오래된 발췌는 건너뜀 — 사용자 말 2개, 그 전에만 바뀐 기록 1개는 읽지 않음" in dlog and "OLDTEXT" not in dlog
      and bc.load_state("dream")["last_run_utc"] > time.time() - 600, [s for s in dlog.splitlines() if "건너뜀" in s][-1:])
bc.ask_model = fake

# X. Codex 스레드는 일지에만: 합성 state_5.sqlite + rollout(임시 CODEX_HOME). dream 은 보지 않는다.
CX = T / "codex"
(CX / "sessions" / "2026" / "10" / "17").mkdir(parents=True)
check("X0 CODEX_HOME 은 임시 폴더", bc.CODEX_HOME == CX, bc.CODEX_HOME)


def cx(kind, payload, ts="2026-10-17T01:00:00.000Z"):
    return json.dumps({"timestamp": ts, "type": kind, "payload": payload}, ensure_ascii=False)


def cmsg(role, text, ts="2026-10-17T01:00:00.000Z", phase=None, blocks=None):
    p = {"type": "message", "role": role,
         "content": blocks or [{"type": "output_text" if role == "assistant" else "input_text", "text": text}]}
    if phase:
        p["phase"] = phase
    return cx("response_item", p, ts)


MAIN, CLI, NEW = "019a0000-0000-7000-8000-0000000c0de1", "019a0000-0000-7000-8000-0000000c11e1", "019a0000-0000-7000-8000-00000000new1"
crows = [
    cx("session_meta", {"id": MAIN, "cwd": WORK, "source": "vscode", "base_instructions": {"text": "BASEINSTR"}}),
    cx("event_msg", {"type": "task_started", "turn_id": "t1"}),
    cx("turn_context", {"cwd": os.path.join(WORK, "sub"), "approval_policy": "never"}),
    cmsg("developer", "<permissions instructions>PERMTEXT</permissions instructions>"),
    cmsg("user", f"# AGENTS.md instructions for {WORK}\n\n<INSTRUCTIONS>AGENTSTEXT</INSTRUCTIONS>"),
    cmsg("user", f"<environment_context>\n  <cwd>{WORK}</cwd>\n  ENVTEXT\n</environment_context>"),
    cmsg("user", "shop-web 장바구니 합계가 틀려. 원인 찾아서 고쳐줘. " + "자세히 " * 120, "2026-10-17T01:01:00.000Z"),
    cx("event_msg", {"type": "user_message", "message": "shop-web 장바구니 합계가 틀려. DUPUSER"}),
    cx("response_item", {"type": "reasoning", "summary": [{"type": "summary_text", "text": "REASONTEXT"}]}),
    cx("response_item", {"type": "function_call", "name": "shell", "arguments": "{}", "call_id": "c1"}),
    cx("response_item", {"type": "function_call_output", "call_id": "c1", "output": 'TOOLOUT "role":"user"'}),
    cmsg("assistant", "cart.ts 의 sumTotal 을 확인하겠습니다. " + "분석 " * 80, "2026-10-17T01:02:00.000Z", phase="commentary"),
    cx("response_item", {"type": "agent_message", "author": "a", "recipient": "b", "content": [{"type": "text", "text": "AGENTMSG"}]}),
    cmsg("user", "", "2026-10-17T01:05:00.000Z", blocks=[
        {"type": "input_text", "text": "<in-app-browser-context>\nBROWSERCTX\n</in-app-browser-context>\n## My request:\n할인 적용 순서도 확인해줘"},
        {"type": "input_text", "text": "<image name=[Image #1]>"}, {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
        {"type": "input_text", "text": "</image>"}]),
    cmsg("user", "<in-app-browser-context>BROWSER2</in-app-browser-context>\n그리고 PLAINAFTER 도", "2026-10-17T01:05:30.000Z"),
    cmsg("user", "<heartbeat>HEARTBEAT</heartbeat>", "2026-10-17T01:05:40.000Z"),
    cmsg("user", "# Files mentioned by the user:\n\n## cart.ts: src/cart.ts\n\n## My request for Codex:\nFILEREQ 테스트도 추가해줘",
         "2026-10-17T01:06:00.000Z"),
    cmsg("assistant", "sumTotal 에서 할인 전에 세금을 더하던 순서를 고쳤습니다. " + "결과 " * 60, "2026-10-17T01:10:00.123Z", phase="final_answer"),
    cx("event_msg", {"type": "agent_message", "message": "DUPAGENT"}, "2026-10-17T01:10:01.000Z"),
]
main_path = CX / "sessions" / "2026" / "10" / "17" / f"rollout-2026-10-17T10-00-00-{MAIN}.jsonl"
main_path.write_text("\n".join(crows) + "\n", encoding="utf-8")
cli_path = main_path.with_name(f"rollout-2026-10-13T10-00-00-{CLI}.jsonl")
cli_path.write_text("\n".join([cx("session_meta", {"id": CLI, "cwd": SIDE}), cmsg("user", "짧은 질문")]) + "\n", encoding="utf-8")
new_path = main_path.with_name(f"rollout-2026-10-17T11-00-00-{NEW}.jsonl")
shutil.copy(main_path, new_path)

msgs, ctotal, ccwd = bc.read_codex_rollout(main_path)
ctext = "\n".join(m["text"] for m in msgs)
MARKERS = ["BASEINSTR", "PERMTEXT", "AGENTSTEXT", "ENVTEXT", "DUPUSER", "REASONTEXT", "TOOLOUT", "AGENTMSG",
           "BROWSERCTX", "BROWSER2", "HEARTBEAT", "DUPAGENT", "<image", "</image>", "My request"]
check("X1 rollout: 사람 말·Codex 답만(지침·환경 맥락·추론·도구·하위 에이전트·event_msg 중복 제외)",
      [m["role"] for m in msgs] == ["user", "assistant", "user", "user", "user", "assistant"]
      and [m["text"] for m in msgs][2:5] == ["할인 적용 순서도 확인해줘", "그리고 PLAINAFTER 도", "FILEREQ 테스트도 추가해줘"]
      and not [k for k in MARKERS if k in ctext] and ctext.count("장바구니") == 1, [k for k in MARKERS if k in ctext])
check("X1b rollout: 전체 줄 수·cwd(session_meta 우선)·시각", ctotal == len(crows) and ccwd == WORK
      and msgs[-1]["ts"] and f"{msgs[-1]['ts']:%H:%M}" == "10:10", (ctotal, ccwd))
start = next(i for i, r in enumerate(crows, 1) if "할인 적용" in r) - 1
check("X1c rollout: start 줄 뒤만", [m["text"] for m in bc.read_codex_rollout(main_path, start)[0]][:1] == ["할인 적용 순서도 확인해줘"]
      and len(bc.read_codex_rollout(main_path, start)[0]) == 4)
check("X1d Windows 긴 경로 표기 정리", bc._plain_path("\\\\?\\C:\\a\\b") == "C:\\a\\b"
      and bc._plain_path("\\\\?\\UNC\\srv\\share") == "\\\\srv\\share" and bc._plain_path("/home/a") == "/home/a")

ext = (lambda p: "\\\\?\\" + str(p)) if WIN else str  # 실제 DB 처럼 Windows 는 \\?\ 붙은 경로
now_s = int(time.time())


def trow(tid, source, cwd, age_h, role=None, path=main_path):
    at = now_s - int(age_h * 3600)
    return (tid, ext(path), at - 60, at, at * 1000, source, ext(cwd), "t", role, 0, 1)


con = sqlite3.connect(str(CX / "state_5.sqlite"))
con.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, created_at INTEGER, updated_at INTEGER, "
            "updated_at_ms INTEGER, source TEXT, cwd TEXT, title TEXT, agent_role TEXT, archived INTEGER, has_user_event INTEGER)")
con.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
    trow(MAIN, "vscode", WORK, 2),
    trow(CLI, "cli", SIDE, 6 * 24, role="", path=cli_path),  # 금요일 세션 → 월요일 따라잡기(7일 안)
    trow("exec-1", "exec", WORK, 1),
    trow("sub-1", '{"subagent":{"other":"guardian"}}', WORK, 1),
    trow("role-1", "vscode", WORK, 1, role="worker"),
    trow("old-1", "vscode", WORK, 10 * 24),
    trow("scratch-1", "vscode", os.path.join(BASE, "scratchpad", "x"), 1),
    trow("private-1", "vscode", PRIVATE, 1),
    trow("temp-1", "vscode", os.path.join(tempfile.gettempdir(), "codex-tmp"), 1)])
con.commit()
con.close()
for p_, age in ((main_path, 2 * 3600), (cli_path, 6 * 86400)):
    os.utime(p_, (now_s - age, now_s - age))
bc.CFG["journal_exclude"] = [PRIVATE]
picked = bc.codex_threads(time.time() - dream.CATCHUP_DAYS * 86400)
check("X2 스레드 고르기: vscode·cli 사람 스레드만, 7일 안, scratch·임시·제외 폴더 뺌",
      dream.CATCHUP_DAYS == 7 and sorted(t["id"] for t in picked) == sorted([MAIN, CLI]), [t["id"] for t in picked])
check("X2b DB 의 \\\\?\\ 경로는 보통 경로로", all(t["cwd"] in (WORK, SIDE) and Path(t["path"]).exists() for t in picked),
      [t["cwd"] for t in picked])

dream.catchup()
qmain = bc.queue_file(f"codex:{MAIN}")
qitem = json.loads(qmain.read_text(encoding="utf-8")) if qmain.exists() else {}
check("X3 따라잡기: codex:<id> 키·source codex 로 대기열(파일 이름에 ':' 없음)",
      qitem.get("source") == "codex" and qitem.get("session_id") == f"codex:{MAIN}" and ":" not in qmain.name
      and qitem.get("cwd") == WORK and bc.queue_file(f"codex:{CLI}").exists(), (qmain.name, qitem))
n_before = len(calls)
bc.drain_queue("journal")
cjp = bc.journal_path(v, "2026-10-17")
ctxt = cjp.read_text(encoding="utf-8") if cjp.exists() else ""
check("X4 일지 줄 [codex·<폴더>]", "- 10:10 [codex·shop-web] " in ctxt and len(calls) == n_before + 1, ctxt[-200:])
jst = bc.load_state("journal")
check("X5 상태 키는 codex:<id>(Claude 세션 id 와 안 겹침)", jst.get(f"codex:{MAIN}", {}).get("done") == len(crows)
      and MAIN not in jst and "size" in jst.get(f"codex:{CLI}", {}), {k: v_ for k, v_ in jst.items() if "codex" in k})
cprompt = calls[-1][2]
check("X6 요약 입력: Codex 답 표기·사람 말만, 끼워 넣은 맥락 없음",
      "Codex: " in cprompt and "할인 적용 순서도" in cprompt and "FILEREQ" in cprompt and "프로젝트 폴더: shop-web" in cprompt
      and not [k for k in MARKERS if k in cprompt], [k for k in MARKERS if k in cprompt])
dream.catchup()
check("X7 바뀌지 않은 스레드는 다시 넣지 않음", not bc.queue_items())

con = sqlite3.connect(str(CX / "state_5.sqlite"))
con.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?)", trow(NEW, "vscode", WORK, 1, path=new_path))
con.commit()
con.close()
os.utime(new_path, (now_s - 3600, now_s - 3600))
bc.CFG["journal_sources"] = ["claude"]
dream.catchup()
n_before = len(calls)
r_off = bc.journal_one(v, {"session_id": f"codex:{NEW}", "transcript_path": str(new_path), "source": "codex"}, {})
check("X8 journal_sources 에 codex 가 없으면 넣지도 요약하지도 않음",
      not bc.queue_items() and r_off == "건너뜀(journal_sources 에 없음)" and len(calls) == n_before, r_off)
bc.CFG.pop("journal_sources")
dream.catchup()
check("X8b 기본값(claude·codex)이면 다시 들어감", bc.queue_file(f"codex:{NEW}").exists())
bc.drain_queue("journal")
bc.CFG.pop("journal_exclude")

saved_home = bc.CODEX_HOME
bc.CODEX_HOME = T / "no-codex"
none_ok = bc.codex_threads(0) == []
bc.CODEX_HOME = T / "codex-empty"
bc.CODEX_HOME.mkdir()
empty_ok = bc.codex_threads(0) == []
bc.CODEX_HOME = T / "codex-bad"
bc.CODEX_HOME.mkdir()
con = sqlite3.connect(str(bc.CODEX_HOME / "state_5.sqlite"))
con.execute("CREATE TABLE threads (id TEXT)")
con.commit()
con.close()
bad_ok = bc.codex_threads(0) == []
bc.CODEX_HOME = saved_home
dlog = (T / "logs" / "brain-dream.log").read_text(encoding="utf-8")
check("X9 Codex 없음·DB 없음·표 모양 다름은 조용히 건너뜀(기록만)", none_ok and empty_ok and bad_ok
      and "Codex 상태 DB 없음" in dlog and "Codex 상태 DB 를 읽지 못함" in dlog, (none_ok, empty_ok, bad_ok))
if WIN:  # X9b. CODEX_HOME 이 \\?\ 긴 경로나 UNC 경로여도 같은 DB 를 읽는다(UNC 는 관리 공유가 열린 PC 에서만)
    want = sorted(t["id"] for t in bc.codex_threads(0))
    homes = {"긴 경로": Path("\\\\?\\" + str(CX))}
    unc = Path(f"\\\\localhost\\{str(CX)[0]}$" + str(CX)[2:])
    try:
        if unc.is_dir():
            homes["UNC"] = unc
            homes["긴 UNC"] = Path(f"\\\\?\\UNC\\localhost\\{str(CX)[0]}$" + str(CX)[2:])
    except OSError:
        pass
    got = {}
    for name_, home in homes.items():
        bc.CODEX_HOME = home
        got[name_] = sorted(t["id"] for t in bc.codex_threads(0))
    bc.CODEX_HOME = saved_home
    check("X9b \\\\?\\·UNC CODEX_HOME 도 같은 스레드를 읽음", want and all(g == want for g in got.values()),
          {k: len(g) for k, g in got.items()})
crow_all = dream.collect(0)[0]
check("X10 dream 발췌는 Claude Code 기록만(Codex 대화 없음)", crow_all and not any("장바구니" in r[2] or "FILEREQ" in r[2] for r in crow_all))

# X11. Codex 가 끼워 넣은 맥락 블록만 빼고, 사용자가 친 HTML·맥락 뒤 요청은 남긴다
cut = bc.codex_user_text
TEMPLATE = "<template>\n  <div>{{ total }}</div>\n</template> 이 컴포넌트 고쳐줘"
SVG = "<image href='a.png'/> 이 SVG 이미지가 안 보여"
check("X11 사용자 HTML(<template>·<b>·SVG <image>)은 그대로", cut(TEMPLATE) == TEMPLATE and cut("<b>굵게</b> 이건 왜") == "<b>굵게</b> 이건 왜"
      and cut(SVG) == SVG, (cut(TEMPLATE), cut("<b>굵게</b> 이건 왜"), cut(SVG)))
check("X11b 맥락 블록 뒤에 이어 친 요청은 남김",
      cut(f"<environment_context>\n  <cwd>{WORK}</cwd>\n</environment_context>\n실제 요청 고쳐줘") == "실제 요청 고쳐줘"
      and cut("<permissions instructions>P</permissions instructions>\n<skill>\n<name>s</name>\n본문\n</skill>\n두 번째 요청")
      == "두 번째 요청", cut(f"<environment_context><cwd>{WORK}</cwd></environment_context>\n실제 요청 고쳐줘"))
ONLY_CTX = [
    f"# AGENTS.md instructions for {WORK}\n\n<INSTRUCTIONS>\nA\n</INSTRUCTIONS>\n<environment_context>e</environment_context>",
    "<turn_aborted>\nThe user interrupted.\n</turn_aborted>", "<external_codex_apps_open_page>x</external_codex_apps_open_page>",
    "<codex_internal_context><objective>o</objective></codex_internal_context>", "<environment_context>\n  <cwd>잘림",
    "<image name=[Image #2] path=x.png>", "</image>"]
check("X11c 맥락만 있는 메시지·닫히지 않은 맥락·이미지 자리 표시는 빈 글", all(cut(t) == "" for t in ONLY_CTX),
      [cut(t)[:30] for t in ONLY_CTX if cut(t)])
check("X11d 맥락 태그 이름은 이름 붙은 튜플 상수", isinstance(bc.CODEX_CONTEXT_TAGS, tuple)
      and {"environment_context", "user_instructions", "permissions", "in-app-browser-context", "heartbeat"} <= set(bc.CODEX_CONTEXT_TAGS))
# X11e. ! 셸 명령 출력·하위 에이전트 결과·/review 결과, 목록에 없는 <이름_이름> 통 블록도 맥락으로 뺀다
SHELL = ("<user_shell_command>\n<command>\ntype .env.local\n</command>\n<result>\nExit code: 0\nOutput:\n"
         "SHELLOUT=1\n## My request:\nSHELLTAIL\n</result>\n</user_shell_command>")
INJECTED = [SHELL, '<subagent_notification>{"agent":"a","status":"SUBOUT"}</subagent_notification>',
            "<user_action>\n  <context>User initiated a review task.</context>\n  <results>REVIEWOUT</results>\n</user_action>",
            "<future_context_block>\nFUTUREOUT\n</future_context_block>"]
check("X11e 셸·하위 에이전트·리뷰·새 맥락 통 블록은 빈 글, 셸 블록 뒤 요청과 사용자 HTML 은 남김",
      all(cut(t) == "" for t in INJECTED) and cut(SHELL + "\n이 결과 보고 고쳐줘") == "이 결과 보고 고쳐줘"
      and cut("<div>\n  <span>합계</span>\n</div>") == "<div>\n  <span>합계</span>\n</div>",
      [cut(t)[:30] for t in INJECTED if cut(t)])

# Y. 깨진 줄이 섞인 기록도 읽기를 멈추지 않는다(dict 가 아닌 JSON 줄, 글자열이 아닌 text)
BAD = "019a0000-0000-7000-8000-0000000bad01"
bad_path = CX / "sessions" / "2026" / "10" / "17" / f"rollout-2026-10-17T12-00-00-{BAD}.jsonl"
bad_rows = [
    cx("session_meta", {"id": BAD, "cwd": WORK}),
    '"role"', '["role", 1]', '[{"role": "user"}]', '["session_meta", "role"]', "null",
    json.dumps({"type": "response_item", "payload": ["role", "user"]}),
    cmsg("user", "", blocks=[{"type": "input_text", "text": {"role": "x"}}]),
    cmsg("user", "", "2026-10-17T03:00:00.000Z", blocks=[{"type": "input_text", "text": ["role"]},
                                                         {"type": "input_text", "text": "쿠폰 계산을 고쳐줘 " + "자세히 " * 150}]),
    cmsg("assistant", "", blocks=[{"type": "output_text", "text": 123}]),
    cx("response_item", {"type": "message", "role": "assistant", "content": "role 글자열 content"}),
    cmsg("assistant", "coupon.ts 의 계산 순서를 고쳤습니다. " + "결과 " * 80, "2026-10-17T03:05:00.000Z"),
]
bad_path.write_text("\n".join(bad_rows) + "\n", encoding="utf-8")
try:
    bmsgs, btotal, bcwd = bc.read_codex_rollout(bad_path)
    bad_err = None
except Exception as e:  # noqa: BLE001
    bmsgs, btotal, bcwd, bad_err = [], 0, None, e
check("Y1 Codex rollout 깨진 줄은 건너뜀(예외 없음)", bad_err is None and [m["role"] for m in bmsgs] == ["user", "assistant"]
      and bmsgs[0]["text"].startswith("쿠폰 계산을") and btotal == len(bad_rows) and bcwd == WORK, bad_err)
bc.enqueue(f"codex:{BAD}", bad_path, WORK, "test", source="codex")
bc.drain_queue("journal")
check("Y2 깨진 줄이 섞인 Codex 스레드도 한 번에 기록", not bc.queue_items()
      and bc.load_state("journal").get(f"codex:{BAD}", {}).get("done") == len(bad_rows)
      and "- 12:05 [codex·shop-web] " in bc.journal_path(v, "2026-10-17").read_text(encoding="utf-8"))
yid = str(uuid.uuid4())
yp = T / "proj" / f"{yid}.jsonl"
ybad = [
    '[{"type":"user","message":{"content":"목록 줄"}}]',  # 첫 user 줄이 목록(예약 작업 판정도 지나감)
    '{"cwd":"C:\\q","type":"user","message":{"content":"잘못된 escape"}}',
    json.dumps({"type": "user", "message": "글자열 message", "timestamp": "2026-10-16T06:00:00Z"}),
    json.dumps({"type": "user", "origin": "이상한 origin", "message": {"content": "origin 글자열"}}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": {"a": 1}}]}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": None}, {"type": "text", "text": ["x"]}]}}),
    line("user", "결제 화면 버튼이 안 눌려. 고쳐줘 " + "자세히 " * 150, "2026-10-16T06:01:00Z"),
    line("assistant", "pay.vue 의 disabled 조건을 고쳤습니다. " + "결과 " * 80, "2026-10-16T06:05:00Z"),
]
yp.write_text("\n".join(ybad) + "\n", encoding="utf-8")
try:
    ymsgs, ytotal, ycwd = bc.read_transcript(yp)
    yreason, y_err = bc.skip_reason(yp, ycwd), None
except Exception as e:  # noqa: BLE001
    ymsgs, ytotal, yreason, y_err = [], 0, None, e
check("Y3 Claude 기록 깨진 줄도 건너뜀(목록 줄·잘못된 escape·글자열 message·dict text)", y_err is None
      and [m["role"] for m in ymsgs] == ["user", "assistant"] and ymsgs[0]["text"].startswith("결제 화면")
      and ymsgs[1]["text"].startswith("pay.vue") and ytotal == len(ybad) and yreason is None, y_err or [m["text"][:20] for m in ymsgs])
bc.enqueue(yid, yp, None, "test")
bc.drain_queue("journal")
check("Y3b 깨진 줄이 섞인 Claude 세션도 한 번에 기록", not bc.queue_items() and bc.load_state("journal")[yid]["done"] == len(ybad))

# Y4. 계속 실패하는 스레드는 3번 뒤 크기를 적어 둬서 따라잡기가 1시간마다 다시 넣지 않는다(기록이 늘면 다시 봄)
FAIL = "019a0000-0000-7000-8000-0000000fa110"
fail_path = bad_path.with_name(f"rollout-2026-10-17T13-00-00-{FAIL}.jsonl")
shutil.copy(main_path, fail_path)
os.utime(fail_path, (now_s - 7200, now_s - 7200))
con = sqlite3.connect(str(CX / "state_5.sqlite"))
con.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?)", trow(FAIL, "vscode", WORK, 1, path=fail_path))
con.commit()
con.close()
saved_projects, bc.PROJECTS = bc.PROJECTS, T / "projects-empty"
real_rollout = bc.read_codex_rollout
bc.read_codex_rollout = lambda *a, **k: (_ for _ in ()).throw(TypeError("깨진 rollout"))
dream.catchup()
queued_first = bc.queue_file(f"codex:{FAIL}").exists()
for _ in range(3):
    bc.drain_queue("journal")
fst = bc.load_state("journal").get(f"codex:{FAIL}", {})
dream.catchup()
check("Y4 3번 실패한 스레드: 대기열에서 빼고 크기 기록 → 따라잡기가 다시 넣지 않음",
      queued_first and not bc.queue_items() and fst.get("size") == fail_path.stat().st_size and fst.get("done", 0) == 0,
      (queued_first, fst, [p.name for p in bc.queue_items()]))
with open(fail_path, "a", encoding="utf-8") as f:
    f.write(cmsg("user", "한 줄 더") + "\n")
os.utime(fail_path, (now_s - 7200, now_s - 7200))
dream.catchup()
check("Y4b 기록이 늘면 다시 대기열에", bc.queue_file(f"codex:{FAIL}").exists())
bc.read_codex_rollout = real_rollout
bc.drain_queue("journal")

# Z. Codex 수집이 터져도(폴더 권한 등) Claude 따라잡기·대기열·색인은 돈다
os.environ.pop("DREAM_FORCE", None)
bc.PROJECTS = T / "projects4"
ZP = os.path.join(BASE, "z-app")
(bc.PROJECTS / slug(ZP)).mkdir(parents=True)
zid = str(uuid.uuid4())
zp = bc.PROJECTS / slug(ZP) / f"{zid}.jsonl"
zp.write_text("\n".join([line("user", "재고 화면 정렬을 고쳐줘 " + "자세히 " * 150, _recent(120), cwd=ZP),
                         line("assistant", "stock.ts 정렬 기준을 고쳤습니다. " + "결과 " * 80, _recent(115), cwd=ZP)]) + "\n",
              encoding="utf-8")
os.utime(zp, (now_s - 3600, now_s - 3600))
bc.save_state("dream", {"last_run_date": bc.now().date().isoformat(), "last_attempt": time.time(), "last_catchup": 0})
real_threads, real_sb = bc.codex_threads, bc.run_sb
sb_calls = []
bc.codex_threads = lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "액세스 거부", str(CX)))
bc.run_sb = lambda *a, **k: sb_calls.append(a)
log_before = len((T / "logs" / "brain-dream.log").read_text(encoding="utf-8").splitlines())
dream.worker()
new_log = (T / "logs" / "brain-dream.log").read_text(encoding="utf-8").splitlines()[log_before:]
check("Z1 Codex 수집 예외: 한 줄 기록하고 Claude 따라잡기·대기열·색인은 계속",
      sum("Codex 따라잡기 건너뜀: PermissionError" in s for s in new_log) == 1
      and bc.load_state("journal").get(zid, {}).get("done") == 2 and sb_calls == [("index", "--quiet")]
      and bc.load_state("dream").get("last_catchup", 0) > 0, new_log)
bc.codex_threads = real_threads
real_catchup = dream.catchup
dream.catchup = lambda: (_ for _ in ()).throw(RuntimeError("따라잡기 고장"))
bc.save_state("dream", {"last_run_date": bc.now().date().isoformat(), "last_attempt": time.time(), "last_catchup": 0})
zid2 = str(uuid.uuid4())
shutil.copy(zp, zp.with_name(f"{zid2}.jsonl"))
bc.enqueue(zid2, zp.with_name(f"{zid2}.jsonl"), ZP, "test")
sb_calls.clear()
dream.worker()
check("Z2 따라잡기 자체가 터져도 대기열·색인은 계속", bc.load_state("journal").get(zid2, {}).get("done") == 2
      and sb_calls == [("index", "--quiet")] and "따라잡기 오류: RuntimeError" in (T / "logs" / "brain-dream.log").read_text(encoding="utf-8"))
dream.catchup, bc.run_sb, bc.PROJECTS = real_catchup, real_sb, saved_projects

# K. 따라잡기: 수정 시각만 바뀐 오래된 대화(마지막 말이 7일 넘음)는 소급하지 않는다. SessionEnd 항목은 그대로 남긴다
old_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
kp = T / "proj-old" / f"{uuid.uuid4()}.jsonl"
kp.parent.mkdir(parents=True, exist_ok=True)
kp.write_text(line("user", "주문 상세 화면 고쳐줘 " + "가" * 700, old_ts) + "\n"
              + line("assistant", "고쳤다 " + "나" * 700, old_ts) + "\n", encoding="utf-8")
st_k, n_calls = {}, len(calls)
r_old = bc.journal_one(v, {"session_id": "k-old", "transcript_path": str(kp), "cwd": WORK, "reason": "catch-up"}, st_k)
check("K1 따라잡기: 마지막 말이 7일 넘으면 요약하지 않고 크기를 적어 다시 넣지 않음",
      r_old.startswith("건너뜀(마지막 대화") and len(calls) == n_calls
      and st_k["k-old"].get("done", 0) > 0 and st_k["k-old"].get("size") == kp.stat().st_size, r_old)
r_end = bc.journal_one(v, {"session_id": "k-end", "transcript_path": str(kp), "cwd": WORK, "reason": "session-end"}, {})
check("K2 SessionEnd 항목은 마지막 말이 오래돼도 남김", r_end.startswith("기록:"), r_end)

# G. 재귀 방지
for name in ("brain-journal", "brain-dream", "brain-lint-reminder"):
    r = subprocess.run([sys.executable, str(HOOKS / f"{name}.py")], input=b'{"session_id":"x","transcript_path":"y"}',
                       capture_output=True, env=dict(os.environ, BRAIN_JOURNAL="1"))
    check(f"G {name}: BRAIN_JOURNAL=1 이면 바로 끝", r.returncode == 0 and not r.stdout)

# H. sb lint 로 hook 이 만든 파일 형식 확인
r = subprocess.run([sys.executable, str(SB), "lint", str(jp), *map(str, files)], capture_output=True,
                   env=dict(os.environ, SECOND_BRAIN=str(v)))
lint_out = r.stdout.decode("utf-8")
check("H1 sb lint: 일지·dream 파일 문제 0건", "문제 0건" in lint_out, lint_out.strip().splitlines()[-1] if lint_out else r.stderr[:200])

print("\n== 일지 ==\n" + jp.read_text(encoding="utf-8"))
print("== dream 제안 ==\n" + body)
print(f"합계: {sum(ok for _, ok in results)}/{len(results)} 통과")
if not os.environ.get("BRAIN_TEST_KEEP"):
    shutil.rmtree(T, ignore_errors=True)
else:
    print(f"임시 폴더: {T}")
sys.exit(0 if all(ok for _, ok in results) else 1)
