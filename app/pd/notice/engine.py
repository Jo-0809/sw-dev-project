"""<<control>> 판정 엔진 — 참여 조건과 학적 프로필을 항목별로 대조해 지원 가능 / 지원 불가 / 확인 필요로 판정한다.

규칙 기반 매칭 (기술 선정 06-1). 판정 결과는 저장하지 않고 요청마다 다시 계산한다 (판정 결과 실체 삭제 결정).
프로필은 소속 대학·학과·학년·재학 상태 4개뿐이라(평점 미수집 결정), 학점·소득 같은 '기타' 조건은
판정할 수 없어 항목 단위로 '확인 필요'가 된다.

전체 판정
  하나라도 불충족            → 지원 불가
  불충족 없고 확인 필요 있음  → 확인 필요
  모두 충족                   → 지원 가능
  공지 상태가 '확인 필요'      → 확인 필요 (UC4에서 조건을 확정하지 못함)

구현 단계에서 생긴 클래스 의존: 판정 엔진 → 관심 출처
  judge(profile) 가 프로필 주인의 관심 출처 공지만 판정하려고 관심 출처를 조회한다. 클래스 다이어그램 v4의
  판정 엔진 의존은 공지·참여 조건뿐이다. 패키지 수준(공고 → 관심출처)은 원래 있는 의존이라 패키지 다이어그램은 그대로다.
"""

import re

from ..source import subscription
from . import condition, notice

OK, NO, CHECK = "충족", "불충족", "확인 필요"
ALL_DEPT = ("무관", "불문", "전체", "전 학과", "전학과", "제한 없", "모든 학과", "누구나")
BROAD_DEPT = ("관련", "계열", "분야", "등", "전공자", "유관")

# 학과별 분야 키워드. 공고에 이 말이 '관련 학과'·'계열' 같은 넓은 표현과 함께 나오면 내 학과도 해당한다고 본다.
# 지금은 소프트웨어공학과만 채웠다. 다른 학과는 같은 모양으로 추가한다 (팀 검토 필요).
# '정보'만 단독으로 쓰면 '경영정보·의료정보·도서관정보' 같은 다른 분야까지 맞아서, 붙은 말로 좁혔다.
DEPT_FIELDS = {
    "소프트웨어공학과": [
        "소프트웨어",
        "SW",
        "컴퓨터",
        "IT",
        "ICT",
        "전산",
        "정보통신",
        "정보보호",
        "정보보안",
        "정보공학",
        "정보시스템",
        "인공지능",
        "AI",
    ],
}
_LATIN = re.compile(r"^[A-Za-z]+$")
# '제외'가 붙은 조건은 반대로 읽어야 한다 ('소프트웨어공학과 제외'는 내 학과가 빠진다는 뜻). '제한 없음'은 제외가 아니다.
EXCLUDE = re.compile(r"제외|불가|미포함|해당\s*없|대상\s*아님|(?<!\S)빼고")
_CLAUSE_STOP = "()[]/;"


def _kind(part):
    """제외 대상 한 토막의 종류: 소속 대학 / 학과 / 학년 / 그 밖(휴학생·졸업예정자·대학원생 등)."""
    if re.search(r"대학교|본교", part):
        return "소속 대학"
    if re.search(r"학과|학부|전공|계열|대학(?!원)", part):
        return "학과"
    if re.search(r"\d", part):
        return "학년"
    return "기타"


_QUALIFIER = ("이상", "이하", "미만", "초과")  # 앞 낱말에 붙여 읽는다 ('2학년 이상')
_CONNECTOR = ("및", "와", "과", "또는", "그리고")  # 같은 종류를 잇는 말 ('1학년 및 2학년')
_BOUNDARY = ("중",)  # 여기서 끊는다 ('재학생 중 휴학생은 제외')


