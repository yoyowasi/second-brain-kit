"""SessionStart hook — stdout 은 세션 맥락에 들어간다. 필요할 때만 `[brain] ...` 안내 줄을 낸다(종류마다 하루 한 번).

- 인박스에 dream 제안(type: dream)이 있으면 /inbox 를 권한다.
- 99_System/브레인 로그.md 의 마지막 lint 가 7일을 넘었으면(한 번도 없었으면 포함) 점검을 권한다.
- 요약용 claude CLI 로그인이 풀려 일지·dream 이 멈춰 있거나, 대기열이 2일 넘게 막혀 있으면 알린다.
무인 세션(CLAUDE_CODE_SESSION_ATTENDED=0 — 헤드리스, CLAUDE_CODE_HOST_SCHEDULED_RUN=1 — 데스크톱 예약 작업)에서는
아무것도 내지 않고 '하루 한 번' 표시도 쓰지 않는다(아침 루틴이 사용자 몫의 알림을 먼저 써 버리지 않게).
"""
import os
import sys

if os.environ.get("BRAIN_JOURNAL"):
    sys.exit(0)

import datetime as dt  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402

import brain_common as bc  # noqa: E402

NAME = "lint-reminder"
LOG_NOTE = ("99_System", "브레인 로그.md")


def dream_files(v):
    found = []
    for p in sorted((v / "00_Inbox").glob("*.md")):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:300]
        except OSError:
            continue
        if re.search(r"^type:\s*dream\s*$", head, re.M):
            found.append(p.stem)
    return found


def last_lint(v):
    try:
        text = (v.joinpath(*LOG_NOTE)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    dates = re.findall(r"^## \[(\d{4}-\d{2}-\d{2})\] lint\b", text, re.M)
    return dt.date.fromisoformat(max(dates)) if dates else None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except (OSError, ValueError):
        data = {}
    attended = os.environ.get("CLAUDE_CODE_SESSION_ATTENDED")
    scheduled = os.environ.get("CLAUDE_CODE_HOST_SCHEDULED_RUN")
    if attended == "0" or scheduled == "1":
        bc.log(NAME, f"무인 세션 — 안내 없음 (attended={attended} scheduled={scheduled} source={data.get('source')})")
        return
    v = bc.vault()
    if not v:
        return
    today = bc.now().date()
    shown = bc.load_state("remind")
    lines = []

    dreams = dream_files(v)
    if dreams and shown.get("dream") != today.isoformat():
        lines.append(f'[brain] 인박스에 dream 규칙 제안 파일 {len(dreams)}개가 승인을 기다린다({", ".join(dreams[:3])}). '
                     f'첫 답 끝에 "dream 규칙 제안이 {len(dreams)}건 있습니다. /inbox 로 볼까요?" 를 한 줄로 제안할 것.')
        shown["dream"] = today.isoformat()

    last = last_lint(v)
    if (last is None or (today - last).days > 7) and shown.get("lint") != today.isoformat():
        since = "한 번도 하지 않았다" if last is None else f"마지막 점검 {last} ({(today - last).days}일 전)"
        lines.append(f'[brain] 세컨드 브레인 점검(lint)을 {since}. '
                     f'첫 답 끝에 "세컨드 브레인 점검을 할까요?" 를 한 줄로 제안할 것.')
        shown["lint"] = today.isoformat()

    auth = bc.load_state("auth")
    pending = len(bc.queue_items())
    if auth.get("failed_at") and shown.get("auth") != today.isoformat():
        lines.append(f'[brain] 세션 일지·dream 요약용 claude CLI 로그인이 풀려 있어(대기 {pending}건) 자동 기록이 멈춰 있다. '
                     f'첫 답 끝에 "터미널에서 claude auth login 을 한 번 해 주시면 세션 일지와 dream 이 다시 쌓입니다." 를 한 줄로 알릴 것.')
        shown["auth"] = today.isoformat()
    elif pending and bc.oldest_queue_age_days() >= 2 and shown.get("stuck") != today.isoformat():
        lines.append(f'[brain] 세션 일지 대기열 {pending}건이 2일 넘게 처리되지 않았다. '
                     f'첫 답 끝에 "세션 일지 요약이 멈춰 있습니다. ~/.claude/hooks/brain-journal.log 를 확인할까요?" 를 한 줄로 제안할 것.')
        shown["stuck"] = today.isoformat()

    if lines:
        print("\n".join(lines))
        bc.save_state("remind", shown)
        bc.log(NAME, f"안내 {len(lines)}줄 (attended={attended} scheduled={scheduled} source={data.get('source')})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — hook 실패가 세션 시작을 방해하지 않게
        bc.log(NAME, f"오류: {type(e).__name__}: {e}")
    sys.exit(0)
