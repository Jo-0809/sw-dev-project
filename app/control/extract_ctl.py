"""<<control>> 조건 추출 제어 — LLM 호출·재시도, 근거 대조, 공지 상태 결정 (UC4 정상 5~7, 대안 3, 예외 2).
흐름 번호는 LMS 최종본 놓칠뻔_중간발표자료_FINAL.pdf (2026-10-11 23:27) 04-2·09-1 명세서 기준 (README 참고).

추출 방법 우선순위
  1) LLM (Gemini 또는 Anthropic, .env 의 LLM_PROVIDER)
       - 같은 공지의 녹화가 있으면 녹화 재생 (LLM_MODE=auto/replay), 없으면 API 호출 후 녹화
       - 호출이 실패하면 최대 3회 재시도, 그래도 실패하면 '확인 필요' (예외 2)
  2) 예시 결과 : 시연 모드(DEMO_MODE=1)에서 키도 녹화도 없을 때. 사람이 LLM 응답 형식으로 써 둔 값 (LLM 출력 아님)
                 모의 게시판 공지와 저장된 실제 공지 10건 (app/demo/examples.py)
  3) 규칙 기반 : 위가 모두 없을 때의 최소 대체 수단 (정규식)
어느 방법이든 결과는 근거 대조기를 거친다.

공지 상태
  모집 공고 아님 : 모집 공고가 아니라고 판별 (대안 3)
  확인 필요      : 조건을 못 찾음(대안 3) / 원문에 없는 값(정상 7) / LLM 3회 실패(예외 2)
                   / 본문이 이미지(수집 단계, 제약사항 03-2) / 추출 중 예상 못 한 오류(수집 제어가 처리)
  추출 완료      : 근거 대조를 통과한 조건·마감일 저장
"""
import re

from .. import config
from ..boundary import llm_client
from ..entity import Condition, Notice
from . import verifier

EXAMPLE_LABEL = "예시 결과 (사람이 작성 · LLM 출력 아님)"


def _example_result(notice):
    """시연 모드에서만: 사람이 써 둔 예시 결과. 운영에서는 쓰지 않는다 (app.demo 를 불러오지도 않음)."""
    if not config.DEMO_MODE:
        return None
    from ..demo import examples
    return examples.example_result(notice)


# ---------------------------------------------------------------- 규칙 기반 대체 추출
_DATE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*\.?\s*(?:일)?\s*(?:\([^)]*\))?\s*(\d{1,2}:\d{2})?")


def _sentences(body):
    for line in body.splitlines():
        line = line.strip()
        if line:
            yield line


def rule_based(title, body):
    text = title + "\n" + body
    res = {"is_recruitment": True, "deadline": None, "deadline_evidence": None, "conditions": []}
    if re.search(r"(명단|결과|합격자)\s*(안내|발표|공고)", title) and not re.search(r"모집|신청|접수", title):
        res["is_recruitment"] = False
        return res
    if not re.search(r"모집|신청|접수|지원|참가", text):
        res["is_recruitment"] = False
        return res
    for s in _sentences(body):
        if not res["deadline"] and re.search(r"마감|까지|기간|기한|접수", s):
            dates = list(_DATE.finditer(s))
            if dates:
                y, mo, d, hm = dates[-1].groups()
                res["deadline"] = f"{y}-{int(mo):02d}-{int(d):02d}" + (f" {hm}" if hm else "")
                res["deadline_evidence"] = s
        m = re.search(r"([1-4])\s*[~∼-]\s*([1-4])\s*학년|([1-4])\s*학년\s*이상|([1-4])\s*학년(?:생)?(?:만)?\s*(?:재학생|대상|지원)", s)
        if m and not any(c["item"] == "학년" for c in res["conditions"]):
            res["conditions"].append({"item": "학년", "value": m.group(0), "evidence": s})
        if re.search(r"휴학생|재학생|졸업예정자", s) and not any(c["item"] == "재학 상태" for c in res["conditions"]):
            v = "휴학생 포함" if re.search(r"휴학생\s*(포함|가능)", s) else ("재학생" if "재학생" in s else "졸업예정자")
            res["conditions"].append({"item": "재학 상태", "value": v, "evidence": s})
        if re.search(r"전공\s*무관|전\s*학과|학과\s*제한\s*없", s) and not any(c["item"] == "학과" for c in res["conditions"]):
            res["conditions"].append({"item": "학과", "value": "전공 무관", "evidence": s})
        m = re.search(r"(\S+(?:학과|학부|대학))\s*(?:소속\s*)?(?:재학생|학생)", s)
        if m and "경상국립" not in m.group(1) and not any(c["item"] == "학과" for c in res["conditions"]):
            res["conditions"].append({"item": "학과", "value": m.group(1), "evidence": s})
        if re.search(r"(본교|경상국립대(?:학교)?)\s*(?:재학생|학생|학부생)", s) and not any(c["item"] == "소속 대학" for c in res["conditions"]):
            res["conditions"].append({"item": "소속 대학", "value": "경상국립대학교", "evidence": s})
        m = re.search(r"(평점|학점|성적)[^\n]{0,20}?\d(?:\.\d+)?\s*(?:이상)?", s)
        if m and not any(c["item"] == "기타" and "평점" in c["value"] for c in res["conditions"]):
            res["conditions"].append({"item": "기타", "value": m.group(0), "evidence": s})
    return res