def _tokens(seg):
    """낱말 [(시작, 끝, 글자)]. 띄어쓰기·쉼표·가운뎃점으로 나누고, '이상·이하'는 앞 낱말에 붙인다."""
    out = []
    for m in re.finditer(r"[^\s,，·]+", seg):
        if out and m.group(0) in _QUALIFIER:
            s0, _, t = out[-1]
            out[-1] = (s0, m.end(), seg[s0 : m.end()])
        else:
            out.append((m.start(), m.end(), m.group(0)))
    return out


def _bare(word):
    return re.sub(r"(은|는|을|를)$", "", word)


def _split_exclusions(value):
    """'… 제외' 마다 무엇을 빼는지 찾는다. (나머지 문장, [(종류, 빼는 대상)]).
    '제외' 바로 앞 낱말부터 거꾸로 보면서 종류(소속 대학·학과·학년·그 밖)가 같은 동안만 제외 대상으로 묶는다.
    괄호·빗금은 넘어가지 않고, '중'에서 끊는다. 띄어쓰기·쉼표만 있어도 종류가 바뀌면 끊긴다.
      '기계공학과, 소프트웨어공학과 제외' → 두 학과        '2학년 이상 휴학생 제외' → 휴학생만
      '소프트웨어공학과 재학생 중 휴학생은 제외' → 휴학생만   '1학년 및 2학년 제외' → 두 학년"""
    excl, keep, pos = [], [], 0
    for m in EXCLUDE.finditer(value):
        start = pos
        for i in range(m.start() - 1, pos - 1, -1):
            if value[i] in _CLAUSE_STOP:
                start = i + 1
                break
        seg = value[start : m.start()]
        toks = _tokens(seg)
        if not toks:
            keep.append(value[pos : m.start()])
            excl.append(("기타", ""))
            pos = m.end()
            continue
        tail_kind = _kind(_bare(toks[-1][2]))
        first = len(toks) - 1
        for j in range(len(toks) - 2, -1, -1):
            word = _bare(toks[j][2])
            if word in _BOUNDARY:
                break
            if word in _CONNECTOR:
                continue
            if _kind(word) == tail_kind or (tail_kind == "학년" and word.isdigit()):
                first = j
            else:
                break
        cut = toks[first][0]
        target = _bare(seg[cut:].strip())
        head = re.sub(r"(?:(?:^|[\s,，·])(?:및|와|과|또는|그리고))?[\s,，·]*$", "", seg[:cut])  # 낱말 끝 '과'는 남김
        keep.append(value[pos:start] + head)
        excl.append((tail_kind, target))
        pos = m.end()
    keep.append(value[pos:])
    rest = "".join(keep)
    rest = re.sub(r"\(\s*\)|\[\s*\]", " ", rest)
    rest = re.sub(r"[\s,，·()]+$", "", re.sub(r"^\s*[,，·)]+", "", rest)).strip()
    return rest, excl


def _has_word(text, word):
    """영문 약어(SW, IT, AI)는 다른 영문 단어 속에 들어 있으면 안 맞는 것으로 본다 (UNIT, SWIFT 등)."""
    if _LATIN.match(word):
        return re.search(rf"(?<![A-Za-z]){word}(?![A-Za-z])", text) is not None
    return word in text


def _grades(value):
    v = value.replace(" ", "")
    v = re.sub(r"\d{4}학년도", "", v)  # '2026학년도'의 6을 6학년으로 읽지 않게 연도를 먼저 지운다
    m = re.search(r"(?<!\d)([1-6])[~∼\-]([1-6])학년", v)
    if m:
        return set(range(int(m.group(1)), int(m.group(2)) + 1))
    m = re.search(r"(?<!\d)([1-6])학년이상", v)
    if m:
        return set(range(int(m.group(1)), 7))
    m = re.search(r"(?<!\d)([1-6])학년이하", v)
    if m:
        return set(range(1, int(m.group(1)) + 1))
    found = {int(x) for x in re.findall(r"(?<!\d)([1-6])(?=[,·및]|학년)", v)}
    return found or None


