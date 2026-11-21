# 놓칠뻔 (sw-dev-project) — Claude Code 작업 지침

팀 이김조 3명이 각자 Claude Code로 이 저장소를 동시에 작업한다. 이 파일은 세 사람의 Claude가 같은 규칙을 따르게 하려는 것이다.
**공개 저장소다.** 개인정보, API 키, 강의자료를 커밋하지 않는다.

## 서비스
학과·외부 기관 공지(장학금·공모전·행사)를 모아, 경상국립대 재학생의 학적 프로필로 지원 자격을 자동 판정하고 근거와 함께 보여 주며 마감 임박 알림을 보내는 서비스.
FastAPI + Jinja2 + SQLite (팀 결정 2026-11-21), 수집 requests + BeautifulSoup + RSS, 추출 Gemini(대안 Anthropic), 판정 규칙 기반, 스케줄 APScheduler 30분(웹 서버 안에서, uvicorn worker 1개).

## 먼저 읽을 것
- `docs/CODING_STANDARD.md` : 이름 규칙, 설계 대응 주석, 계층·패키지 의존 규칙. **코드를 쓰기 전에 반드시 읽는다.**
- `docs/STRUCTURE.md` : 폴더 구조, 결정, 남은 일(5절), 담당표(6절)
- `docs/mapping/` : 함수명 맵핑 테이블 (설계 연산 ↔ 코드 이름)
- 설계 기준(텍스트판): `docs/놓칠뻔_클래스다이어그램_v4_텍스트판.txt`, `docs/15_시퀀스다이어그램_v4_텍스트판.txt`, `docs/17_패키지다이어그램_최종_텍스트판.txt`

## 설계는 고정, 코드를 맞춘다
- 유스케이스 6개(UC1 로그인, UC2 프로필 입력, UC3 관심 출처 등록, UC4 공지 수집·조건 추출, UC5 지원 가능 공고 조회, UC6 마감 임박 알림), 클래스 33개(경계 9, 제어 13, 실체 11), 패키지 6개는 **확정**이다.
- 설계 문서(`docs/*_텍스트판.txt`)를 고치지 않는다. 코드와 설계가 다르면 코드를 설계에 맞춘다.
- 설계대로는 구현이 안 되는 곳을 찾으면 고치지 말고 사용자에게 알린다(팀이 결정한다). 맵핑 테이블 비고란에 적는다.
- 판정 결과 실체는 없다. 판정 엔진이 요청마다 판정한다. '모집 공고 아님'은 판정이 아니다(판정은 지원 가능·지원 불가·확인 필요 세 가지).
- 학적 프로필은 소속 대학·학과·학년·재학 상태 4개만. 평점·소득분위는 받지 않고, 그런 조건이 있는 공지는 "기타 조건"으로 남겨 "확인 필요"로 판정한다.
- 알림 채널은 UC6에서 조회만 한다. 채널 입력 기능은 만들지 않는다.
- 첨부파일은 내려받지 않고 링크만 저장한다.

## 계층과 패키지
- `app/hci/` 화면 6개 → `app/pd/<패키지>/` 제어·실체·외부 연동 → `app/dm/` DB. import는 이 방향으로만.
- PD 패키지: `user`, `source`, `collect`, `notice`, `notify`, `external`. 패키지끼리 import는 패키지 다이어그램의 의존 10개만 허용. 화면 모듈도 소속 패키지(`STRUCTURE.md` 1절 표)로 같은 규칙을 따른다. `hci/common.py`는 사용자 패키지만 import 한다.
- 표에 없는 화면 모듈이나 `app/pd` 아래의 모르는 패키지는 위반이다. 새 화면을 만들어야 하면 사용자에게 먼저 알린다.
- `tests/test_architecture.py`가 이 규칙을 검사하며, 위반이 있으면 안 된다. 이 테스트를 끄거나 예외를 추가하지 않는다. 예외가 필요해 보이면 고치지 말고 사용자에게 알린다(팀 결정).
- 제어·실체는 모듈 함수다. 상태가 있는 `CollectCtl`·`CollectScheduler`만 클래스(인스턴스 `collector`·`scheduler`).
- 경계 클래스(외부 연동)는 창구만, 판단은 제어가 한다.
- 다른 패키지의 값이나 시연 정보는 `hci/common.py`의 `register_footer`·`register_nav`·`register_panel`로 함수를 등록해 화면에 끼운다.
- 코드의 이름(함수·클래스·모듈·템플릿)은 맵핑표(`docs/mapping/`)가 기준이다. 이름을 바꾸거나 설계 연산을 새로 구현하면 같은 PR에서 맵핑표도 고친다.
- 설계 외 공개 함수를 만들면 코드에 `# 설계 외: 이유`를 달고 맵핑표에도 적는다. 설계 연산을 구현한 함수(화면 라우트 포함)에는 연산 표기를 주석으로 단다.
- 시연 전용 코드는 `app/demo/`에만 둔다(DEMO_MODE=1일 때만 `main.py`가 설치). 본 코드는 `app.demo`를 import 하지 않는다.

