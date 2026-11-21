"""<<control>> 조건 추출 제어 — LLM 호출·재시도, 근거 대조, 공지 상태 결정 (UC4 정상 5~7, 대안 3, 예외 2).
흐름 번호는 LMS 최종본 놓칠뻔_중간발표자료_FINAL.pdf (2026-10-11 23:27) 04-2·09-1 명세서 기준.

추출 방법
  1) LLM (Gemini 또는 Anthropic, .env 의 LLM_PROVIDER)
       - 같은 공지의 녹화가 있으면 녹화 재생 (LLM_MODE=auto/replay), 없으면 API 호출 후 녹화
       - 호출이 실패하면 최대 MAX_RETRY(3)회 시도, 그래도 실패하면 '확인 필요' (예외 2)
  2) LLM을 쓸 수 없을 때 (키도 녹화도 없음)
       - 대체 결과 제공자가 등록돼 있으면 그것 (시연 모드에서 app/demo 가 등록: 예시 결과 → 규칙 기반)
       - 없으면 (운영) '확인 필요' + 'LLM 미설정'. 조건을 지어내지 않는다
어느 방법이든 결과는 근거 대조기를 거친다.

공지 상태
  모집 공고 아님 : 모집 공고가 아니라고 판별 (대안 3)
  확인 필요      : 조건을 못 찾음(대안 3) / 원문에 없는 값(정상 7) / LLM 3회 실패(예외 2) / LLM 미설정
                   / 본문이 이미지(수집 단계) / 추출 중 예상 못 한 오류(수집 제어가 처리)
  추출 완료      : 근거 대조를 통과한 조건·마감일 저장
"""

from ... import config
from ..external import llm_client
from ..notice import condition, notice
from . import verifier

MAX_RETRY = config.LLM_MAX_RETRY  # 최대 재시도 횟수 = 3
NO_LLM_NOTE = "LLM 미설정 (API 키·녹화 없음) — 조건을 추출하지 않음, 원문 확인"

_example_provider = None


def set_example_provider(fn):  # 설계 외: 시연용 대체 결과 주입
    """LLM을 쓸 수 없을 때의 대체 결과 제공자를 등록한다. fn(공지) → (응답, 추출 방법 문구) 또는 None.
    시연 모드에서만 app/main.py 가 app/demo 의 제공자를 넣는다. 이 모듈은 app.demo 를 불러오지 않는다."""
    global _example_provider
    _example_provider = fn


# ---------------------------------------------------------------- 상태 결정
def decide_status(response, body, title=""):  # 설계 외: 상태 결정 (클래스 다이어그램 v4에는 +추출한다(공지)만 있음)
    """LLM 응답(또는 대체 결과)과 본문으로 공지 상태를 정한다. DB를 쓰지 않아 채점(app/demo/evaluation.py)에서도 쓴다.
    클래스 목록의 책임 '상태 결정'을 맡는 함수다. 채점이 직접 부르므로 공개 이름으로 둔다 (_ 예외를 늘리지 않으려고)."""
    if not response.get("is_recruitment", True):  # 대안 3: 모집 공고 아님
        return {
            "status": notice.NOT_RECRUIT,
            "conditions": [],
            "deadline": None,
            "deadline_evidence": None,
            "note": "모집 공고가 아닌 공지",
        }
    checked = verifier.verify(response, body, title)  # 대조한다(응답, 본문) : 검증 결과
    conds = [c for c in checked["conditions"] if c.get("item") in llm_client.ITEMS and c.get("value")]
    unverified = [c for c in conds if not c["verified"]]
    deadline = response.get("deadline") if checked["deadline_verified"] else None
    deadline_ev = response.get("deadline_evidence") if deadline else None
    if not conds:
        status, note = notice.CHECK, "공지 본문에서 참여 조건을 찾지 못함"
    elif unverified:
        status = notice.CHECK
        note = "근거 대조 실패: " + ", ".join(
            f"{c['item']} '{c['value']}' ({c.get('why') or '원문에 근거 없음'})" for c in unverified
        )
    else:
        status, note = notice.DONE, None
    if response.get("deadline") and not deadline:
        note = (note + " / " if note else "") + "마감일이 근거 문장과 맞지 않음 (원문에 없거나 날짜·시각이 다름)"
    return {"status": status, "conditions": conds, "deadline": deadline, "deadline_evidence": deadline_ev, "note": note}


def _method_text(info):
    name = llm_client.provider_name(info["provider"])
    if info["how"] == "replay":
        return f"LLM 녹화 재생 · {name} {info['model']} (녹화 {info['recorded_at']})"
    return f"LLM · {name} {info['model']} ({info['latency_ms']} ms, 녹화함)"


def run_llm(title, body, provider=None, mode=None):  # 설계 외: LLM 호출 + 재시도 (채점에서도 씀)
    """(응답, 정보, 오류). 키도 녹화도 없으면 (None, None, None). MAX_RETRY회 모두 실패하면 (None, None, 마지막 오류)."""
    last_err = None
    for _ in range(MAX_RETRY):
        try:
            data, info = llm_client.extract_conditions(title, body, provider=provider, mode=mode)
            return data, info, None
        except llm_client.LLMUnavailableError:
            return None, None, None
        except llm_client.LLMError as e:
            last_err = e
    return None, None, last_err


# ---------------------------------------------------------------- 추출 흐름
def extract(notice_id):  # 추출한다(공지)
    n = notice.get(notice_id)
    if n is None:
        return
    response, info, err = run_llm(n["title"], n["body"])
    if err is not None:  # 예외 2: 3회 실패 → 확인 필요
        notice.save_result(
            notice_id,
            notice.CHECK,
            method=f"LLM · {llm_client.provider_name()}",
            note=f"LLM {MAX_RETRY}회 실패 ({err})",
        )
        condition.save_all(notice_id, [])
        return
    if response is not None:
        method = _method_text(info)
    else:
        fallback = _example_provider(n) if _example_provider else None
        if fallback is None:  # 운영: 대체 결과 없음 → 확인 필요 (지어내지 않음)
            notice.save_result(notice_id, notice.CHECK, method="추출 안 함", note=NO_LLM_NOTE)
            condition.save_all(notice_id, [])
            return
        response, method = fallback
    r = decide_status(response, n["body"], n["title"])
    condition.save_all(notice_id, r["conditions"])
    notice.save_result(
        notice_id,
        r["status"],
        deadline=r["deadline"],
        deadline_evidence=r["deadline_evidence"],
        method=method,
        note=r["note"],
    )


def extract_pending():  # 설계 외: 추출 대기 공지 다시 처리
    for nid in notice.pending():
        extract(nid)
