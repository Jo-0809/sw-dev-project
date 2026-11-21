# recordings

- `web/` : 경상국립대 게시판의 실제 응답. 수집기 v4가 2026-10-11 21:37 에 저장한 20개 파일을 그대로 가져왔다 (`_meta.json` origin=captured).
  `FETCH_MODE=replay` 일 때 이 파일을 재생한다. 학교 네트워크에서 `FETCH_MODE=record` 로 실행하면 새 응답으로 덮어쓴다.
- `llm/<제공자>/` : LLM 응답 녹화. 같은 공지·같은 모델·같은 질문(PROMPT_VERSION)이면 다시 부르지 않고 재생한다.
  파일에는 응답 JSON, 모델 이름, 녹화 시각, 걸린 시간만 있다 (API 키 없음). 이 판에는 녹화가 없다 (키가 없어서 호출하지 못함).
