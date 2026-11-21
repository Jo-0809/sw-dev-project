"""<<control>> 근거 대조기 — LLM이 돌려준 근거 문장이 원문에 실제로 있는지 대조한다 (UC4 정상 7).

1) 근거 문장이 본문에 있는가        (공백·줄바꿈·일부 기호 차이는 무시)
2) 값의 숫자가 근거 문장에 있는가    근거는 진짜인데 값을 잘못 읽은 경우를 거른다.
   예: 근거 "1, 2학년 재학생"인데 값 "3학년 이상" → 3 이 근거에 없음 → 통과 못 함
   숫자만 본다. '재학생'↔'휴학생'처럼 글자로만 다른 값은 아직 거르지 못한다 (한계).
3) 마감일은 날짜로 비교한다. 근거 문장에서 날짜·시각을 읽어(2026.11.20 / 2026-11-20 / 2026년 11월 20일 /
   11. 20.(금) / 11/20, 18:00 / 23시 59분) 월·일이 같은지, 근거에 연도가 있으면 연도도 같은지 본다.
   근거에 기간(~·부터)이나 '까지'·'마감'이 있으면 그 끝 날짜(마감 날짜)와 같아야 한다 (시작일을 뽑으면 실패).
   연도가 없는 날짜는 앞 날짜의 연도를 이어받고, 월이 줄면 다음 해로 본다 (12. 20. ~ 1. 10.).
   마감 시각을 냈으면 그 마감 날짜 뒤에 적힌 시각과 같아야 한다 (근거에 없는 시각이면 실패).
   숫자 대조를 그대로 쓰면 '2026-11-20'과 '2026. 11. 20.'처럼 쓰는 방식만 달라도 떨어져서 따로 둔다.
통과하지 못한 값은 판정에 쓰지 않고 공지를 '확인 필요'로 돌린다. LLM의 지어내기(환각) 방어 장치.
"""
import re

_PUNCT = re.compile(r"[\s ·•\-–—~∼:：,，.。()（）\[\]「」『』\"'“”‘’]")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize(text):
    return _PUNCT.sub("", text or "")


def _numbers(text):
    return set(_NUM.findall(text or ""))


def value_matches(value, evidence):
    """값에 나온 숫자가 모두 근거 문장에도 있는지."""
    return _numbers(value) <= _numbers(evidence)


_FULL_DATE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
_MD_DATE = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*(?:월\s*|[./]\s*)([12]\d|3[01]|0?[1-9])(?!\d)")
_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-4])\s*(?::\s*([0-5]\d)|시\s*(?:([0-5]?\d)\s*분)?)")
_DEADLINE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?")


_RANGE = re.compile(r"[~∼〜]|부터")
_UNTIL = re.compile(r"까지")
_CLOSE = re.compile(r"마감")


def _dated(text):
    """근거 문장의 날짜를 나온 순서대로 [(시작 위치, 끝 위치, 연도, 월, 일)].
    연도가 없는 날짜는 앞 날짜의 연도를 이어받고, 앞 날짜보다 월이 작으면 다음 해로 본다 (12. 20. ~ 1. 10.)."""
    raw = [(m.start(), m.end(), int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in _FULL_DATE.finditer(text)]
    masked = _FULL_DATE.sub(lambda m: " " * len(m.group(0)), text)
    raw += [(m.start(), m.end(), None, int(m.group(1)), int(m.group(2))) for m in _MD_DATE.finditer(masked)]
    raw.sort()
    out, year, prev_month = [], None, None
    for s0, e0, y, mo, d in raw:
        if y is None and year is not None:
            y = year + (1 if prev_month is not None and mo < prev_month else 0)
        if y is not None:
            year = y
        prev_month = mo
        out.append((s0, e0, y, mo, d))
    return out


def _times_after(text, pos, stop):
    seg = text[pos:stop]
    return [(int(h), int(mi or mi2 or 0)) for h, mi, mi2 in _TIME.findall(seg)]


def dates_in(text):
    """근거 문장의 (연도 또는 None, 월, 일) 목록과 (시, 분) 목록. 연도 이어받기를 한 뒤의 값."""
    text = text or ""
    found = [(y, mo, d) for _, _, y, mo, d in _dated(text)]
    times = [(int(h), int(mi or mi2 or 0)) for h, mi, mi2 in _TIME.findall(_FULL_DATE.sub(" ", text))]
    return found, times


def deadline_candidates(text):
    """마감일이 될 수 있는 날짜들. 기간(~·부터)이 있으면 그 끝 날짜, '까지' 앞 날짜, '마감' 뒤 날짜만.
    그런 표시가 없으면 근거 문장의 모든 날짜."""
    text = text or ""
    dated = _dated(text)
    picks = set()
    for m in _RANGE.finditer(text):                       # 기간의 끝 = 표시 바로 뒤의 첫 날짜
        after = [x for x in dated if x[0] >= m.end()]
        if after:
            picks.add(after[0])
    for m in _UNTIL.finditer(text):                       # '까지' 바로 앞의 날짜
        before = [x for x in dated if x[1] <= m.start()]
        if before:
            picks.add(before[-1])
    if not picks:
        for m in _CLOSE.finditer(text):                   # '마감' 바로 뒤의 날짜
            after = [x for x in dated if x[0] >= m.end()]
            if after:
                picks.add(after[0])
    chosen = sorted(picks) if picks else dated
    out = []
    for x in chosen:
        nxt = [y[0] for y in dated if y[0] > x[0]]
        out.append((x[2], x[3], x[4], _times_after(text, x[1], nxt[0] if nxt else len(text))))
    return out


def deadline_matches(deadline, evidence):
    """마감일 값('YYYY-MM-DD' 또는 'YYYY-MM-DD HH:MM')이 근거 문장의 마감 날짜·시각과 맞는지.
    시작일을 마감일로 뽑은 경우, 연도가 다른 경우, 근거에 없는 시각을 붙인 경우는 통과하지 못한다."""
    m = _DEADLINE.match(deadline or "")
    if not m:
        return False
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hm = (int(m.group(4)), int(m.group(5))) if m.group(4) is not None else None
    for cy, cm, cd, times in deadline_candidates(evidence):
        if (cm, cd) != (mo, d) or (cy is not None and cy != y):
            continue
        if hm is None or hm in times:
            return True
    return False


def verify(response, body):                  # 근거 문장을 대조한다(응답, 본문) : 검증 결과
    nbody = normalize(body)

    def found(ev):
        ev_n = normalize(ev)
        return len(ev_n) >= 2 and ev_n in nbody

    conds = []
    for c in response.get("conditions") or []:
        if not isinstance(c, dict):
            continue                         # 형식이 틀린 원소는 버린다 (LLM 연결에서 먼저 걸러짐)
        ev = c.get("evidence")
        in_body = found(ev)
        same = in_body and value_matches(str(c.get("value") or ""), ev)
        conds.append({**c, "verified": same,
                      "why": None if same else ("원문에 근거 없음" if not in_body else "값의 숫자가 근거와 다름")})
    deadline_ok = (bool(response.get("deadline")) and found(response.get("deadline_evidence"))
                   and deadline_matches(response.get("deadline"), response.get("deadline_evidence")))
    return {"conditions": conds, "deadline_verified": deadline_ok}
