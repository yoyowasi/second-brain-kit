# AI와 함께 쓰기

`second-brain` 스킬을 설치하면 Claude Code나 Codex 같은 AI 에이전트가 어느 프로젝트 세션에서든 내 볼트를 읽고 쓴다. 스킬은 두 부분이다. AI가 읽는 작업 설명서(`SKILL.md`)와, 날짜 계산·템플릿 채우기·중복 확인·점검처럼 틀리기 쉬운 일을 맡는 보조 도구 `sb.py`다.

AI는 볼트 일을 시작할 때마다 이 순서를 따른다.

1. `sb.py where`로 볼트 위치를 확인한다.
2. `sb.py where`가 알려 주는 `local.md`(개인 설정, 기본 `~/.second-brain/local.md`)가 있으면 읽는다.
3. 볼트의 `AGENTS.md`(볼트 규칙의 단일 기준)를 읽는다.
4. 판단이 애매하면 `30_Areas/나의 판단 방식.md`를 기본값으로 쓴다.
5. 날짜는 `sb.py today`로 얻는다(머리로 계산하지 않는다).

규칙이 서로 다르면 **사용자의 그때그때 지시 > `AGENTS.md` > `local.md` > 나의 판단 방식 노트 > 스킬 기본값** 순으로 따른다.

볼트를 아직 만들지 않았다면 [세컨드 브레인 만들기](세컨드-브레인-만들기.md)부터 본다.