def _dept_hit(value, mine):
    """(정확히 맞음, 일부만 겹침, 분야 키워드가 맞음)"""
    exact = re.search(rf"(?<![가-힣]){re.escape(mine)}", value) is not None
    core = re.sub(r"(학과|학부|전공)$", "", mine)
    same_core = bool(core) and re.search(rf"(?<![가-힣]){re.escape(core)}(학과|학부|전공)", value) is not None
    partial = len(core) >= 3 and core[:-1] in value  # 두 글자 이상 겹칠 때만 ('경' 한 글자로 맞추지 않음)
    keyword = any(_has_word(value, w) for w in DEPT_FIELDS.get(mine, []))
    return exact, same_core or partial, keyword


def _match_dept(value, mine):
    """학과 판정. '불충족'은 근거가 분명할 때만 낸다 (잘못된 지원 불가는 공고를 숨겨 미열람으로 이어지기 때문).
    0) '제외·불가'가 붙음: 학과를 빼는 '제외'일 때만 반대로 읽는다 ('휴학생 제외'는 학과 조건이 아님).
       내 학과가 제외 대상에 그대로 있으면 불충족, 겹치면 확인 필요, 아니면 남은 문장으로 판정 (없으면 확인 필요)
    1) 제한 없음 표현                         → 충족
    2) 내 학과명이 그대로 있음 (앞에 다른 글자 없이) → 충족
    3) 넓은 표현(관련·계열·분야·등) + 내 학과 분야 키워드 → 충족
    4) 내 학과와 일부만 겹침 (키워드, 학과·학부만 다름, 두 글자 이상) → 확인 필요
    5) 넓은 표현인데 키워드가 안 맞음              → 확인 필요
    6) 단과대학·계열만 적힘                       → 확인 필요
    7) 구체적인 학과명만 있고 하나도 안 맞음         → 불충족
    """
    rest, excl = _split_exclusions(value)
    targets = " ".join(t for k, t in excl if k == "학과")  # 학과를 빼는 '제외'만 본다
    if targets:
        exact, partial, keyword = _dept_hit(targets, mine)
        if exact:
            return NO, f"{value} (내 학과 {mine} 제외)"
        if partial or keyword:
            return CHECK, f"제외 대상과 내 학과가 겹칠 수 있음 ({value}) — 원문 확인"
        if not rest:
            return CHECK, f"제외 조건 ({value}) — 원문 확인"
    value = rest or value  # 휴학생·대학원생 제외 같은 말은 떼고 판정
    exact, partial, keyword = _dept_hit(value, mine)
    if any(k in value for k in ALL_DEPT):
        return OK, None
    if exact:
        return OK, None
    broad = any(b in value for b in BROAD_DEPT)
    if broad and keyword:
        return OK, None
    if keyword or partial:
        return CHECK, f"내 학과와 일부만 겹침 ({value}) — 원문 확인"
    if broad:
        return CHECK, f"넓은 범위의 학과 조건 ({value}) — 원문 확인"
    if re.search(r"(대학|계열)", value) and not re.search(r"(학과|학부|전공)", value):
        return CHECK, f"단과대학 소속 여부 확인 필요 ({value})"
    if re.search(r"(학과|학부|전공)", value):
        return NO, f"{value} 대상 (내 학과 {mine})"
    return CHECK, "학과 조건을 해석하지 못함"


