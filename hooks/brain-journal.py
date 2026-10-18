"""SessionEnd hook — 끝난 세션에서 한 일을 haiku 로 한 줄 요약해 볼트 10_Daily/Journal/<날짜> 세션.md 에 남긴다.

hook 자체는 입력을 대기열(~/.second-brain/state/queue/)에 넣고 떼어 낸 프로세스를 띄운 뒤 바로 끝난다
(SessionEnd 는 기본 1.5초 안에 끝나야 한다). 요약은 `--worker` 프로세스가 잠금 안에서 한다.
세션마다 요약한 줄 수를 상태에 남겨, 이어서 연 세션은 늘어난 부분만 본다.
시험: BRAIN_SYNC=1 이면 떼어 내지 않고 끝까지 기다린다.
"""
import os
import sys

if os.environ.get("BRAIN_JOURNAL"):
    sys.exit(0)

import json  # noqa: E402

import brain_common as bc  # noqa: E402

NAME = "journal"


def worker():
    import time
    time.sleep(3)  # transcript 는 비동기로 기록된다. 마지막 메시지가 파일에 닿을 시간을 준다.
    try:
        with bc.Lock():
            bc.drain_queue(NAME)
    except TimeoutError as e:
        bc.log(NAME, f"{e} — 대기열에 남겨 다음 실행이 처리")


def main():
    if sys.argv[1:2] == ["--worker"]:
        worker()
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError as e:
        bc.log(NAME, f"입력 JSON 오류: {e}")
        return
    if not bc.enqueue(data.get("session_id"), data.get("transcript_path"), data.get("cwd"), data.get("reason")):
        bc.log(NAME, "session_id·transcript_path 없음 — 건너뜀")
        return
    if os.environ.get("BRAIN_SYNC"):
        worker()
    else:
        bc.spawn_background(__file__, "--worker")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — hook 실패가 세션 종료를 방해하지 않게
        bc.log(NAME, f"오류: {type(e).__name__}: {e}")
    sys.exit(0)