# ---------------------------------------------------------------- 상태 결정
def decide(response, body):                  # 상태를 결정한다(응답, 검증 결과)
    """LLM 응답(또는 예시·규칙 결과)과 본문으로 공지 상태를 정한다. DB를 쓰지 않아 채점에서도 쓴다."""
    if not response.get("is_recruitment", True):           # 대안 3: 모집 공고 아님
        return {"status": "모집 공고 아님", "conditions": [], "deadline": None, "deadline_evidence": None,
                "note": "모집 공고가 아닌 공지"}
    checked = verifier.verify(response, body)              # 대조한다(응답, 본문) : 검증 결과
    conds = [c for c in checked["conditions"] if c.get("item") in llm_client.ITEMS and c.get("value")]
    unverified = [c for c in conds if not c["verified"]]
    deadline = response.get("deadline") if checked["deadline_verified"] else None
    deadline_ev = response.get("deadline_evidence") if deadline else None
    if not conds:
        status, note = "확인 필요", "공지 본문에서 참여 조건을 찾지 못함"
    elif unverified:
        status = "확인 필요"
        note = "근거 대조 실패: " + ", ".join(f"{c['item']} '{c['value']}' ({c.get('why') or '원문에 근거 없음'})"
                                         for c in unverified)
    else:
        status, note = "추출 완료", None
    if response.get("deadline") and not deadline:
        note = (note + " / " if note else "") + "마감일이 근거 문장과 맞지 않음 (원문에 없거나 날짜·시각이 다름)"
    return {"status": status, "conditions": conds, "deadline": deadline, "deadline_evidence": deadline_ev,
            "note": note}


def _method_text(info):
    name = llm_client.PROVIDERS[info["provider"]]["name"]
    if info["how"] == "replay":
        return f"LLM 녹화 재생 · {name} {info['model']} (녹화 {info['recorded_at']})"
    return f"LLM · {name} {info['model']} ({info['latency_ms']} ms, 녹화함)"


def run_llm(title, body, provider=None, mode=None):
    """(응답, 정보, 오류). 키도 녹화도 없으면 (None, None, None). 3회 모두 실패하면 (None, None, 마지막 오류)."""
    last_err = None
    for _ in range(config.LLM_MAX_RETRY):                  # 최대 3회 재시도
        try:
            data, info = llm_client.extract_conditions(title, body, provider=provider, mode=mode)
            return data, info, None
        except llm_client.NotAvailable:
            return None, None, None
        except llm_client.LLMError as e:
            last_err = e
    return None, None, last_err


# ---------------------------------------------------------------- 추출 흐름
def extract(notice_id):                      # 추출한다(공지)
    notice = Notice.get(notice_id)
    if notice is None:
        return
    response, info, err = run_llm(notice["title"], notice["body"])
    if err is not None:                                    # 예외 2: 3회 실패 → 확인 필요
        Notice.save_result(notice_id, "확인 필요", method=f"LLM · {llm_client.PROVIDERS[llm_client._pid(None)]['name']}",
                           note=f"LLM 3회 실패 ({err})")
        Condition.save_all(notice_id, [])
        return
    if response is not None:
        method = _method_text(info)
    else:
        response = _example_result(notice)
        method = EXAMPLE_LABEL if response else None
        if response is None:
            response = rule_based(notice["title"], notice["body"])
            method = "규칙 기반 (정규식)"

    r = decide(response, notice["body"])
    Condition.save_all(notice_id, r["conditions"])
    Notice.save_result(notice_id, r["status"], deadline=r["deadline"], deadline_evidence=r["deadline_evidence"],
                       method=method, note=r["note"])


def extract_pending():
    for nid in Notice.pending():
        extract(nid)