- [스킬 설치](#스킬-설치)
- [설치 확인](#설치-확인)
- [볼트 연결](#볼트-연결)
- [개인 설정: local.md와 config.json](#개인-설정-localmd와-configjson)
- [요청별로 AI가 실제로 하는 일](#요청별로-ai가-실제로-하는-일)
- [다른 프로젝트 작업 중에 쓰기](#다른-프로젝트-작업-중에-쓰기)
- [자동 루틴](#자동-루틴)
- [sb.py 명령 참고](#sbpy-명령-참고)
- [문제 해결](#문제-해결)

## 스킬 설치

저장소 폴더(`install.ps1`·`install.sh`가 있는 곳)에서 설치 스크립트를 실행한다. 저장소를 내려받고 그 폴더로 이동하는 방법은 [세컨드 브레인 만들기 > 2-2](세컨드-브레인-만들기.md#2-2-이-키트-설치)에 있다.

| 에이전트 | Windows (PowerShell) | macOS / Linux | 설치 위치 |
|---|---|---|---|
| Claude Code | `powershell -ExecutionPolicy Bypass -File install.ps1` | `bash install.sh` | `~/.claude/skills/second-brain` |
| Claude Code + Codex | `powershell -ExecutionPolicy Bypass -File install.ps1 -Codex` | `bash install.sh --codex` | 위 경로와 `~/.agents/skills/second-brain` |

- Claude Code는 `~/.claude/skills/` 아래 스킬을 모든 프로젝트에서 쓴다.
- Codex는 사용자 스킬을 `~/.agents/skills/`에서 읽는다(Codex 공식 문서 기준). 예전 버전의 Codex나 이 키트의 예전 설치 스크립트는 `~/.codex/skills`를 썼을 수 있다. 설치 뒤 Codex의 스킬 목록에 보이지 않으면 Codex 공식 문서에서 지금 버전의 사용자 스킬 위치를 확인한다.
- `-ExecutionPolicy Bypass`는 그 한 번의 실행에만 적용되고 PC의 실행 정책 설정은 바꾸지 않는다.
- 다시 실행해도 된다. 설치된 스킬 파일만 새로 복사하고 개인 설정 폴더 `~/.second-brain/`은 건드리지 않는다. 키트를 새 버전으로 바꿀 때는 저장소를 갱신(`git pull` 또는 새 ZIP)한 뒤 설치 스크립트를 다시 실행한다.
- **볼트 경로와 개인 설정은 한 곳에 있다.** `config.json`(볼트 경로)과 `local.md`(개인 설정)는 설치 위치와 관계없이 `~/.second-brain/`에 두고 Claude Code와 Codex 설치가 함께 쓴다. 그래서 `init`이나 `setup`은 한 번만 하면 된다([개인 설정](#개인-설정-localmd와-configjson)).
- **예전 버전에서 바꿀 때**: 예전 버전은 `config.json`·`local.md`를 설치된 스킬 폴더 안에 두었다. 지금 `sb.py`는 그 파일을 읽지 않으므로, 그 두 파일을 `~/.second-brain/`으로 옮기거나 `setup`을 다시 한 번 실행한다.

## 설치 확인

1. **파일이 있는지**

   ```powershell
   # Windows (PowerShell) — True가 나오면 된다
   Test-Path "$HOME\.claude\skills\second-brain\SKILL.md"
   Test-Path "$HOME\.agents\skills\second-brain\SKILL.md"    # -Codex로 설치했을 때
   ```

   ```bash
   # macOS / Linux
   ls ~/.claude/skills/second-brain/SKILL.md
   ls ~/.agents/skills/second-brain/SKILL.md   # --codex로 설치했을 때
   ```

2. **보조 도구가 실행되는지**

   ```powershell
   # Windows (PowerShell)
   python "$HOME\.claude\skills\second-brain\scripts\sb.py" where
   ```

   ```bash
   # macOS / Linux (Windows Git Bash에서는 python3 대신 python)
   python3 ~/.claude/skills/second-brain/scripts/sb.py where
   ```

   볼트를 연결하기 전이라면 다음 안내가 나온다. 도구는 정상이고 볼트만 아직 없다는 뜻이다. `<sb.py 경로>` 자리에는 방금 실행한 `sb.py`의 절대 경로가 나오므로, 줄을 그대로 복사해 `<폴더>`만 바꿔 실행하면 된다(macOS·Linux에서는 `python` 대신 `python3`).

   ```text
   볼트 경로가 설정되지 않았습니다.
     새로 만들기: python "<sb.py 경로>" init <폴더>
     기존 볼트:   python "<sb.py 경로>" setup <폴더>   (또는 환경변수 SECOND_BRAIN)
   ```

3. **에이전트가 스킬을 보는지**
   - Claude Code: 새 세션에서 `/skills`를 실행하면 목록에 `second-brain`이 보인다. `/second-brain`으로 직접 부를 수도 있다.
   - Codex: 버전에 따라 `/skills`로 목록을 보거나 `$`를 입력해 스킬을 고른다. 정확한 방법은 Codex 공식 문서를 따른다.
   - 어느 쪽이든 "세컨드 브레인 볼트 위치 확인해줘"라고 말하면 AI가 `sb.py where`를 실행하고 결과를 알려 준다.

## 볼트 연결

볼트 위치는 **환경변수 `SECOND_BRAIN` → `~/.second-brain/config.json`의 `"vault"`** 순서로 찾는다. 설정 폴더 `~/.second-brain/`은 환경변수 `SECOND_BRAIN_HOME`으로 바꿀 수 있다([개인 설정](#개인-설정-localmd와-configjson)).

### 새 볼트를 만들 때

"세컨드 브레인 만들어줘" 또는 `sb.py init <새 폴더>`. 자세한 순서는 [세컨드 브레인 만들기](세컨드-브레인-만들기.md#3-볼트-만들기)에 있다.

### 이미 있는 볼트를 쓸 때

"기존 볼트 연결해줘"라고 하거나 직접 실행한다. 경로는 내 볼트 폴더로 바꾼다.

```powershell
# Windows (PowerShell)
python "$HOME\.claude\skills\second-brain\scripts\sb.py" setup "$HOME\Documents\SecondBrain"
```

```bash
# macOS / Linux (Windows Git Bash에서는 python3 대신 python)
python3 ~/.claude/skills/second-brain/scripts/sb.py setup ~/Documents/SecondBrain
```

- `setup`은 볼트의 노트를 바꾸지 않는다. 경로만 `~/.second-brain/config.json`에 저장하고, 볼트에 빠진 것이 있으면 `주의:`로 알려 준다.
- `AGENTS.md`와 템플릿이 둘 다 없는 볼트라면 이렇게 나온다. `<설치된 스킬 폴더>` 자리에는 실행한 스킬 폴더의 절대 경로가 내 운영체제의 경로 형식으로 나온다.

  ```text
  볼트 경로를 저장했습니다: <볼트 경로>
  주의: AGENTS.md(볼트 규칙)가 없습니다. <설치된 스킬 폴더>\assets\starter-vault\AGENTS.md 를 참고해 만들어 두세요.
  주의: 템플릿이 없어 'sb new daily' 등이 실패합니다: daily, weekly, project, fix, note, inbox
        <설치된 스킬 폴더>\assets\starter-vault\99_System\Templates 에서 복사하세요(Obsidian을 닫은 상태에서).
  ```

- 환경변수 `SECOND_BRAIN`이 설정되어 있으면 두 번째 줄에 `주의: 환경변수 SECOND_BRAIN(<경로>)이 설정되어 있어 그쪽 볼트가 계속 쓰입니다.`가 나온다. 저장한 경로보다 환경변수가 우선하므로, 이 볼트를 쓰려면 [환경변수를 지운다](#환경변수-second_brain).

`주의:`가 나왔으면 볼트에 다음을 준비한다. 아래 `assets/starter-vault/`는 설치된 스킬 폴더(예: `~/.claude/skills/second-brain/`) 안에 있다.

1. **`AGENTS.md`**: 메시지에 나온 `assets/starter-vault/AGENTS.md`를 볼트 맨 위에 복사해 내 볼트의 폴더 이름·형식에 맞게 고친다. AI에게 연결을 부탁했다면 AI가 예시를 보여 주고 넣을지 묻는다.
2. **템플릿**: `sb.py new`는 볼트의 `99_System/Templates/<이름>.md`를 템플릿으로 쓴다. 없으면 `템플릿이 없습니다` 오류로 멈춘다(`Resource`만 내장 기본 구조가 있다). 그래서 템플릿이 없는 볼트는 "오늘 노트 만들어줘"부터 실패한다.
   - **Obsidian을 닫고** `setup`이 알려 준 폴더(`assets/starter-vault/99_System/Templates/`)의 파일을 볼트의 `99_System/Templates/`로 복사한다. 폴더를 만들고 이미 있는 템플릿은 덮어쓰지 않는 복사 명령(PowerShell·bash)은 [README 빠른 시작 B](../README.md#빠른-시작)의 3번에 있다. Templater의 "새 파일 생성 시 실행"이 켜져 있으면 열려 있는 볼트에 들어온 템플릿 구문이 그 자리에서 실행되어 템플릿이 망가진다.
   - Obsidian을 다시 열고 Templater 설정의 템플릿 폴더를 `99_System/Templates`로 정한다.
   - `Fix.md`(해결 기록)는 `area: "[[업무]]"`가 기본값이다. 내 볼트에 `업무` 노트가 없으면 해결 기록마다 `lint`가 `깨진 링크 [[업무]]`로 알려 주므로, 볼트에 복사한 `Fix.md`에서 `업무`를 내 영역 노트 이름으로 바꾼다.
   - (선택) AI가 애매할 때 기본값으로 쓰는 `assets/starter-vault/30_Areas/나의 판단 방식.md`도 같은 방법으로 복사한다. 이 노트 끝의 영역 링크(`[[업무]]` 등)도 내 영역 노트 이름으로 고친다.

**확인**:

```powershell
# Windows (PowerShell)
python "$HOME\.claude\skills\second-brain\scripts\sb.py" where
python "$HOME\.claude\skills\second-brain\scripts\sb.py" render Daily --title 2026-10-15
```

```bash
# macOS / Linux (Windows Git Bash에서는 python3 대신 python)
python3 ~/.claude/skills/second-brain/scripts/sb.py where
python3 ~/.claude/skills/second-brain/scripts/sb.py render Daily --title 2026-10-15
```

- `where`에서 `vault:`가 그 폴더이고 `agents_md: ... exists=True`이면 된다.
- `render`가 날짜가 채워진 본문(`# 2026-10-15`, `← 어제: [[2026-10-14]]`)을 출력하면 템플릿이 준비된 것이다. 날짜는 아무 날이나 된다. `템플릿이 없습니다`가 나오면 복사 위치를 다시 본다. `render`는 출력만 하고 파일을 쓰지 않는다.
- 기존 볼트 전체를 `lint`하면 기존 노트마다 `frontmatter 없음`, `type 값 이상: ''`, `created 형식 이상: ''`, `제목(H1) '...' ≠ 파일 이름` 같은 줄이 나온다. 기존 노트가 이 키트의 노트 형식을 따르지 않아서 생기는 것이고 고장이 아니다. 기존 노트를 한꺼번에 고치지 말고, 새로 만들거나 고친 파일만 `lint "<파일 경로>"`로 점검한다(AI도 바꾼 파일만 점검한다).

### 환경변수 SECOND_BRAIN

`config.json`보다 우선한다. 잠깐 다른 볼트(연습용 등)를 가리킬 때 쓴다. 평소에는 `setup`으로 저장한 경로면 충분하다.

```powershell
# Windows: 지금 창에서만
$env:SECOND_BRAIN = "C:\Notes\Practice"
# Windows: 내 계정에 계속 (새 터미널부터 적용)
[Environment]::SetEnvironmentVariable("SECOND_BRAIN", "C:\Notes\Practice", "User")
```

```bash
# macOS / Linux: 지금 창에서만
export SECOND_BRAIN="$HOME/Documents/Practice"
# 계속 쓰려면 같은 줄을 ~/.bashrc 또는 ~/.zshrc에 추가한다
```

이 환경변수가 설정된 채로 `init`이나 `setup`을 실행하면, 경로는 `config.json`에 저장되지만 `주의: 환경변수 SECOND_BRAIN(<경로>)이 설정되어 있어 그쪽 볼트가 계속 쓰입니다.`가 나온다. 볼트를 옮겼는데 옛 경로를 계속 찾을 때도 이 환경변수가 옛 경로로 남아 있는지 먼저 본다. 저장한 경로를 쓰려면 환경변수를 지운다.

```powershell
# Windows: 지금 창에서만
Remove-Item Env:SECOND_BRAIN
# Windows: 내 계정에서 지우기 (새 터미널부터 적용)
[Environment]::SetEnvironmentVariable("SECOND_BRAIN", $null, "User")
```

```bash
# macOS / Linux: 지금 창에서만
unset SECOND_BRAIN
# ~/.bashrc 또는 ~/.zshrc에 넣어 둔 export SECOND_BRAIN=... 줄도 지운다
```

AI 에이전트는 실행될 때의 환경변수를 물려받으므로, 지운 뒤에는 새 터미널에서 에이전트를 다시 시작하고 `sb.py where`의 `vault:`를 확인한다.

### Obsidian 볼트 루트가 더 위에 있을 때

큰 Obsidian 볼트 안의 하위 폴더 하나를 세컨드 브레인으로 쓰는 경우다. `sb.py`는 `.obsidian` 폴더가 있는 가장 가까운 상위 폴더를 Obsidian 볼트 루트로 보고, 링크 해석과 백링크 검색을 그 기준으로 한다(`sb.py where`의 `obsidian_root`). 노트 생성은 여전히 세컨드 브레인 폴더 안에서만 한다. 이 구조라면 `local.md`의 "볼트" 절에 적어 둔다.

Dataview는 경로를 Obsidian 볼트 루트 기준으로 읽으므로, 스타터 볼트의 Dataview 경로 앞에 하위 폴더 이름을 붙여야 한다. 고칠 곳은 아래가 전부다. 하위 폴더가 `SecondBrain`이면 `FROM "00_Inbox"` → `FROM "SecondBrain/00_Inbox"`, `startswith(file.folder, "99_System")` → `startswith(file.folder, "SecondBrain/99_System")`처럼 바꾼다.

| 파일 | 고칠 곳 |
|---|---|
| `Home.md` | `FROM "00_Inbox"`, `FROM "20_Projects"`(두 곳), `FROM "10_Daily" OR "20_Projects"`, `FROM "50_Notes"` |
| `30_Areas/`의 영역 노트(`업무`·`학습`·`건강`·`재무`) | `FROM "20_Projects" AND [[]]`, `startswith(file.folder, "99_System")`(`업무`는 두 곳) |
| `99_System/Templates/Weekly.md` | `FROM "20_Projects" OR "30_Areas" OR "40_Resources" OR "50_Notes"`. 이 템플릿으로 이미 만든 주간 노트도 같다 |

`config.json`의 `folders`로 폴더 이름을 바꿀 때도 같은 파일의 해당 폴더 경로를 고친다.

같은 Obsidian 볼트 안의 볼트 밖 폴더(예: 세컨드 브레인 옆의 `업무 일지`)에 세컨드 브레인 노트를 가리키는 `[[링크]]`가 있다면, 노트 이름을 바꿀 때 그 링크도 찾을 수 있게 `config.json`의 `read_outside`에 그 폴더를 넣는다(예: `"read_outside": ["../업무 일지"]`). 그러면 `sb.py backlinks`가 그 폴더도 함께 읽고, 걸린 파일을 `볼트 밖(고치지 말고 보고)`으로 표시한다. `read_outside`에 넣지 않은 볼트 밖 파일은 `backlinks`가 읽지 않는다.

## 개인 설정: local.md와 config.json

둘 다 **`~/.second-brain/`** 폴더에 둔다. 스킬 설치 폴더 밖에 있어서 Claude Code와 Codex 설치가 같은 파일을 함께 쓰고, 설치 스크립트를 다시 실행해도 바뀌지 않는다. 개인 설정이라 공개 저장소에 올리지 않는다(실수로 저장소 안에 만들어도 올라가지 않게 `.gitignore`에 들어 있다).

| 파일 | 누가 읽나 | 무엇을 적나 |
|---|---|---|
| `local.md` | AI가 볼트 일을 시작할 때 | 다른 프로젝트 세션에서 볼트를 쓸 때 필요한 것: 태그 어휘, 기록 정책, 프로젝트 연결, 더 읽어도 되는 곳 |
| `config.json` | `sb.py` | 볼트 경로, 폴더 이름, 열지 않을 폴더, 링크를 함께 찾을 볼트 밖 폴더, 외부 원본 경로, 시간대 |

볼트 규칙 자체(폴더 구조, 노트 형식, 반복 작업 절차)는 볼트의 `AGENTS.md`에 둔다. `local.md`에 규칙을 복사하지 않는다.

`sb.py where`의 `config:`·`local_md:` 줄이 지금 쓰는 두 파일의 경로와 존재 여부를, `skill:` 줄이 지금 실행한 스킬 폴더를 보여 준다.

**설정 폴더 바꾸기**: 환경변수 `SECOND_BRAIN_HOME`에 폴더를 지정하면 `~/.second-brain/` 대신 그 폴더의 `config.json`·`local.md`를 쓴다(설정 방법은 위 [환경변수 SECOND_BRAIN](#환경변수-second_brain)과 같다). AI 에이전트도 같은 환경변수를 받아야 하므로, 바꿨다면 에이전트 세션 안에서 `sb.py where`로 경로를 확인한다.

### local.md

예시 파일을 `~/.second-brain/local.md`로 복사해 고친다. 폴더가 아직 없으면(`init`·`setup` 전) 함께 만든다.

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force "$HOME\.second-brain" | Out-Null
if (-not (Test-Path "$HOME\.second-brain\local.md")) { Copy-Item "$HOME\.claude\skills\second-brain\local.example.md" "$HOME\.second-brain\local.md" }
```

```bash
# macOS / Linux / Windows Git Bash
mkdir -p ~/.second-brain
[ -e ~/.second-brain/local.md ] || cp ~/.claude/skills/second-brain/local.example.md ~/.second-brain/local.md
```

`local.md`가 이미 있으면 복사하지 않으므로(덮어쓰지 않는다) 다시 실행해도 된다. 예시로 처음부터 다시 시작하고 싶으면 기존 `local.md`의 이름을 바꿔 둔 뒤 실행한다.

예시에 있는 절:

| 절 | 적는 것 |
|---|---|
| 볼트 | 볼트 위치, Obsidian 볼트 루트가 더 위인지, 동기화 방식(예: Git 플러그인 자동 push → AI는 commit·push 안 함) |
| 더 읽어도 되는 곳 | 내가 지정할 때만 읽을 볼트 밖 원본 폴더 |
| 열지 않는 곳 | AI가 열면 안 되는 폴더·파일 |
| 태그 어휘 | 쓰는 태그 목록. 목록 밖 태그는 만들기 전에 묻는다 |
| 기록 정책 | 다시 쓸 사실을 확인하면 바로 기록할지, 끝에 제안만 할지 |
| 프로젝트 연결 | 작업 폴더(저장소) → 기록할 프로젝트 노트 |
| 검증 범위 라벨 | 해결 기록의 "검증"에 쓸 표현 |
| 자동 루틴 | 돌리고 있는 루틴과 시각. 루틴이 쓰는 블록을 수동 작업에서 중복으로 만들지 않게 한다 |

**확인**: `sb.py where`의 `local_md: ... exists=True`.

### config.json

`init`·`setup`이 `"vault"`를 저장하며 `~/.second-brain/config.json`을 만든다. 나머지 키는 필요할 때 직접 넣는다.

- **인코딩**: UTF-8로 저장한다(메모장 등이 붙이는 BOM이 있어도 된다). UTF-16이나 ANSI(한국어 Windows의 CP949 등)로 저장하면 `sb.py`가 `설정 파일을 UTF-8로 다시 저장하세요(PowerShell Out-File·Set-Content 기본값은 UTF-8이 아님): <경로>`를 출력하고 멈춘다. 메시지에 나온 파일을 인코딩을 고를 수 있는 편집기로 열어 UTF-8로 다시 저장한다.
- **형식**: JSON 형식이 틀리면 `설정 파일 형식 오류: <경로> (<틀린 위치>)`를 출력하고 멈춘다. 쉼표·따옴표를 고친 뒤 다시 실행한다.

모든 키를 넣은 예:

```json
{
  "vault": "C:/Notes/SecondBrain",
  "folders": {
    "fix": "40_Resources/Troubleshooting",
    "resource": "40_Resources/Reference"
  },
  "exclude": ["40_Resources/개인 서류"],
  "read_outside": ["../업무 일지"],
  "today_sources": {
    "업무 일지": "../업무 일지/%Y-%m-%d.md"
  },
  "utc_offset": 9
}
```

| 키 | 뜻 |
|---|---|
| `vault` | 볼트 경로. Windows에서는 `/`를 써도 되고, `\`를 쓰려면 `\\`로 적는다 |
| `folders` | 노트 종류별 폴더(볼트 기준). 종류: `daily`, `weekly`, `project`, `fix`, `resource`, `note`, `inbox`. 적지 않은 종류는 기본 폴더를 쓴다. `sb.py new`·`today`·`tasks`·`stale`에 적용되며, 최종 경로가 볼트 밖이면 거부한다(`../`, 외부 절대 경로, 볼트 밖을 가리키는 심볼릭 링크 포함) |
| `exclude` | `sb.py`가 열지 않을 폴더·파일. 볼트 기준 경로와 Obsidian 볼트 루트 기준 경로를 둘 다 받고, 대소문자를 가리지 않는다. `lint`·`tags`·`backlinks`·`tasks`·`stale`와 `new`의 같은 이름 확인에서 빠진다 |
| `read_outside` | `sb.py backlinks`가 볼트와 함께 읽을 볼트 밖 폴더(볼트 기준, 예: `"../업무 일지"`). 여기 없는 볼트 밖 파일은 `backlinks`가 읽지 않는다([볼트 루트가 더 위에 있을 때](#obsidian-볼트-루트가-더-위에-있을-때)) |
| `today_sources` | `sb.py today`가 같이 보여 줄 외부 원본 파일. `"이름": "경로 패턴"` |
| `utc_offset` | UTC 기준 시차(시간). 기본 9(한국 시간). 오늘 날짜와 `created` 시각에 쓴다 |

알아 둘 점:

- **`folders`를 바꾸면 볼트 쪽도 맞춘다.** 실제 폴더 이름, `AGENTS.md`의 폴더 표, Dataview 경로([고칠 파일 표](#obsidian-볼트-루트가-더-위에-있을-때))는 `sb.py`가 바꾸지 않는다. `daily`를 바꿔도 `weekly`는 따로 바꿔야 한다. 템플릿 폴더는 항상 `99_System/Templates`다.
- **`exclude`는 `sb.py`만 막는다.** AI가 그 폴더를 열지 않게 하려면 `AGENTS.md`의 "열지 않을 곳"에도 같은 경로를 적는다. `.obsidian`, `.trash`, `.git`과 이름에 토큰·비번·비밀번호·password·passwd·token·secret·credential이 든 파일, `.env`·`.pem`·`.key` 파일은 설정과 관계없이 항상 건너뛴다.
- **`today_sources`의 경로 패턴**은 Obsidian 볼트 루트(보통 볼트 폴더) 기준이고, 날짜는 Python `strftime` 기호로 쓴다: `%Y`(연도 4자리), `%m`(월 2자리), `%d`(일 2자리). 위 예에서 10월 15일이면 `../업무 일지/1015.md`를 가리킨다. `read_outside`는 볼트 기준이므로, Obsidian 볼트 루트가 볼트보다 위에 있으면 같은 폴더라도 두 키에 적는 경로가 달라진다. AI는 이 파일을 내가 "오늘 노트에 업무 일지 붙여줘"처럼 요청하고 `AGENTS.md`가 읽기를 허용할 때만 읽는다.

**확인**: `sb.py today`를 실행하면 설정이 반영된 경로가 보인다.

```text
date: 2026-10-15 (목)
now: 2026-10-15T09:42
iso_week: 2026-W42  start: 2026-10-12  end: 2026-10-18
prev: 2026-10-14  next: 2026-10-16
daily: C:\Notes\SecondBrain\10_Daily\2026-10-15.md  exists=False
weekly: C:\Notes\SecondBrain\10_Daily\Weekly\2026-W42.md  exists=False
업무 일지: C:\Notes\SecondBrain\..\업무 일지\1015.md  exists=True
```

## 요청별로 AI가 실제로 하는 일

아래 `sb`는 `python "<스킬 폴더>/scripts/sb.py"`를 줄인 것이다. "확인만", "찾아봐"라고 하면 AI는 아무것도 바꾸지 않고 찾아서 보고만 하고, 보고에 `볼트 변경: 없음(읽기 전용)`이라고 적는다.

| 이렇게 말하면 | AI가 하는 일 | 결과 |
|---|---|---|
| "세컨드 브레인 만들어줘" | 만들 위치를 묻는다(기본 제안 `~/Documents/SecondBrain`) → `sb init "<폴더>"` → Obsidian 설정(보관소로 열기, Dataview·Templater, 템플릿 폴더)을 안내한다 | 새 볼트 |
| "기존 볼트 연결해줘" | `sb setup "<폴더>"` → `AGENTS.md`가 없으면 스타터 예시를 보여 주고 고쳐 넣을지 묻는다. 템플릿이 없다는 경고가 나오면 Obsidian을 닫고 복사하라고 안내한다([이미 있는 볼트를 쓸 때](#이미-있는-볼트를-쓸-때)) | `~/.second-brain/config.json` |
| "오늘 노트 만들어줘" | `sb today` → 없으면 `sb new daily` → `sb tasks --older 2`로 이틀 넘은 미완료 할 일을 알린다(복사하지 않는다) | `10_Daily/YYYY-MM-DD.md` |
| "할 일 추가해줘: ○○ 금요일까지" | 오늘 끝낼 일은 오늘 노트 `## 할 일`에 `- [ ] ○○`로 적는다. 마감이 오늘이 아니거나 며칠 이어지는 일은 관련 진행 중(`status: active`) 프로젝트 노트 `## 할 일`에 `- [ ] ○○ 📅 YYYY-MM-DD`로 적는다(맞는 프로젝트가 없으면 오늘 노트에 📅와 함께). "금요일까지"는 `sb today --date`로 요일을 확인해 실제 날짜로 바꾸고, 해석한 날짜를 보고에 적는다. 미래 날짜의 일일 노트는 미리 만들지 않고, 같은 할 일을 두 곳에 적지 않는다(`sb tasks`로 먼저 확인) | 오늘 노트 또는 프로젝트 노트 |
| "볼트에 '○○' 프로젝트 만들어줘" | `sb new project "<이름>"` → `area`(예: `area: "[[업무]]"`)·`due`와 `## 목표 · 완료 조건`을 채운다. 며칠 이어지는 할 일은 이 노트 `## 할 일`에 둔다. 요청에 '볼트'를 넣어야 코드 프로젝트 만들기로 오해하지 않는다 | `20_Projects/` |
| "메모해 둬: ○○" | `sb new inbox "<짧은 제목>"`으로 만들고 한 말을 그대로 적는다. 분류는 하지 않는다 | `00_Inbox/` |
| "인박스 정리해줘" | 메모를 하나씩 읽고 분류 질문으로 옮긴다(지우고 새로 만들지 않고 이동). `type`·`area`·`tags`를 채우고 링크한다. 섞인 메모는 나누고, 같은 주제 노트가 있으면 합친다. 여러 노트로 나누거나 기존 노트에 합친 원본은 `90_Archive/`로 옮긴다. 애매하면 인박스에 두고 이유를 말한다 | "원래 이름 → 위치" 표 |
| "주간 리뷰 해줘" | `sb today`의 `iso_week`·`start`·`end`로 기간을 정한다 → 그 주 일일 노트·새 노트·진행 중 프로젝트를 읽는다 → `sb new weekly`(이미 있으면 빈 절만 채움) → 한 일·배운 것·막힌 것·다음 주 우선순위 3개 → `sb stale`로 2주 넘게 손대지 않은 프로젝트를 알린다(상태는 내가 정한다) | `10_Daily/Weekly/YYYY-Www.md` |
| "이거 해결 기록 남겨줘" | 증상과 원인 기제가 같은 기록이 있는지 먼저 찾는다 → 있으면 그 노트에 사례 추가, 없으면 `sb new fix "<증상 한 줄>"`. 증상이 비슷해도 원인이 다르면 새 노트를 만들고 서로 링크한다 → 현상·원인(확인/추정 구분)·변경·검증(어디까지 확인했는지)·출처. 제목에 비밀 파일 단어가 있으면 `sb new`가 거부하므로 다른 말로 짓는다(아래 주의) | `40_Resources/해결 기록/` |
| "참고 자료로 정리해줘" | `sb new resource "<주제>"` → 내 말로 요약, 원본 링크. 같은 주제가 있으면 합친다 | `40_Resources/참고 자료/` |
| "[[노트]]에서 노트 정제해줘" | 다시 쓸 생각 하나당 `sb new note "<한 문장 주장>"` → 본문 3~10줄, 출처 링크 필수, 추측은 `> 추측:` | `50_Notes/` |
| "볼트에서 ○○ 노트를 90_Archive로 옮겨줘" | 지우지 않고 `90_Archive/`로 옮긴다(옮기기만 하면 이름이 그대로라 링크는 깨지지 않는다). 이름까지 바꾸면 `sb backlinks "<옛 이름>"`으로 찾아 볼트 안 링크만 고친다 | `90_Archive/` |
| "볼트 기준으로 ○○ 알려줘" | 키워드 2~4개로 볼트 안에서만 찾는다(파일 이름 포함) → 걸린 부분과 링크 한 단계만 읽는다 → 결론과 근거 `[[노트]]`. 없으면 "볼트에 없음"이라고 먼저 말하고 일반 지식으로 보충한다 | 답변(읽기만) |
| "전에 이거 해결한 적 있나" | 해결 기록 → 참고 자료 → 프로젝트·보관 → 일일 노트 순으로 찾는다. 노트는 그 시점의 기록이라 지금과 다를 수 있다고 구분한다 | 답변(읽기만) |

쓰는 요청에는 공통으로 다음 순서를 지킨다.

1. **쓰기 전에 묻는다.** 기록할 대상(화면·파일·환경)이 정해지지 않았거나 찾은 증거가 내 말과 어긋나면, 후보 2~3개와 증거를 보여 주고 먼저 한 번 묻는다. 쓰고 나서 묻지 않는다.
2. **고치기 직전에 다시 읽는다.** 기존 노트는 고치기 바로 전에 다시 읽는다. 처음 읽은 뒤 파일이 바뀌었으면(Obsidian·다른 세션·자동 루틴) 편집만 다시 하지 않고 중복 확인·줄 상태·보고 내용을 처음부터 다시 판단한다. 지우기·덮어쓰기는 하지 않는다.
3. **실제 파일로 점검한다.** 쓴 파일을 다시 읽고 `sb lint "<절대 경로>" ...`로 점검한다. 출력의 `점검(지정한 파일) N개`가 바꾼 파일 수와 맞는지도 본다.
4. **점검한 뒤의 상태로 보고한다.** `파일(절대 경로) | 한 일(생성/추가/이동) | 연결한 노트` 표로 보고한다. 바꾼 파일에 원래 있던 문제는 기본으로 고치지 않고 목록으로 남기며, 확인한 것과 추정을 구분해 적는다.

## 다른 프로젝트 작업 중에 쓰기

스킬은 사용자 스킬 폴더에 설치되므로, 볼트와 상관없는 코드 저장소나 문서 폴더에서 일하는 세션에서도 쓸 수 있다. 이때 AI는 `sb where`로 얻은 **절대 경로**로 볼트 파일을 다룬다(상대 경로를 쓰면 지금 작업 폴더에 노트가 잘못 생긴다).

**문제를 해결한 직후**

1. 작업 세션에서 그대로 "이거 해결 기록 남겨줘"라고 한다.
2. AI가 대화에서 현상·원인·변경·검증을 모아 `40_Resources/해결 기록/<증상 한 줄>.md`를 쓰고, 관련 프로젝트나 영역 노트에 링크한다. `local.md`의 "프로젝트 연결" 표가 있으면 지금 작업 폴더에 맞는 프로젝트 노트를 쓴다.
3. 제목이 곧 검색 키다. "로그인 후 빈 화면이 뜬다"처럼 증상을 한 줄로 쓰면 나중에 찾기 쉽다.

> **주의**: 제목(파일 이름)에 토큰·비번·비밀번호·password·passwd·token·secret·credential을 쓰지 않는다. 이런 이름의 파일은 비밀정보가 들었을 수 있어 AI(`AGENTS.md` 규칙)와 `sb.py`가 열지 않고 건너뛰므로, 나중에 "전에 이거 해결한 적 있나"로 다시 찾을 수 없다. 그래서 `sb new`는 이런 단어가 든 제목을 `제목에 비밀 파일로 보이는 단어가 있어 검색·점검에서 빠집니다. 다른 말로 바꾸세요(예: 토큰 → 인증): <제목>`로 거부한다. 예: "API 토큰 만료로 로그인 실패" 대신 "인증 만료로 로그인 실패". 영어 단어는 단어 단위로 보므로 `Tokenizer`는 통과하지만, 한국어 `토큰`·`비번`·`비밀번호`는 다른 글자와 붙어 있어도 걸린다(`토큰화`도 거부).

기록하라고 하지 않아도, AI가 다시 쓸 만한 원인이나 환경 특성을 확인하면 `local.md`의 기록 정책을 따른다. 정책이 없으면 작업 끝에 "해결 기록으로 남길까요?"라고 한 줄 제안한다.

**비슷한 문제를 다시 만났을 때**

작업을 시작하기 전에 "전에 이거 해결한 적 있나"라고 묻는다. AI는 해결 기록부터 찾아 근거 노트 링크(다른 프로젝트 세션이면 절대 경로도)와 함께 답한다.

## 자동 루틴

스타터 볼트의 `99_System/Routines/`에는 사람이 없을 때 AI가 실행할 프롬프트 노트가 들어 있다. 각 파일은 질문하지 않고 `AGENTS.md` 규칙대로 끝까지 처리하며, 정해진 파일 외에는 고치지 않도록 쓰여 있다.

| 루틴 파일 | 권장 시각 | 하는 일 | 고치는 파일 |
|---|---|---|---|
| `아침 오늘 노트.md` | 평일 아침 | 오늘 노트를 만들고, 이틀 넘은 미완료 할 일과 진행 중 프로젝트를 오늘 노트에 알린다 | 오늘 노트 |
| `퇴근 정리.md` | 평일 저녁 | 오늘 노트 `## 기록`에 요약을 쓰고, 해결 기록·노트 정제 후보를 표시한다(오늘 노트가 없으면 아무것도 하지 않는다) | 오늘 노트 |
| `금요일 주간 리뷰.md` | 금요일 오후 | 인박스 메모 중 한 폴더로 그대로 옮기면 끝나는 것만 옮긴다. 나누기·합치기가 필요하거나 분류가 애매한 메모는 인박스에 두고 주간 노트에 "정리 후보"로만 적는다. 이번 주 주간 노트를 쓰고, 방치 프로젝트와 정제 후보도 주간 노트의 `## 🤖 정리 결과` 절에 적는다 | 인박스에서 그대로 옮긴 노트, 이번 주 주간 노트 |

"고치는 파일"의 정확한 범위는 각 루틴 파일의 마지막 항목이 기준이다. 금요일 루틴이 남긴 정리 후보는 내가 있을 때 "인박스 정리해줘"로 처리한다. 루틴은 평범한 문장으로 된 프롬프트라 고쳐서 써도 된다. 돌리기 시작하면 `local.md`의 "자동 루틴" 절에 시각을 적어 둔다.

어떤 방법이든 예약 작업에 넣는 내용은 같다.

- 작업 폴더: 볼트 폴더
- 프롬프트: `볼트의 99_System/Routines/아침 오늘 노트.md를 읽고 그대로 실행한다` (파일 이름만 바꿔 다른 루틴에 쓴다)

### 방법 1. Claude 데스크톱 앱의 예약 작업

쓰는 Claude 데스크톱 앱에 예약 작업 기능이 있다면, 새 예약 작업을 만들어 위 프롬프트를 넣고 작업 폴더를 볼트로, 반복을 원하는 요일·시각으로 정한다. 메뉴 이름과 설정 항목은 앱 버전에 따라 다르므로 앱의 도움말이나 공식 문서를 따른다.

### 방법 2. OS 스케줄러 + CLI 비대화 실행

운영체제의 예약 실행 도구(Windows 작업 스케줄러, macOS·Linux의 cron이나 launchd)로 에이전트 CLI를 비대화 모드로 실행한다.

- Claude Code: `claude -p "<프롬프트>"`가 응답을 출력하고 끝나는 비대화 실행이다. 이 모드에서는 권한 확인 창을 띄울 수 없으므로, 파일 수정 허용(예: `--permission-mode acceptEdits`)과 `sb.py` 실행 허용(`--allowedTools`)을 필요한 만큼만 정해 둔다.
- Codex: `codex exec "<프롬프트>"`. 기본은 읽기 전용이라 파일을 고치려면 `--sandbox workspace-write`가 필요하다.
- 정확한 옵션은 버전마다 바뀌므로 [Claude Code 문서](https://code.claude.com/docs/en/overview)와 Codex 공식 문서에서 확인한다.

cron 예시(평일 09:00, 실행해 보지 않은 예시다. 경로와 옵션은 내 환경에 맞게 바꾼다):

```bash
0 9 * * 1-5 cd "$HOME/Documents/SecondBrain" && /path/to/claude -p "볼트의 99_System/Routines/아침 오늘 노트.md를 읽고 그대로 실행한다" --permission-mode acceptEdits --allowedTools "Bash(python3 $HOME/.claude/skills/second-brain/scripts/sb.py where*)" "Bash(python3 $HOME/.claude/skills/second-brain/scripts/sb.py today*)" "Bash(python3 $HOME/.claude/skills/second-brain/scripts/sb.py new daily*)" "Bash(python3 $HOME/.claude/skills/second-brain/scripts/sb.py tasks*)" "Bash(python3 $HOME/.claude/skills/second-brain/scripts/sb.py lint*)" >> "$HOME/second-brain-routine.log" 2>&1
```

- `--permission-mode acceptEdits`는 파일 편집만 자동으로 허용한다. `sb.py` 실행(Bash)은 `--allowedTools`로 따로 허용하되, 루틴에 필요한 하위 명령만 허용한다. `init`·`setup`은 무인 루틴에 허용하지 않는다(노트에 섞인 신뢰할 수 없는 글이 볼트 설정을 바꾸게 하지 않기 위해서다). 허용하지 않으면 루틴이 `sb.py` 없이 날짜와 할 일을 직접 계산하게 되어 틀리기 쉽다.
- `--allowedTools` 규칙은 AI가 실제로 쓰는 명령 문자열의 앞부분과 맞아야 한다. 위 규칙의 `$HOME`은 cron의 셸이 내 홈 폴더 경로로 바꿔 넘긴다. 이 규칙은 `sb.py`를 그 경로로 부르는 명령만 허용하고, 다른 Python 스크립트는 허용하지 않는다. AI가 `python`으로 부르거나 경로를 따옴표로 감싸면 맞지 않을 수 있다. 처음에는 같은 명령을 터미널에서 직접 실행해 `sb.py` 실행이 거부되지 않았는지 출력에서 확인하고, 거부되면 규칙을 실제 명령 모양에 맞춘다.
- 이 옵션은 값을 여러 개 받으므로 프롬프트는 `-p` 바로 뒤에 두고 `--allowedTools`는 그 뒤에 둔다. 규칙 문법(`Bash(명령 *)`)은 버전에 따라 다를 수 있으니 `claude --help`와 Claude Code 문서의 권한(permissions) 설명에서 확인한다.

cron은 터미널과 PATH가 달라 `claude`를 못 찾을 수 있으니 실행 파일의 전체 경로를 쓴다(`which claude`로 확인). Windows 작업 스케줄러에서는 프로그램에 실행 파일 경로, 인수에 `-p "<프롬프트>"`와 옵션, 시작 위치에 볼트 폴더를 넣는다.

**안전하게 시작하기**: 처음 몇 번은 같은 명령을 터미널에서 직접 실행해 결과를 확인한다. 루틴이 고치는 파일 범위를 넓히지 않는다. 볼트를 git으로 백업하고 있으면 문제가 생겨도 되돌리기 쉽다. 루틴에서 git commit·push는 시키지 않는다.

## sb.py 명령 참고

`sb.py`는 Python 3.9+ 표준 라이브러리만 쓴다. 노트 내용은 판단하지 않고 기계적인 일만 한다.

매번 전체 경로를 치기 번거로우면 줄임 명령을 만든다(선택).

```powershell
# Windows: PowerShell 프로필($PROFILE)에 추가
function sb { python "$HOME\.claude\skills\second-brain\scripts\sb.py" @args }
```

- **먼저 실행 정책을 본다.** PowerShell 프로필은 스크립트 파일이라 실행 정책이 허용할 때만 실행된다. `Get-ExecutionPolicy`가 `Restricted`(Windows 데스크톱의 기본값)나 `AllSigned`를 출력하면 프로필이 실행되지 않으므로 이 방법은 쓰지 않고 전체 경로로 실행한다. 이 줄임 명령 때문에 실행 정책을 바꾸지 않는다.
- `RemoteSigned`처럼 허용하는 값이면, 프로필 파일이 아직 없을 수 있으니 `if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force }`로 만든 뒤(이미 있으면 아무것도 하지 않는다) `notepad $PROFILE`로 열어 위 줄을 붙여 넣는다. 새 PowerShell 창부터 `sb where`처럼 쓸 수 있다.
- 그래도 새 창을 열 때 "스크립트를 실행할 수 없으므로 ... 로드할 수 없습니다" 같은 오류가 나면 실행 정책이 프로필을 막고 있는 것이다. 방금 만든 프로필 파일이라면 지워서 오류를 없애고, 전체 경로로 실행한다.

```bash
# macOS / Linux: ~/.bashrc 또는 ~/.zshrc에 추가 (Windows Git Bash에서는 python3 대신 python)
alias sb='python3 ~/.claude/skills/second-brain/scripts/sb.py'
```

| 명령 | 하는 일 |
|---|---|
| `sb init <새 폴더>` | 스타터 볼트를 만들고 경로를 `~/.second-brain/config.json`에 저장한다. 이미 `.md` 노트가 있는 폴더는 거부한다. 경로가 너무 길어 만들지 못하면 더 짧은 폴더를 쓰라고 안내하고 멈춘다. 환경변수 `SECOND_BRAIN`이 설정되어 있으면 그쪽 볼트가 계속 쓰인다고 경고한다 |
| `sb setup <기존 볼트>` | 기존 볼트 경로를 저장한다. `AGENTS.md`가 없으면 스타터 `AGENTS.md`의 절대 경로를, 템플릿이 없으면 복사해 올 폴더(설치된 스킬의 `assets/starter-vault/99_System/Templates`)를 알려 준다. `init`처럼 `SECOND_BRAIN` 경고도 한다 |
| `sb where` | 지금 쓰는 볼트(`vault`), Obsidian 볼트 루트(`obsidian_root`), `AGENTS.md`(`agents_md`)·`config.json`(`config`)·`local.md`(`local_md`)의 위치와 존재 여부, 지금 실행한 스킬 폴더(`skill`). 볼트가 설정되지 않았으면 이 `sb.py`의 절대 경로로 `init`·`setup` 명령을 안내한다 |
| `sb today [--date YYYY-MM-DD]` | 날짜와 요일, 현재 시각, ISO 주차와 그 주 월~일, 어제·내일 날짜(`prev`·`next`), 일일·주간 노트 경로와 존재 여부, `today_sources`. 날짜 형식이 틀리면 `날짜는 YYYY-MM-DD 형식이어야 합니다: <값>`으로 멈춘다 |
| `sb render <템플릿> [--title T]` | 템플릿의 Templater 구문을 실제 값으로 바꾼 본문을 출력한다(파일은 쓰지 않는다). 템플릿 이름: `Daily`(제목은 `YYYY-MM-DD`), `Weekly`(제목은 `YYYY-Www`), `Project`, `Fix`, `Resource`, `Note`, `Inbox` |
| `sb new <종류> [제목] [--date D] [--dry-run]` | 템플릿으로 새 노트를 만든다. `daily`·`weekly`는 제목을 생략하면 오늘(또는 `--date`) 기준으로 정한다. 나머지는 제목이 필요하다(공백만 있으면 `제목이 필요합니다.`). 볼트 어디든 같은 이름(대소문자 무시)이 있거나, 제목에 금지 문자나 비밀 파일 단어가 있으면 거부한다(아래). 경로가 너무 길어 파일을 만들지 못하면 제목을 줄이거나 볼트를 더 짧은 경로로 옮기라고 안내한다. `--dry-run`은 경로와 내용만 출력한다 |
| `sb tasks [--older N]` | 일일 노트와 `status: active` 프로젝트의 미완료 `- [ ]` 할 일. 비밀 파일 이름과 `exclude` 경로는 건너뛴다. `--older N`은 N일보다 오래된 일일 노트 항목만 |
| `sb stale [--days 14]` | 파일 수정 시각 기준으로 N일 넘게 손대지 않은 `status: active` 프로젝트. 비밀 파일 이름과 `exclude` 경로는 건너뛴다 |
| `sb tags` | frontmatter의 `tags`에 적은 태그와 개수(`99_System` 제외). 한 줄 목록(`['a', "b"]`)과 여러 줄 목록의 항목은 양끝의 같은 따옴표를 벗겨 집계한다. 본문의 `#태그`는 세지 않는다 |
| `sb backlinks <노트 이름>` | 그 노트를 `[[링크]]`하는 파일. `.md` 확장자 유무와 대소문자를 구분하지 않는다. 볼트와 `config.json`의 `read_outside` 폴더만 읽고, 볼트 밖 파일은 "볼트 밖(고치지 말고 보고)"으로 표시한다 |
| `sb lint [파일...]` | 형식 점검. 링크 존재 여부와 고아 노트 판정은 `.md` 확장자 유무와 대소문자를 구분하지 않는다. 파일을 주지 않으면 볼트 전체. 없는 파일을 주면 `파일 없음: <경로>`로 멈춘다 |

`new`의 종류와 기본 폴더:

| 종류 | 템플릿 | 기본 폴더 | 파일 이름 |
|---|---|---|---|
| `daily` | `Daily` | `10_Daily` | `YYYY-MM-DD.md` |
| `weekly` | `Weekly` | `10_Daily/Weekly` | `YYYY-Www.md` |
| `project` | `Project` | `20_Projects` | `<제목>.md` |
| `fix` | `Fix` | `40_Resources/해결 기록` | `<제목>.md` |
| `resource` | `Resource` | `40_Resources/참고 자료` | `<제목>.md` |
| `note` | `Note` | `50_Notes` | `<제목>.md` |
| `inbox` | `Inbox` | `00_Inbox` | `<제목>.md` |

제목에는 파일 이름에 쓸 수 없는 `/ \ : * ? " < > |`와 `[[링크]]`를 깨뜨리는 `# ^ [ ]`를 쓸 수 없다(`제목에 / \ : * ? " < > | # ^ [ ] 를 쓸 수 없습니다(파일 이름·링크가 깨짐): <제목>`). 토큰·비번·비밀번호·password·passwd·token·secret·credential이 든 제목도 거부된다. 영어 단어는 단어 단위로 보고(`Tokenizer`는 통과), 한국어는 글자가 붙어 있어도 걸린다(`토큰화`도 거부)([주의](#다른-프로젝트-작업-중에-쓰기)).

`lint`가 보는 것: frontmatter가 있는지, frontmatter 값의 따옴표 없는 `[[링크]]`(예: `area: [[업무]]` → `frontmatter 'area'의 [[링크]]에 따옴표 필요`), `type` 값, `created` 형식(`YYYY-MM-DDTHH:mm`), 프로젝트 `status`(`active`·`done`·`paused`), 첫 제목(`# `)과 파일 이름이 같은지(주간 노트 제외), 파일 이름 금지 문자, 남은 `<%`·`[[undefined]]`·frontmatter 값 `undefined`, 비밀정보로 보이는 문자열, 깨진 `[[링크]]`, 고아 노트(들어오고 나가는 링크가 없는 노트. 인박스·일일·주간 노트는 제외). 날짜 링크(`[[YYYY-MM-DD]]`)는 일일·주간 노트에서만 아직 없는 날짜를 가리켜도 건너뛰고, 다른 노트에서는 그 날짜의 노트가 없으면 깨진 링크로 잡는다. 본문의 제목·링크 자리에 들어간 `undefined`나 `Invalid date`는 "제목(H1) ≠ 파일 이름"이나 "깨진 링크"로만 보이고, 주간 노트의 `start`·`end` 값과 형식은 맞지만 틀린 `created` 값은 보지 않는다. `99_System/`과 `AGENTS.md`·`CLAUDE.md`·`GEMINI.md`는 건너뛰고 개수 N에도 넣지 않는다(파일을 지정했으면 `건너뜀(점검 대상 아님: ...)` 줄을 출력한다 — 템플릿을 고쳤으면 `sb.py new`로 노트를 하나 만들어 그 노트를 점검한다). `exclude`에 걸린 경로와 이름에 비밀 단어가 든 파일·폴더는 읽지 않고 `제외된 경로(읽지 않음)`만 출력한다. 문제마다 `경로<탭>내용`을 출력하고 마지막 줄에 `점검(볼트 전체) N개, 문제 M건`(파일을 지정했으면 `점검(지정한 파일) N개, 문제 M건`)을 쓴다. 문제가 있으면 종료 코드가 1이다.

**템플릿을 고칠 때**: `sb.py`가 바꿀 수 있는 Templater 구문은 다음뿐이다. 이 밖의 구문을 넣으면 `처리할 수 없는 Templater 구문`으로 멈추고 파일을 쓰지 않는다.

| 구문 | 값 |
|---|---|
| `tp.file.title` | 노트 제목 |
| `tp.date.now("FMT")` | 지금 시각 |
| `tp.date.now("FMT", N, tp.file.title, "YYYY-MM-DD")` | 제목 날짜에서 N일 뒤(음수면 앞) |
| `moment(tp.file.title, "GGGG-[W]WW", true).startOf("isoWeek").format("FMT")` | 제목 주차의 월요일(`endOf`면 일요일) |

`FMT`에는 `YYYY`, `MM`, `DD`, `HH`, `mm`과 `T`, `-`, `:`만 쓴다.

## 문제 해결

### 스킬이 불리지 않는다

- 설치 위치에 `SKILL.md`가 있는지 확인한다([설치 확인](#설치-확인)).
- 설치 전에 열어 둔 세션이라면 새 세션을 시작한다.
- 요청에 "세컨드 브레인", "볼트", "해결 기록", "오늘 노트"처럼 스킬이 알아듣는 말을 넣는다.
- 직접 부른다. Claude Code는 `/second-brain 오늘 노트 만들어줘`처럼 쓴다. Codex는 버전에 따라 `/skills`나 `$`로 스킬을 고른다.
- Codex에서만 안 보이면 `~/.agents/skills/second-brain/SKILL.md`가 있는지 확인하고(`-Codex`·`--codex`로 설치했는지), Codex 공식 문서에서 지금 버전의 사용자 스킬 폴더를 확인한다([스킬 설치](#스킬-설치)).

### 볼트 경로·설정 오류

| 메시지·증상 | 원인과 해결 |
|---|---|
| `볼트 경로가 설정되지 않았습니다.` | `~/.second-brain/config.json`이 없거나 `"vault"`가 비어 있다. `init`이나 `setup`을 한 번 실행하거나 `SECOND_BRAIN`을 설정한다. 환경변수 `SECOND_BRAIN_HOME`을 설정했다면 `~/.second-brain/`이 아니라 그 폴더의 `config.json`을 읽으므로, 그 값이 맞는지도 본다 |
| `볼트 폴더가 없습니다: <경로>` | 볼트를 옮기거나 이름을 바꿨다. `setup`으로 새 경로를 저장한다. 환경변수 `SECOND_BRAIN`이 옛 경로를 가리키고 있지 않은지도 본다(환경변수가 우선한다) |
| `설정 파일 형식 오류: <경로> (...)` | `config.json`의 JSON 문법이 틀렸다(빠진 따옴표, 마지막 항목 뒤 쉼표 등). 괄호 안의 줄·칸 위치를 보고 고친다 |
| `설정 파일을 UTF-8로 다시 저장하세요(...): <경로>` | `config.json`이 UTF-16이나 ANSI(CP949 등)로 저장됐다. 그 파일을 인코딩을 고를 수 있는 편집기로 열어 UTF-8로 다시 저장한다(BOM은 있어도 된다) |
| `주의: 환경변수 SECOND_BRAIN(<경로>)이 설정되어 있어 그쪽 볼트가 계속 쓰입니다.` | `init`·`setup`으로 저장한 경로보다 환경변수가 우선한다. 저장한 볼트를 쓰려면 [환경변수를 지운다](#환경변수-second_brain) |
| `이미 노트가 있는 폴더입니다(덮어쓰지 않음)` | `init`은 빈 폴더에만 쓴다. 그 폴더를 쓰려면 `setup`을 쓴다 |
| `볼트를 만들지 못했습니다: ...` | Windows에서 전체 경로가 너무 길면 생긴다. `C:\Notes\SecondBrain`처럼 짧은 폴더로 다시 `init`한다. 실패한 폴더에 일부 폴더가 만들어졌을 수 있으니 확인하고 정리한다 |
| `템플릿이 없습니다: <경로>` | 볼트에 그 템플릿 파일이 없다. [이미 있는 볼트를 쓸 때](#이미-있는-볼트를-쓸-때)의 2번대로 Obsidian을 닫고 복사한다 |
| `제목에 / \ : * ? " < > \| # ^ [ ] 를 쓸 수 없습니다(...)` | 제목에서 그 기호를 빼거나 글자로 바꾼다(예: `C# 빌드 오류` → `CSharp 빌드 오류`) |
| `노트를 만들지 못했습니다: ...` | 대개 Windows에서 전체 경로가 너무 길 때다. 제목을 줄이거나 볼트를 더 짧은 경로로 옮긴다 |
| `날짜는 YYYY-MM-DD 형식이어야 합니다: <값>` | `--date`에 `2026-10-15`처럼 연-월-일을 넣는다 |
| `파일 없음: <경로>` | `lint`에 준 파일 경로가 틀렸다. 따옴표로 감싼 절대 경로로 다시 준다 |
| `can't open file '...~...sb.py'` (Windows) | Windows PowerShell은 `python`에 넘기는 `~`를 풀지 않는다. `~` 대신 `$HOME`을 쓴다 |
| 노트가 볼트가 아닌 작업 폴더에 생겼다 | AI가 상대 경로를 썼다. `sb where`의 경로(절대 경로)로 옮겨 달라고 하고, 잘못 생긴 파일을 볼트로 옮긴다 |
| `python`을 찾을 수 없다 | Windows는 `py`, macOS·Linux는 `python3`로 실행한다. 반대로 Windows Git Bash에서는 `python3`가 실행되지 않을 수 있으니 `python`을 쓴다. AI에게도 어떤 명령을 쓰는지 알려 준다 |

### 한글이 깨진다

- **터미널 출력이 깨질 때**: `sb.py`는 UTF-8로 출력한다. Windows 터미널에서 깨지면 PowerShell에서는 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`, 명령 프롬프트(cmd)에서는 `chcp 65001`을 먼저 실행한다.
- **노트나 `config.json`이 깨질 때**: 파일이 UTF-8이 아닌 인코딩으로 저장된 것이다. Windows PowerShell 5.1의 `Set-Content`·`Out-File`·`>`는 기본 인코딩이 UTF-8(BOM 없음)이 아니므로 노트를 쓰는 데 쓰지 않는다. 깨진 파일은 인코딩을 고를 수 있는 편집기로 열어 BOM 없는 UTF-8로 다시 저장한다. `config.json`은 BOM이 붙은 UTF-8까지는 읽지만, UTF-16이나 ANSI로 저장되면 `sb.py`가 `설정 파일을 UTF-8로 다시 저장하세요(...): <경로>`를 출력하고 멈춘다. 그 경로의 파일을 UTF-8로 다시 저장한다.