## 동시 작업 규칙 (중요)
- **사용자가 맡긴 영역 밖은 고치지 않는다.** 영역은 `STRUCTURE.md` 6절 담당표 기준이다. `app/hci/`와 템플릿은 패키지 폴더가 아니라 **파일 단위**로 나뉜다. 다른 영역을 고쳐야 하면 고치지 말고 무엇을 왜 고쳐야 하는지 사용자에게 알린다(담당표·남은 일에 적힌 교차 수정은 예외, 그 영역 담당이 리뷰).
- 공용 파일(`app/main.py`, `app/config.py`, `app/dm/schema.sql`, `requirements.txt`, `pyproject.toml`, `tests/conftest.py`, `tests/test_architecture.py`, `docs/`(단 `docs/mapping/`은 제외), `README.md`, `run.py`, `run.bat`, `.env.example`, `.gitignore`)은 담당자만 고친다. 담당자가 아니면 사용자에게 알린다.
- 다른 사람이 쓰는 공개 함수 이름을 바꾸면 그 호출부 전체가 깨진다. 이름을 바꿀 때는 맵핑 테이블을 먼저 고치고, 호출하는 다른 패키지 목록을 사용자에게 알린다.
- 맵핑 테이블은 자기 패키지 파일(`docs/mapping/<패키지>.md`)만 고친다.

## Git
- `main`에 직접 커밋·push 하지 않는다. `feature/<기능이름>` 브랜치에서 작업한다.
- 작업 전에 `git pull origin main`. PR 전에 다시 받아 충돌을 먼저 해결한다.
- 커밋 메시지: `[US-01] 관심 출처 등록 화면 추가` 형식. 백로그 항목이 없으면 `[REFACTOR]`, `[DOCS]`, `[TEST]`, `[CHORE]`.
- 폴더 이동·포맷과 로직 변경을 한 커밋에 섞지 않는다.
- 커밋·push·PR 생성은 사용자가 시킬 때만 한다.
- `.env`, `data/`, `.venv/`를 커밋하지 않는다.

## 확인 명령
```bash
pip install -r requirements.txt ruff
ruff format <내 담당 경로>
ruff check <내 담당 경로> --fix
ruff check .
pytest -q            # 한글 Windows에서 인코딩 문제가 나면 PYTHONUTF8=1
python run.py        # Windows는 py run.py
```
포맷과 `--fix`는 자기 담당 경로에만 돌린다(전체에 돌리면 다른 사람 파일까지 바뀌어 충돌한다). `ruff check .`(검사만)는 전체에 돌린다.
PR 전에 `ruff check .`(위반 0건)와 `pytest`가 모두 통과해야 한다. 테스트 수가 줄면 안 된다.

## 답변 방식
- 한국어로 답한다. 설계 이름(한글)과 코드 이름(영어)을 함께 적는다. 예: "수집 제어(`pd/collect/collect_ctl.py::CollectCtl.start`)".
- 직접 실행해 확인하지 않은 것은 확인했다고 쓰지 않는다.
