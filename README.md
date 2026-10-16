# 세컨드 브레인 키트

> Build an Obsidian second brain (PARA + permanent notes) from scratch, and let AI agents like Claude Code and Codex read and write it through a `second-brain` skill.

세컨드 브레인이 아예 없는 사람도 이 저장소를 따라 하면 Obsidian 볼트(노트 폴더)를 만들고, Claude Code나 Codex 같은 AI 에이전트에게 "메모해 둬", "주간 리뷰 해줘", "전에 이거 해결한 적 있나"처럼 말로 부탁해 그 볼트를 읽고 쓰게 할 수 있다. 볼트는 내 컴퓨터에 있는 평범한 Markdown 파일이라 앱이나 서비스에 묶이지 않는다. 키트는 세 부분으로 되어 있다. 바로 쓸 수 있는 스타터 볼트, AI가 볼트 규칙을 지키며 일하게 하는 `second-brain` 스킬, 날짜 계산·템플릿 채우기·점검을 맡는 보조 도구 `sb.py`다. Claude Code에는 세션마다 한 줄 일지를 남기고 대화에서 작업 규칙 제안(dream)을 골라 주는 [자동 기록](#자동-기록-claude-code)도 함께 설치된다.

## 이런 분께

- 메모가 여기저기 흩어져 있어 필요할 때 다시 찾지 못하는 분
- 일하다 해결한 문제를 기록해 두었다가 다음에 같은 문제를 만나면 바로 꺼내 쓰고 싶은 분
- Obsidian을 처음 쓰거나, 폴더를 어떻게 나눌지 정하지 못해 시작을 미루고 있는 분
- AI 에이전트가 내 노트를 근거로 답하고, 정리도 대신 해 주기를 바라는 분

## 흐름: 적고 → 분류하고 → 연결하고 → 다시 쓴다

| 단계 | 하는 일 | 이 키트에서는 |
|---|---|---|
| 적는다 | 떠오른 것을 분류하지 않고 일단 적는다 | `00_Inbox/`, 오늘 일일 노트 |
| 분류한다 | 끝나는 일인지, 계속 관리할 일인지, 자료인지, 내 생각인지 나눈다 | "인박스 정리해줘" → PARA 폴더로 이동 |
| 연결한다 | 관련 노트를 `[[노트 이름]]`으로 잇는다 | 새 노트는 적어도 하나의 기존 노트에 연결 |
| 다시 쓴다 | 기록을 근거로 답하고, 생각을 영구 노트로 다듬는다 | "볼트 기준으로 ○○ 알려줘", "노트 정제해줘" |

## 빠른 시작

**A. 세컨드 브레인이 아직 없다** → [docs/세컨드-브레인-만들기.md](docs/세컨드-브레인-만들기.md)를 처음부터 따라 한다. 준비물 설치, 볼트 만들기, Obsidian 설정, 첫날 해 볼 것까지 순서대로 안내한다.

**B. 이미 Obsidian 볼트가 있다**

1. 아래 [설치](#설치)로 스킬을 설치한다.
2. AI에게 "기존 볼트 연결해줘"라고 하거나 직접 경로를 저장한다. 경로는 내 볼트 폴더로 바꾼다.

   ```powershell
   # Windows (PowerShell) — $HOME은 내 사용자 폴더(C:\Users\<사용자>)다
   python "$HOME\.claude\skills\second-brain\scripts\sb.py" setup "$HOME\Documents\SecondBrain"
   ```

   ```bash
   # macOS / Linux (Windows Git Bash에서는 python3 대신 python)
   python3 ~/.claude/skills/second-brain/scripts/sb.py setup ~/Documents/SecondBrain
   ```

   `볼트 경로를 저장했습니다: <경로>`가 나오면 경로가 `~/.second-brain/config.json`에 저장된 것이다. `setup`은 볼트의 노트를 바꾸지 않는다.
3. `setup`이 `주의:`로 알려 주는 것을 채운다.
   - `AGENTS.md(볼트 규칙)가 없습니다. <스타터 AGENTS.md 경로> 를 참고해 만들어 두세요.`: 메시지에 나온 파일(스타터 볼트의 [AGENTS.md](skills/second-brain/assets/starter-vault/AGENTS.md))을 볼트 맨 위에 넣고 내 볼트의 폴더 이름과 규칙에 맞게 고친다. 폴더 이름이 다르면 `sb.py` 설정에서도 바꾼다([docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#개인-설정-localmd와-configjson)).
   - `템플릿이 없어 'sb new daily' 등이 실패합니다`: 템플릿이 없으면 첫 요청인 "오늘 노트 만들어줘"부터 `템플릿이 없습니다` 오류로 멈춘다. **Obsidian을 닫은 상태에서** 아래 명령으로 스타터 템플릿을 볼트의 `99_System/Templates/`로 복사한다. 폴더가 없으면 만들고, 볼트에 이미 있는 같은 이름의 템플릿은 덮어쓰지 않는다. `$vault`(bash는 `vault`)는 내 볼트 폴더로 바꾼다. 복사한 뒤 Obsidian을 열고 Templater 설정의 템플릿 폴더를 `99_System/Templates`로 정한다.

     ```powershell
     # Windows (PowerShell) — Obsidian을 닫고 실행한다
     $vault = "$HOME\Documents\SecondBrain"
     $src = "$HOME\.claude\skills\second-brain\assets\starter-vault\99_System\Templates"
     New-Item -ItemType Directory -Force "$vault\99_System\Templates" | Out-Null
     Get-ChildItem "$src\*.md" | ForEach-Object {
       $dst = "$vault\99_System\Templates\$($_.Name)"
       if (-not (Test-Path $dst)) { Copy-Item $_.FullName $dst }   # 이미 있으면 건너뛴다
     }
     ```

     ```bash
     # macOS / Linux / Windows Git Bash — Obsidian을 닫고 실행한다
     vault="$HOME/Documents/SecondBrain"
     src="$HOME/.claude/skills/second-brain/assets/starter-vault/99_System/Templates"
     mkdir -p "$vault/99_System/Templates"
     for f in "$src"/*.md; do
       dst="$vault/99_System/Templates/${f##*/}"
       [ -e "$dst" ] || cp "$f" "$dst"   # 이미 있으면 건너뛴다
     done
     ```

   - `환경변수 SECOND_BRAIN(...)이 설정되어 있어 그쪽 볼트가 계속 쓰입니다`: 저장한 경로보다 환경변수가 우선한다. 이 볼트를 쓰려면 환경변수를 지운다([docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#환경변수-second_brain)).
4. (선택) AI가 판단이 애매할 때 기본값으로 쓰는 `나의 판단 방식.md`를 설치된 스킬의 `assets/starter-vault/30_Areas/`에서 볼트의 `30_Areas/`로 복사한다(볼트에 같은 이름의 노트가 있으면 복사하지 않는다). 이 노트 끝의 `[[업무]] · [[학습]] · [[건강]] · [[재무]]`는 내 영역 노트 이름으로 고친다.
5. 첫 점검(`sb.py lint`)에서 문제가 많이 나와도 고장이 아니다. 기존 노트는 이 키트의 노트 형식(frontmatter의 `type`·`created`, 첫 제목 = 파일 이름)을 따르지 않으므로 노트마다 `frontmatter 없음`, `type 값 이상: ''`, `created 형식 이상: ''`, `제목(H1) '...' ≠ 파일 이름` 같은 줄이 나온다. 기존 노트를 한꺼번에 고치지 않아도 된다.
   - 해결 기록 템플릿 `Fix.md`는 `area: "[[업무]]"`가 기본값이라, 볼트에 `업무` 노트가 없으면 해결 기록마다 `깨진 링크 [[업무]]`가 나온다. 볼트의 `99_System/Templates/Fix.md`에서 `업무`를 내 영역 노트 이름으로 바꾼다.
   - 점검은 새로 만들거나 고친 파일만 지정해서 한다: `sb.py lint "<파일 경로>"`. 마지막 줄이 `점검(지정한 파일) 1개, 문제 0건`이면 그 파일은 깨끗하다. AI도 바꾼 파일만 이렇게 점검한다.

> [!WARNING]
> **Templater 함정**: Templater의 "새 파일 생성 시 실행"(Trigger Templater on new file creation)이 켜진 볼트를 Obsidian이 열고 있는 동안 템플릿 파일을 밖에서 복사해 넣으면, 템플릿 안의 `<% ... %>` 구문이 그 자리에서 실행되어 템플릿이 `undefined` 같은 값으로 망가진다. 템플릿은 반드시 Obsidian을 닫고 복사한다.

확인 방법과 자세한 내용은 [docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#이미-있는-볼트를-쓸-때)에 있다.

## 준비물

| 준비물 | 용도 | 확인 |
|---|---|---|
| [Obsidian](https://obsidian.md) | 노트를 보고 쓰는 앱 | 앱이 열린다 |
| Claude Code 또는 Codex | 말로 부탁하는 AI 에이전트 | 터미널에서 실행된다 |
| [Python](https://www.python.org/downloads/) 3.9 이상 | 보조 도구 `sb.py`와 Claude Code hook 실행(표준 라이브러리만 쓴다) | `python --version`(macOS·Linux는 `python3 --version`. Windows Git Bash에서는 bash 예시의 `python3` 대신 `python`) |
| Git(선택) | 이 저장소 내려받기, 볼트 백업 | `git --version` |

## 설치

1. 저장소를 내려받는다. Git이 있으면 `git clone <저장소 주소>`, 없으면 저장소 페이지에서 ZIP으로 내려받아 압축을 푼다.
2. 터미널에서 저장소 폴더(이 README와 `install.ps1`·`install.sh`가 있는 곳)로 이동해 설치 스크립트를 실행한다.

```powershell
# Windows (PowerShell)
cd "<저장소 폴더>"
powershell -ExecutionPolicy Bypass -File install.ps1          # Claude Code에 설치
powershell -ExecutionPolicy Bypass -File install.ps1 -Codex   # Claude Code와 Codex 둘 다
```

```bash
# macOS / Linux
cd "<저장소 폴더>"
bash install.sh           # Claude Code에 설치
bash install.sh --codex   # Claude Code와 Codex 둘 다
```

- 하는 일: `skills/second-brain` 폴더를 `~/.claude/skills/second-brain`으로 복사한다. 옵션을 주면 Codex의 사용자 스킬 폴더 `~/.agents/skills/second-brain`에도 복사한다. 스타터 볼트도 이 안(`assets/starter-vault`)에 함께 들어간다.
- Claude Code에는 [자동 기록](#자동-기록-claude-code)도 설치한다: hook 파일을 `~/.claude/hooks/`에, `/inbox`·`/init-project` 스킬을 `~/.claude/skills/`에 복사하고, `~/.claude/settings.json`에 hook을 등록하고, 전역 `~/.claude/CLAUDE.md` 끝에 `<!-- brain:start -->` 구역을 더한다. 두 파일은 고칠 것이 있을 때만 원본을 `.bak-<날짜시각>`으로 남기고 고친다. 이 단계는 `python`(macOS·Linux는 `python3`)으로 [tools/claude_setup.py](tools/claude_setup.py)를 실행한다.
- `-ExecutionPolicy Bypass`는 그 한 번의 실행에만 적용된다. PC의 실행 정책 설정은 바꾸지 않는다.
- 다시 실행해도 된다: 스킬·hook 파일을 새로 복사하고, hook 등록과 `CLAUDE.md` 구역은 이미 있으면 그대로 둔다(중복으로 더하지 않는다). 개인 설정(`~/.second-brain/`의 `config.json`·`local.md`)은 건드리지 않는다.
- 확인: 끝에 `Installed: <설치 경로>`가 출력되고, 그 폴더에 `SKILL.md`와 `scripts/sb.py`가 있다. 이어서 `Next:` 줄에 볼트를 만들거나 연결하는 `sb.py` 명령이 나온다(`install.sh`는 `python3`가 실행되지 않는 환경, 예: Windows Git Bash에서는 `python`으로 보여 준다). 자세한 확인 방법은 [docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#설치-확인)에 있다.

## 말로 부탁하기

AI 에이전트(스킬을 설치한 Claude Code나 Codex)에게 이렇게 말한다. 아래 폴더는 기본값이다.

| 이렇게 말하면 | AI가 하는 일 | 결과가 놓이는 곳 |
|---|---|---|
| "세컨드 브레인 만들어줘" | 만들 위치를 묻고 `sb init`으로 스타터 볼트를 만든 뒤, Obsidian 설정을 안내한다 | 지정한 폴더(기본 제안 `~/Documents/SecondBrain`) |
| "기존 볼트 연결해줘" | `sb setup`으로 볼트 경로를 저장한다. `AGENTS.md`가 없으면 예시를 보여 주고 넣을지 묻는다 | `~/.second-brain/config.json` |
| "오늘 노트 만들어줘" | 오늘 일일 노트가 없으면 템플릿으로 만들고, 이틀 넘게 남은 할 일을 알려 준다(복사하지 않는다) | `10_Daily/YYYY-MM-DD.md` |
| "할 일 추가해줘: ○○ 금요일까지" | 오늘 끝낼 일은 오늘 노트에 적는다. 마감이 오늘이 아니거나 며칠 걸리는 일은 관련 진행 중(`status: active`) 프로젝트 노트에 `- [ ] ○○ 📅 날짜`로 적는다(맞는 프로젝트가 없으면 오늘 노트에 📅와 함께) | 오늘 일일 노트 또는 `20_Projects/` |
| "볼트에 '○○' 프로젝트 만들어줘" | 프로젝트 노트를 만들고 목표·완료 조건, 영역(`area: "[[업무]]"` 형식), 마감(`due`)을 채운다 | `20_Projects/` |
| "메모해 둬: ○○" | 분류하지 않고 인박스에 새 노트로 적는다 | `00_Inbox/` |
| "인박스 정리해줘" | 메모를 하나씩 분류해 옮기고 연결한 뒤, "원래 이름 → 위치" 표로 보고한다 | 각 PARA 폴더. 여러 노트로 나누거나 기존 노트에 합친 원본은 `90_Archive/` |
| "주간 리뷰 해줘" | 이번 주(ISO 주차, 월~일) 일일 노트·새 노트·진행 중 프로젝트를 읽고 주간 노트를 쓴다. 2주 넘게 손대지 않은 프로젝트를 알려 준다 | `10_Daily/Weekly/YYYY-Www.md` |
| "이거 해결 기록 남겨줘" | 현상 → 원인 → 변경 → 검증 → 출처 순으로 쓴다. 증상과 원인 기제가 같은 기록에 사례를 더하고, 원인이 다르면 새 노트를 만들어 서로 링크한다 | `40_Resources/해결 기록/` |
| "참고 자료로 정리해줘" | 내 말로 요약하고 원본 링크를 단다 | `40_Resources/참고 자료/` |
| "[[노트]]에서 노트 정제해줘" | 다시 쓸 생각 하나당 영구 노트 하나를 만든다. 제목은 한 문장 주장, 출처 링크 필수 | `50_Notes/` |
| "볼트에서 ○○ 노트를 90_Archive로 옮겨줘" | 지우지 않고 보관 폴더로 옮긴다 | `90_Archive/` |
| "볼트 기준으로 ○○ 알려줘" | 볼트에서 찾아 근거 노트 링크와 함께 답한다. 없으면 "볼트에 없음"이라고 먼저 말한다 | (읽기만) |
| "전에 이거 해결한 적 있나" | 해결 기록부터 찾아 답한다 | (읽기만) |
| "기억해: ○○", "브레인에 넣어" | 지식·사실·결정이면 같은 주제 노트를 찾아 고치거나 맞는 폴더에 새로 쓴다. AI의 작업 방식에 대한 교정이면 볼트가 아니라 에이전트 메모리에 둔다 | 해당 노트, `99_System/브레인 로그.md` |
| (분석·비교·웹 조사 답 끝의) "브레인에 남길까요?"에 "응" | 같은 주제 노트를 찾아 고치거나 새로 쓰고 출처를 단다 | 해당 노트, `99_System/브레인 로그.md` |
| "세컨드 브레인 점검" | 색인을 다시 만들고 `sb lint`로 깨진 링크·고아·비밀정보·남은 `> 충돌:`을 찾아 형식 문제는 고친다. 낡은 내용·방치 프로젝트는 목록으로만 보고한다 | `99_System/색인.md`, `99_System/브레인 로그.md` |
| `/inbox`, `/inbox 같이` (Claude Code) | 인박스를 나와 함께 정리하고, dream 규칙 제안은 번호별로 승인받아 반영한다 | 각 폴더, 전역 `CLAUDE.md` 또는 프로젝트 메모리 |
| `/init-project [경로]` (Claude Code) | 코드 저장소를 읽기만 하고 저장소 노트를 만들거나 갱신한다 | `40_Resources/저장소/` |

AI는 매번 볼트의 `AGENTS.md`를 먼저 읽고 그 규칙을 따른다. 규칙이 서로 다르면 **사용자의 그때그때 지시 > `AGENTS.md` > `local.md` > 나의 판단 방식 노트 > 스킬 기본값** 순으로 따른다. 기록할 대상이 애매하면 쓰기 전에 먼저 묻고, 쓴 뒤에는 바꾼 파일을 점검한 실제 결과로 보고한다. 읽기만 했으면 `볼트 변경: 없음(읽기 전용)`이라고 적는다. 자세한 동작은 [docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#요청별로-ai가-실제로-하는-일)에 있다.

## 폴더 구조

PARA(Tiago Forte의 분류법)에 영구 노트 폴더를 더한 구조다.

| 폴더 | 넣는 것 | 나가는 곳 |
|---|---|---|
| `00_Inbox/` | 빠르게 적은 메모, 링크, 생각. 분류 전 상태 | 정리 후 아래 폴더로 |
| `10_Daily/` | 일일 노트 `YYYY-MM-DD.md` | 그대로 보관 |
| `10_Daily/Weekly/` | 주간 리뷰 `YYYY-Www.md`(예: `2026-W42.md`) | 그대로 보관 |
| `10_Daily/Journal/` | 세션 일지 `YYYY-MM-DD 세션.md`(Claude Code hook이 자동으로 쓴다) | 그대로 보관 |
| `20_Projects/` | 끝나는 날이나 완료 조건이 있는 일 | 끝나면 `90_Archive/` |
| `30_Areas/` | 계속 관리하는 책임 영역(업무, 학습, 건강, 재무 등)과 `나의 판단 방식` | 그대로 유지 |
| `40_Resources/해결 기록/` | 해결한 문제의 현상·원인·변경·검증 | 그대로 유지 |
| `40_Resources/참고 자료/` | 주제별 참고 자료, 요약, 스니펫 | 그대로 유지 |
| `40_Resources/저장소/` | 코드 저장소 하나당 노트 하나(`/init-project`) | 그대로 유지 |
| `50_Notes/` | 내 말로 정리한 생각 하나짜리 영구 노트 | 그대로 유지 |
| `90_Archive/` | 끝난 프로젝트, 쓰지 않는 노트, 정리가 끝난 인박스 원본 | — |
| `99_System/` | `Templates/`(노트 틀), `Routines/`(예약 실행용 프롬프트), `색인.md`(자동 생성 목록), `브레인 로그.md`(작업 기록) | — |

## 자동 기록 (Claude Code)

Claude Code에 설치하면 hook 세 개가 볼트에 기록을 쌓는다. 저절로 쌓이는 것은 아래 셋뿐이고, 규칙은 내가 승인한 것만 들어간다.

| 언제 | 무엇을 | 어디에 |
|---|---|---|
| 세션이 끝날 때 | 그 세션에서 한 일을 한 줄로 요약 | `10_Daily/Journal/YYYY-MM-DD 세션.md` |
| 하루 한 번(세션 시작 때) | 대화에서 내가 AI를 교정하거나 선호를 밝힌 대목을 골라 규칙 **제안** | `00_Inbox/YYYY-MM-DD dream 규칙 제안.md` → `/inbox`에서 승인한 것만 전역 `CLAUDE.md`의 `# 배운 규칙 (dream)` 또는 프로젝트 메모리로 |
| 세션 시작 때 | 볼트 색인을 다시 만들고, dream 제안 대기·점검 7일 경과·로그인 풀림을 하루 한 번 알림 | `99_System/색인.md`, 세션 맥락의 `[brain]` 줄 |

- **터미널 CLI 로그인이 필요하다.** 요약은 `claude -p --model haiku`(도구 없음)로 하므로 터미널에서 `claude auth login`을 한 번 해 둔다. 데스크톱 앱 로그인과는 따로다. 로그인 전에는 대기열에 쌓였다가 로그인 뒤 처리된다.
- **대화 일부가 요약 모델로 간다.** 사람이 친 말과 Claude의 글(도구 결과 제외)이 비밀정보 패턴을 가린 뒤 내 Claude 계정으로 보내지고, 사용량도 그 계정에서 쓴다. 일지·dream 파일은 볼트 노트라 볼트를 백업하면 함께 올라간다. 빼고 싶은 작업 폴더는 `~/.second-brain/config.json`의 `journal_exclude`에 적는다.
- 자세한 동작·보내는 내용·바뀌는 파일·확인 방법은 [docs/AI와-함께-쓰기.md](docs/AI와-함께-쓰기.md#자동-기록-claude-code-hook)에 있다.

## 지우기

Claude Code 자동 기록만 끄려면 저장소 폴더에서 hook 등록을 뺀다. `settings.json`의 다른 설정은 그대로 두고, 바꾸기 전 원본은 `.bak-<날짜시각>`으로 남는다.

```powershell
# Windows (PowerShell)
python tools\claude_setup.py remove
```

```bash
# macOS / Linux (Windows Git Bash에서는 python3 대신 python)
python3 tools/claude_setup.py remove
```

이어서 필요하면 파일을 직접 지운다. 같은 이름의 다른 스킬을 쓰고 있지 않은지 먼저 확인한다.

```powershell
# Windows (PowerShell)
Remove-Item "$HOME\.claude\hooks\brain_common.py", "$HOME\.claude\hooks\brain-*.py", "$HOME\.claude\hooks\brain-*.log"
Remove-Item -Recurse "$HOME\.claude\skills\inbox", "$HOME\.claude\skills\init-project", "$HOME\.second-brain\state"
Remove-Item -Recurse "$HOME\.claude\skills\second-brain"   # 스킬까지 모두 지울 때
```

```bash
# macOS / Linux / Windows Git Bash
rm -f ~/.claude/hooks/brain_common.py ~/.claude/hooks/brain-*.py ~/.claude/hooks/brain-*.log
rm -rf ~/.claude/skills/inbox ~/.claude/skills/init-project ~/.second-brain/state
rm -rf ~/.claude/skills/second-brain   # 스킬까지 모두 지울 때
```

- 전역 `~/.claude/CLAUDE.md`의 `<!-- brain:start -->` ~ `<!-- brain:end -->` 구역은 내가 승인한 규칙이 들어 있어 자동으로 지우지 않는다. 필요 없으면 편집기로 그 구역을 지운다.
- `~/.second-brain/`의 `config.json`·`local.md`(볼트 경로·개인 설정)와 볼트의 노트(세션 일지·dream 제안 포함)는 지우지 않는다. Codex에 설치했다면 `~/.agents/skills/second-brain`도 지운다.

## 안전 원칙

- **비밀정보를 적지 않는다.** 비밀번호·토큰·API 키·개인 식별번호는 노트에 쓰지 않는다. AI는 쓰기 전에 걸러 `[비밀정보 제거됨]`으로 바꾸고, `sb lint`가 의심 문자열을 찾아 준다.
- **노트 제목에 비밀 파일 단어를 쓰지 않는다.** 이름에 토큰·비번·비밀번호·password·passwd·token·secret·credential이 든 파일은 비밀정보가 들었을 수 있어 AI와 `sb.py`가 열지 않고 건너뛴다. 그래서 `sb new`는 이런 단어가 든 제목을 거부하고 다른 말을 쓰라고 알려 준다(예: `토큰` → `인증`). 영어 단어는 단어 단위로 본다(`API token`은 거부, `Tokenizer`는 통과). 한국어는 글자가 붙어 있어도 걸린다(`토큰화`도 거부).
- **백업 저장소는 private으로.** 볼트를 git으로 백업하면 쓴 내용이 그대로 원격으로 나간다. 볼트 백업 저장소는 반드시 private으로 만들고, 공개 저장소인 이 키트와 섞지 않는다.
- **노트는 지우지 않고 보관한다.** 필요 없어진 노트는 `90_Archive/`로 옮긴다. `sb new`는 같은 이름의 노트가 볼트 어디에든 있으면 만들지 않는다(덮어쓰기 없음). 대소문자만 다른 이름도 같은 이름으로 본다.
- **AI는 볼트 안에서만 쓴다.** 볼트 밖 폴더의 내용은 내가 허용하고 지정할 때만 읽는다. `sb.py`는 내용 읽기를 볼트와 `read_outside`로 제한하며, `lint`의 링크 확인에는 상위 Obsidian 노트의 이름만 색인한다. 순회 중 연결 폴더는 건너뛰고 제외 규칙은 별칭·실제 경로에 모두 적용한다. 하드링크·bind mount는 경로로 구분할 수 없어 차단 범위 밖이다. 볼트의 git commit·push는 내가 요청할 때만 한다.
- **개인 설정은 저장소 밖에 둔다.** `config.json`(볼트 경로)과 `local.md`(개인 설정)는 `~/.second-brain/`에 있고 Claude Code·Codex 설치가 함께 쓴다. 이 키트 저장소의 `.gitignore`는 실수로 저장소 안에 만든 `config.json`·`local.md`와 `.claude/`·`.obsidian/`·`.trash/`·`.env*`·`*.pem`·`*.key`·`*.log`가 올라가지 않게 막는다. 볼트를 git으로 백업할 때는 볼트 저장소의 `.gitignore`를 따로 만든다.

## 저장소 구성

| 경로 | 내용 |
|---|---|
| `README.md` | 이 문서 |
| `docs/세컨드-브레인-만들기.md` | 입문 가이드: 준비물부터 첫 주 리듬까지 |
| `docs/AI와-함께-쓰기.md` | 스킬 설치·연결·개인 설정, 요청별 동작, 자동 루틴, `sb.py` 명령 참고 |
| `install.ps1`, `install.sh` | 설치 스크립트(Windows / macOS·Linux): 스킬 복사와 Claude Code 자동 기록 설치 |
| `skills/second-brain/SKILL.md` | AI 에이전트가 읽는 스킬 본문 |
| `skills/second-brain/references/` | 기록하기(`capture.md`)·찾기(`search.md`) 세부 절차 |
| `skills/second-brain/scripts/sb.py` | 보조 도구: 볼트 만들기·연결, 날짜, 템플릿 채우기, 할 일·태그·링크 점검 |
| `skills/second-brain/local.example.md` | 개인 설정 `local.md`의 예시. `~/.second-brain/local.md`로 복사해 쓴다 |
| `skills/second-brain/assets/starter-vault/` | 스타터 볼트: `AGENTS.md`, `Home.md`, 템플릿, 루틴 프롬프트 |
| `skills/inbox/`, `skills/init-project/` | Claude Code에서 직접 부르는 `/inbox`(인박스·dream 제안 승인), `/init-project`(저장소 노트) |
| `hooks/` | Claude Code hook: 세션 일지(`brain-journal.py`), dream·색인(`brain-dream.py`), 안내 줄(`brain-lint-reminder.py`), 공용 코드(`brain_common.py`) |
| `tools/claude_setup.py`, `tools/brain-claude-md.md` | hook·전용 스킬 복사와 `settings.json`·`CLAUDE.md` 고치기(설치 스크립트가 부른다), `CLAUDE.md`에 더하는 구역 |
| `LICENSE` | MIT 라이선스 |

테스트: 저장소 루트에서 `python -m unittest discover -s tests -v`를 실행한다(표준 라이브러리만 사용, macOS·Linux는 `python3`). `sb.py` 시험, 설치 보조 스크립트 시험(임시 폴더의 가짜 `~/.claude`), hook 시나리오(`tests/brain_hooks_scenario.py`를 별도 프로세스로, 가짜 모델·합성 대화 기록·임시 볼트)가 함께 돈다. 실제 `~/.claude`·`~/.second-brain`·볼트는 건드리지 않는다.

성능 비교: `python tests/benchmark_sb.py`는 격리된 임시 볼트에 노트 2,000개와 첨부 1,000개를 만들어 `origin/main`과 현재 작업 트리를 비교한다. 다른 버전은 `--refs REF worktree`로 지정하며, 결과 JSON의 임시 경로는 `<tmp>`로 표시한다.

## 라이선스

[MIT](LICENSE)
