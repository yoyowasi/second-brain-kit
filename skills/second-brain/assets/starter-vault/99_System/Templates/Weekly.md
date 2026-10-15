---
type: weekly
start: <% moment(tp.file.title, "GGGG-[W]WW", true).startOf("isoWeek").format("YYYY-MM-DD") %>
end: <% moment(tp.file.title, "GGGG-[W]WW", true).endOf("isoWeek").format("YYYY-MM-DD") %>
tags: []
created: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
---
# <% tp.file.title %> 주간 리뷰

## 한 일
- 

## 배운 것
- 

## 막힌 것 · 미결
- 

## 다음 주 우선순위
1. 
2. 
3. 

## 이번 주에 만든 노트
```dataview
TABLE type, file.folder AS "위치"
FROM "20_Projects" OR "30_Areas" OR "40_Resources" OR "50_Notes"
WHERE file.cday >= date(this.start) AND file.cday <= date(this.end)
SORT file.ctime DESC
```
