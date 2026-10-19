"""brain hook 시나리오 — 가짜 모델로 일지·dream·리마인더 흐름을 임시 볼트·임시 상태·임시 로그 폴더에서 끝까지 돌린다.

실제 볼트·~/.second-brain·~/.claude 는 읽지도 쓰지도 않는다(CLAUDE_CONFIG_DIR·SECOND_BRAIN_HOME 을 임시 폴더로 바꾼다).
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
import subprocess
import sys
import tempfile
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
                  CLAUDE_CONFIG_DIR=str(T / "claude"), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
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
real.subprocess.run = real_run
check("D4 401 이 든 정상 요약은 통과, 진짜 로그인 실패는 AuthError, 연결 오류·시간 초과는 TransientError",
      ok401 and auth_raised and trans and trans2, (ok401, auth_raised, trans, trans2))
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
    "- [ ] [A1] [[x]] — 문제\n- [x] [A2] [[y]] — 문제 → 결정: 닫기 (2026-10-19)\n- [ ] [A3] [[z]] — 문제\n\n"
    "## 웹으로 채울 빈칸\n- 조사 항목\n\n## 처리 결과\n- [ ] 이 줄은 세지 않는다\n", encoding="utf-8")
bc.save_state("remind", {})
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True,
                     env=dict(os.environ)).stdout.decode("utf-8")
check("F10 알림: 점검 결과 결정 대기 2건(결정 대기 절만 셈)", "점검 결과 결정 대기가 2건" in out, out[:160])
# F11. 7일 점검 권유(이 볼트는 lint 기록이 없다)에 앞선 점검 결과를 먼저 처리하라는 안내가 붙는다
check("F11 7일 점검 권유에 앞선 결과 먼저 처리 안내", "점검(lint)을 한 번도 하지 않았다" in out and "결정 대기 2건을 /inbox 로 먼저" in out)
out = subprocess.run([sys.executable, str(HOOKS / "brain-lint-reminder.py")], input=b"{}", capture_output=True,
                     env=dict(os.environ)).stdout.decode("utf-8")
check("F11b 같은 날 두 번째 세션은 다시 알리지 않음", "점검 결과 결정 대기" not in out and "점검(lint)" not in out, out[:160])

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
