"""<<control>> 공고 조회 제어 — 목록·상세 조회, 마감일 순 정렬, 열람 기록 (UC5).

정상   목록 요청 → 프로필 조회 → 판정 엔진 → 지원 가능 공지를 마감일 순 정렬 → 표시
대안 1 전체 보기 (지원 불가·확인 필요·모집 공고 아님까지)
대안 2 원문 링크 선택 → 원문 페이지
예외 1 프로필 없음 → 프로필 입력 화면 (2-1)
예외 2 지원 가능 공고 없음 → '현재 지원 가능한 공고가 없습니다' (5-6)
"""

from datetime import date

from ... import config
from ..source import subscription
from ..user import profile
from . import condition, engine, notice, view_log

_ORDER = {"지원 가능": 0, "확인 필요": 1, "지원 불가": 2, "추출 중": 3, "모집 공고 아님": 4}


def _dday(deadline):
    if not deadline:
        return None
    try:
        d = date.fromisoformat(deadline[:10])
    except ValueError:
        return None
    return (d - config.today()).days


def _sort_by_deadline(items):  # 지원 가능 공지를 마감일 순으로 정렬한다()
    return sorted(
        items,
        key=lambda x: (x["dday"] is None, x["dday"] if x["dday"] is not None else 0, x["notice"]["deadline"] or ""),
    )


def _not_judged(n):
    """조건 추출이 끝나지 않았거나 모집 공고가 아닌 공지의 판정 칸."""
    verdict = "모집 공고 아님" if n["status"] == notice.NOT_RECRUIT else "추출 중"
    return {"verdict": verdict, "rows": [], "unmet": [], "reason": None}


def _collect_items(account_id, view):
    """프로필·관심 출처 공지를 판정해 목록 항목으로 만든다. 프로필이 없으면 items 없이 돌려준다 (예외 1)."""
    prof = profile.find(account_id)
    subs = subscription.find(account_id)
    out = {"profile": prof, "subscriptions": subs, "items": [], "counts": {}, "view": view, "past_count": 0}
    if prof is None:  # 예외 1
        return out, [], []
    judged = engine.judge(prof)  # 판정한다(프로필) : 판정 목록
    viewed = view_log.viewed(account_id)
    items = []
    for n in notice.list_for([s["id"] for s in subs]):
        j = judged.get(n["id"]) or _not_judged(n)
        dd = _dday(n["deadline"])
        items.append(
            {
                "notice": n,
                "verdict": j["verdict"],
                "reason": j["reason"],
                "unmet": j["unmet"],
                "dday": dd,
                "expired": dd is not None and dd < 0,
                "viewed": n["id"] in viewed,
            }
        )
    live = [i for i in items if not i["expired"]]
    past = [i for i in items if i["expired"]]
    out["past_count"] = len(past)
    out["counts"] = {
        "지원 가능": sum(i["verdict"] == "지원 가능" for i in live),
        "전체": len(live),
        "확인 필요": sum(i["verdict"] == "확인 필요" for i in live),
    }
    return out, live, past


def request_list(account_id):  # 공고 목록을 요청한다(계정)
    """지원 가능 공고만, 마감일 가까운 순 (정상 흐름, 5-1 메인 화면)."""
    out, live, _ = _collect_items(account_id, "possible")
    out["items"] = _sort_by_deadline([i for i in live if i["verdict"] == "지원 가능"])
    return out


def request_all(account_id, include_past=False):  # 전체 목록을 요청한다() : 판정 목록 전체
    """대안 1 전체 보기: 지원 불가·확인 필요·모집 공고 아님까지. 마감일 미확인은 맨 뒤.
    include_past: 시연용으로 마감 지난 공고도 맨 아래에 (저장된 실제 공지 확인용)."""
    out, live, past = _collect_items(account_id, "all")
    dated = _sort_by_deadline([i for i in live if i["dday"] is not None])
    undated = sorted([i for i in live if i["dday"] is None], key=lambda i: _ORDER.get(i["verdict"], 9))
    out["items"] = dated + undated
    if include_past:
        out["items"] += sorted(past, key=lambda i: i["notice"]["deadline"] or "", reverse=True)
    return out


def request_detail(account_id, notice_id):  # 상세를 요청한다(계정, 번호)
    n = notice.get(notice_id)  # 조회한다(번호) : 공지
    if n is None or not any(s["id"] == n["source_id"] for s in subscription.find(account_id)):
        return None
    prof = profile.find(account_id)
    conds = condition.find(notice_id)  # 조회한다(번호) : 참여 조건
    j = (engine.judge(prof).get(notice_id) if prof else None) or _not_judged(n)  # 판정한다(프로필)
    view_log.save(account_id, notice_id)  # 저장한다(계정, 번호, 열람 시각)
    return {
        "notice": n,
        "judgement": j,
        "conditions": conds,
        "profile": prof,
        "dday": _dday(n["deadline"]),
        "verified": [c for c in conds if c["verified"]],
    }