def _match_item(item, value, prof):
    """(결과, 내 정보, 이유)"""
    if item == "학년":
        mine = f"{prof['grade']}학년"
        if any(k in value for k in ("무관", "제한 없", "전 학년", "누구나")):
            return OK, mine, None
        if re.search(r"진학\s*예정|진급\s*예정", value):
            return CHECK, mine, "다음 학기 학년 기준 조건 (원문 확인)"
        if re.search(r"수료|마친|마쳐|이수한", value):
            return CHECK, mine, "수혜 시점에 마친 학년 기준 (원문 확인)"
        m = re.search(r"([1-6])\s*학년\s*([12])\s*학기\s*이상", value)
        if m:
            g_min = int(m.group(1))
            if prof["grade"] > g_min:
                return OK, mine, None
            if prof["grade"] < g_min:
                return NO, mine, f"{value} 대상 (내 학년 {mine})"
            return CHECK, mine, "학기까지 확인 필요 (프로필에 학기 없음)"
        rest, excl = _split_exclusions(value)
        out = set()
        for k, t in excl:  # 학년을 빼는 '제외'만 ('1학년 제외')
            if k == "학년":
                out |= _grades(t + ("" if "학년" in t else "학년")) or set()
        if prof["grade"] in out:
            return NO, mine, f"{value} (내 학년 {mine})"
        g = _grades(rest) if rest else None
        if g is None:
            return (OK, mine, None) if out else (CHECK, mine, "학년 조건을 해석하지 못함")
        return (OK, mine, None) if prof["grade"] in g else (NO, mine, f"{value} 대상 (내 학년 {mine})")
    if item == "학과":
        mine = prof["department"]
        result, reason = _match_dept(value, mine)
        return result, mine, reason
    if item == "재학 상태":
        mine = prof["status"]
        if "휴학" in value and ("포함" in value or "가능" in value):
            ok = mine in ("재학", "휴학")
        elif "졸업예정" in value:
            ok = mine in ("재학", "졸업예정")
        elif "휴학생" in value and ("제외" in value or "불가" in value):
            ok = mine == "재학"
        elif "재학" in value:
            ok = mine == "재학"
        else:
            return CHECK, mine, "재학 상태 조건을 해석하지 못함"
        return (OK, mine, None) if ok else (NO, mine, f"{value} 대상 (내 상태 {mine})")
    if item == "소속 대학":
        mine = prof["university"]
        core = mine.replace("학교", "")
        rest, excl = _split_exclusions(value)
        targets = " ".join(t for k, t in excl if k == "소속 대학")  # 대학을 빼는 '제외'만 본다
        if targets:
            if core in targets or "본교" in targets:
                return NO, mine, f"{value} (내 소속 제외)"
            if not rest:
                return CHECK, mine, f"제외 조건 ({value}) — 원문 확인"
        value = rest or value
        if core in value or "본교" in value or any(k in value for k in ("무관", "전국", "누구나", "국내")):
            return OK, mine, None
        if re.search(r"\S+대학교", value):
            return NO, mine, f"{value} 대상"
        return CHECK, mine, "소속 대학 조건을 해석하지 못함"
    return CHECK, "-", "프로필로 판정할 수 없는 조건 (원문 확인)"


def _judge_one(prof, n, conditions):
    """공지 하나 판정. 판정 엔진 밖에서는 judge(profile) 를 쓴다 (채점·테스트는 예외로 직접 부름)."""
    rows = []
    for c in conditions:
        if not c.get("verified", 1):
            continue  # 근거 대조를 통과한 값만 판정에 쓴다
        result, mine, reason = _match_item(c["item"], c["value"], prof)
        rows.append({**c, "mine": mine, "result": result, "reason": reason})
    if n["status"] == notice.CHECK:
        verdict = "확인 필요"
    elif any(r["result"] == NO for r in rows):
        verdict = "지원 불가"
    elif any(r["result"] == CHECK for r in rows) or not rows:
        verdict = "확인 필요"
    else:
        verdict = "지원 가능"
    unmet = [r for r in rows if r["result"] == NO]
    return {
        "notice_id": n["id"],
        "verdict": verdict,
        "rows": rows,
        "unmet": unmet,
        "reason": unmet[0]["reason"] if unmet else None,
    }


def judge(profile):  # 판정한다(프로필) : 판정 목록
    """프로필 주인의 관심 출처 공지를 조회하고(→ 관심 출처, 공지), 조건을 조회해(→ 참여 조건) 판정한다.
    {공지 번호: 판정}. 조건 추출이 끝난 공지(추출 완료·확인 필요)만 들어 있다."""
    source_ids = [s["id"] for s in subscription.find(profile["account_id"])]
    notices = [n for n in notice.list_for(source_ids) if n["status"] in (notice.DONE, notice.CHECK)]
    conds = condition.find_many([n["id"] for n in notices])
    return {n["id"]: _judge_one(profile, n, conds.get(n["id"], [])) for n in notices}
