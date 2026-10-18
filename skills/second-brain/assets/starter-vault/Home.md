---
type: system
tags: []
created: 2026-10-15T09:00
---
# 세컨드 브레인 홈

> 적고 → 분류하고 → 연결하고 → 다시 쓴다. 볼트 규칙은 [[AGENTS]]에, 애매할 때의 기준은 [[나의 판단 방식]]에 있다.

**영역**: [[업무]] · [[학습]] · [[건강]] · [[재무]]

> [!tip] 아래 목록은 Dataview 플러그인을 켜야 보인다. 처음이면 [[처음 써 보는 메모]]부터 열어 본다.

> [!warning] Templater를 쓴다면
> - 템플릿 폴더는 `99_System/Templates`로 지정한다.
> - Obsidian이 켜진 동안 템플릿 파일을 밖에서 복사해 넣지 않는다. 구문이 그 자리에서 실행되어 템플릿이 망가질 수 있다.
> - 주간 노트를 Obsidian에서 직접 만들 때는 파일 이름을 먼저 `2026-W42`처럼 지은 뒤 템플릿을 적용한다. 이름이 이 형식이 아니면 `start`·`end` 날짜가 잘못 채워진다.

## 📥 인박스 (정리 대기)
```dataview
LIST
FROM "00_Inbox"
SORT file.ctime ASC
```
> 🤖 이름에 `dream`이 든 노트는 Claude가 대화에서 고른 규칙 제안이다(Claude Code hook을 설치했을 때). Claude Code에서 `/inbox`로 승인·거절한다.

## 🗒️ 최근 세션 일지 (자동)
```dataview
LIST
FROM "10_Daily/Journal"
SORT file.name DESC
LIMIT 5
```

## 🚀 진행 중 프로젝트
```dataview
TABLE area, due, file.mtime AS "최근 수정"
FROM "20_Projects"
WHERE status = "active"
SORT due ASC
```

## ✅ 열린 할 일 (일일 노트 + 진행 중 프로젝트 + 저장소 노트)
```dataview
TASK
FROM "10_Daily" OR "20_Projects" OR "40_Resources/저장소"
WHERE !completed AND text != "" AND (type = "daily" OR (type = "project" AND file.frontmatter.status = "active") OR type = "repo")
GROUP BY file.link
```

## 🌱 최근 영구 노트
```dataview
LIST
FROM "50_Notes"
SORT file.ctime DESC
LIMIT 10
```

## 💤 2주 넘게 손대지 않은 진행 중 프로젝트
```dataview
LIST
FROM "20_Projects"
WHERE status = "active" AND file.mtime < date(today) - dur(14 days)
```

## AI에게 이렇게 부탁하기
Claude Code·Codex 같은 AI 에이전트에서 이 볼트 폴더를 열거나, second-brain 스킬을 설치한 세션에서 이렇게 말한다.
- `메모해 둬: ○○` — 인박스에 적는다
- `인박스 정리해줘`
- `오늘 노트 만들어줘`
- `할 일 추가해줘: ○○ 금요일까지`
- `주간 리뷰 해줘`
- `이거 해결 기록 남겨줘`
- `참고 자료로 정리해줘`
- `[[노트]]에서 노트 정제해줘`
- `볼트 기준으로 ○○ 알려줘`
- `전에 이거 해결한 적 있나`
- `기억해: ○○` / `브레인에 넣어` (어느 프로젝트 세션에서든)
- `세컨드 브레인 점검` (깨진 링크·고아·남은 충돌·낡은 내용 점검. hook을 설치했으면 7일 넘을 때 Claude가 먼저 권한다)
- Claude Code 전용: `/inbox` (인박스·dream 규칙 제안 승인, 함께 보려면 `/inbox 같이`) · `/init-project ~/code/shop-web` (저장소 노트)

자동 목록: `99_System/색인.md` · 작업 기록: `99_System/브레인 로그.md` (처음 `sb.py index`·`sb.py log`를 실행할 때 생긴다)
