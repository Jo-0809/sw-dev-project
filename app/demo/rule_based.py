"""규칙 기반 추출 (정규식) — 시연 모드에서 LLM도 예시 결과도 없을 때의 대체 수단이자 채점의 기준선.

운영(DEMO_MODE=0)에서는 쓰지 않는다. 조건 추출 제어에는 app/main.py 가 대체 결과 제공자로 넣는다.
"""

import re

LABEL = "규칙 기반 (정규식)"

_DATE = re.compile(
    r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*\.?\s*(?:일)?\s*(?:\([^)]*\))?\s*(\d{1,2}:\d{2})?"
)


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
        m = re.search(
            r"([1-4])\s*[~∼-]\s*([1-4])\s*학년|([1-4])\s*학년\s*이상|([1-4])\s*학년(?:생)?(?:만)?\s*(?:재학생|대상|지원)",
            s,
        )
        if m and not any(c["item"] == "학년" for c in res["conditions"]):
            res["conditions"].append({"item": "학년", "value": m.group(0), "evidence": s})
        if re.search(r"휴학생|재학생|졸업예정자", s) and not any(c["item"] == "재학 상태" for c in res["conditions"]):
            v = (
                "휴학생 포함"
                if re.search(r"휴학생\s*(포함|가능)", s)
                else ("재학생" if "재학생" in s else "졸업예정자")
            )
            res["conditions"].append({"item": "재학 상태", "value": v, "evidence": s})
        if re.search(r"전공\s*무관|전\s*학과|학과\s*제한\s*없", s) and not any(
            c["item"] == "학과" for c in res["conditions"]
        ):
            res["conditions"].append({"item": "학과", "value": "전공 무관", "evidence": s})
        m = re.search(r"(\S+(?:학과|학부|대학))\s*(?:소속\s*)?(?:재학생|학생)", s)
        if m and "경상국립" not in m.group(1) and not any(c["item"] == "학과" for c in res["conditions"]):
            res["conditions"].append({"item": "학과", "value": m.group(1), "evidence": s})
        if re.search(r"(본교|경상국립대(?:학교)?)\s*(?:재학생|학생|학부생)", s) and not any(
            c["item"] == "소속 대학" for c in res["conditions"]
        ):
            res["conditions"].append({"item": "소속 대학", "value": "경상국립대학교", "evidence": s})
        m = re.search(r"(평점|학점|성적)[^\n]{0,20}?\d(?:\.\d+)?\s*(?:이상)?", s)
        if m and not any(c["item"] == "기타" and "평점" in c["value"] for c in res["conditions"]):
            res["conditions"].append({"item": "기타", "value": m.group(0), "evidence": s})
    return res
