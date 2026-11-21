"""추출 API 비교·채점 (시연·측정 도구. 클래스 다이어그램 밖이다).

표본: 저장된 실제 경상국립대 공지 10건 (recordings/web, 2026-10-11 저장). 정답: evaluation/labels.json (초안).
비교 대상
  rule       : 규칙 기반 (정규식) — API 없이 항상 돈다. 기준선
  gemini     : Gemini API (녹화가 있으면 재생)
  anthropic  : Anthropic API (녹화가 있으면 재생)
예시 결과(사람이 작성)는 채점하지 않는다. 정답을 쓴 사람이 같은 기준으로 썼기 때문에 점수가 의미 없다.

지표 (표본이 작아 '중간 측정값'으로만 쓴다)
  모집 판별 정확도   is_recruitment 가 정답과 같은 공지 비율
  마감일 정확도      (모집 공고만) 날짜(YYYY-MM-DD)가 정답과 같은 비율. 정답이 없음(null)이면 null 이어야 맞음
  조건 재현율        정답 조건 중 같은 항목·핵심어로 뽑힌 비율
  조건 정밀도        뽑은 조건 중 정답 조건과 맞은 비율
  근거 통과율        뽑은 조건 중 근거 문장이 원문에 있는 비율 (근거 대조기)
  지어낸 조건 수     근거 대조를 통과하지 못한 조건 수
  확인 필요 비율     표본 전체 중 시스템이 '확인 필요'로 저장한 공지 비율 (추출 단계 상태, 이미지 본문 포함)
  판정 일치율        labels.json 의 프로필로 판정 엔진을 돌린 결과가 expected_verdict 와 같은 비율
  평균 응답 시간     API 호출(또는 녹화된 호출)의 평균 ms
"""

import json
import re
import threading
from datetime import datetime

from .. import config
from ..pd.collect import extract_ctl, parser, verifier
from ..pd.external import llm_client, web
from ..pd.notice import engine
from . import rule_based

EVAL_DIR = config.BASE_DIR / "evaluation"
LABELS = EVAL_DIR / "labels.json"
RESULTS = EVAL_DIR / "results"
METHODS = {"rule": "규칙 기반 (기준선)", "gemini": "Gemini", "anthropic": "Anthropic (Claude)"}
# 중간발표 05 품질 시나리오 #1 응답척도 (표본 100건 기준)
TARGETS = {"cond_recall": "90% 이상", "deadline_acc": "95% 이상", "fabricated": "0건", "check_ratio": "10% 이하"}

_lock = threading.Lock()
state = {"running": False, "progress": "", "error": None}


def load_labels():
    return json.loads(LABELS.read_text(encoding="utf-8"))


def eval_notices():
    """정답 라벨이 있는 공지를 저장된 실제 응답에서 다시 해석해 온다 (DB를 쓰지 않음)."""
    out = []
    for lab in load_labels()["notices"]:
        url = f"https://www.gnu.ac.kr/{lab['site']}/na/ntt/selectNttInfo.do?nttSn={lab['ntt_sn']}"
        try:
            html = json.loads(web._record_path(url).read_text(encoding="utf-8"))["text"]
            p = parser.parse_detail(html, url, lab["ntt_sn"])
        except (OSError, ValueError, KeyError):
            p = None
        out.append({"label": lab, "parsed": p})
    return out


def _norm(t):
    return re.sub(r"\s+", "", (t or "")).lower()


def _match(label_conds, pred_conds):
    used, matched = set(), 0
    for lc in label_conds:
        keys = [_norm(k) for k in lc["match"]]
        for i, pc in enumerate(pred_conds):
            if i in used or pc.get("item") != lc["item"]:
                continue
            text = _norm(pc.get("value")) + _norm(pc.get("evidence"))
            if any(k in text for k in keys):
                used.add(i)
                matched += 1
                break
    return matched, len(used)


def availability():
    rows = [
        {
            "id": "rule",
            "name": METHODS["rule"],
            "model": "-",
            "has_key": True,
            "recordings": 0,
            "usable": True,
            "note": "API 없이 항상 실행",
        }
    ]
    for pid in ("gemini", "anthropic"):
        key = llm_client.has_key(pid)
        recs = llm_client.recording_count(pid)
        rows.append(
            {
                "id": pid,
                "name": METHODS[pid],
                "model": llm_client.model_of(pid),
                "has_key": key,
                "recordings": recs,
                "usable": key or recs > 0,
                "note": ("키 있음" if key else "키 없음") + f" · 녹화 {recs}건",
            }
        )
    return rows


def run_method(method, mode="auto", progress=None):
    """한 방법으로 표본 전체를 추출하고 채점한다."""
    labels = load_labels()
    prof = labels["profile"]
    rows, lat = [], []
    for k, e in enumerate(eval_notices(), 1):
        lab, p = e["label"], e["parsed"]
        if progress:
            progress(f"{METHODS[method]} {k}/{len(labels['notices'])}")
        row = {"ntt_sn": lab["ntt_sn"], "title": lab["title"], "expected_verdict": lab.get("expected_verdict")}
        if lab.get("exclude") or p is None:
            # 이미지 본문은 수집 단계에서 '확인 필요'로 저장되므로 확인 필요 비율에는 넣는다
            row.update(
                excluded=True,
                reason=lab.get("exclude_reason") or "저장된 응답 없음",
                status="확인 필요" if lab.get("exclude") else None,
            )
            rows.append(row)
            continue
        info, err = None, None
        if method == "rule":
            resp = rule_based.rule_based(p["title"], p["body"])
        else:
            resp, info, err = extract_ctl.run_llm(p["title"], p["body"], provider=method, mode=mode)
            if resp is None:
                row.update(
                    excluded=False,
                    failed=True,
                    error=str(err) if err else "키·녹화 없음 (실행 못 함)",
                    unavailable=err is None,
                )
                rows.append(row)
                continue
        if info and info.get("latency_ms") is not None:
            lat.append(info["latency_ms"])
        decided = extract_ctl.decide_status(resp, p["body"])
        if decided["status"] == "모집 공고 아님":
            verdict = "모집 공고 아님"
        else:
            verdict = engine._judge_one(  # 채점용 예외: 공지 하나를 DB 없이 판정
                prof, {"id": 0, "status": decided["status"]}, decided["conditions"]
            )["verdict"]
        preds = [c for c in resp.get("conditions") or [] if isinstance(c, dict)]  # 근거 대조기와 같은 범위
        checked = [c["verified"] for c in verifier.verify(resp, p["body"])["conditions"]]
        rec_ok = bool(resp.get("is_recruitment", True)) == bool(lab["is_recruitment"])
        dl_pred = (resp.get("deadline") or "")[:10] or None
        lconds = lab["conditions"] if lab["is_recruitment"] else []
        pconds = preds if resp.get("is_recruitment", True) else []
        matched, used = _match(lconds, pconds)
        row.update(
            excluded=False,
            failed=False,
            how=(info or {}).get("how", "rule"),
            model=(info or {}).get("model", "-"),
            latency_ms=(info or {}).get("latency_ms"),
            is_recruitment=resp.get("is_recruitment"),
            recruit_ok=rec_ok,
            deadline=dl_pred,
            deadline_label=lab.get("deadline"),
            deadline_ok=(dl_pred == lab.get("deadline")) if lab["is_recruitment"] else None,
            label_conds=len(lconds),
            pred_conds=len(pconds),
            matched=matched,
            pred_matched=used,
            verified=sum(checked),
            fabricated=len(checked) - sum(checked),
            verdict=verdict,
            verdict_ok=verdict == lab.get("expected_verdict"),
            status=decided["status"],
            conditions=[{**c, "verified": v} for c, v in zip(preds, checked, strict=True)],
        )
        rows.append(row)
    scored = [r for r in rows if not r["excluded"] and not r.get("failed")]
    rec = [r for r in scored if r["deadline_ok"] is not None]

    def pct(a, b):
        return round(a / b * 100, 1) if b else None

    label_total = sum(r["label_conds"] for r in scored)
    pred_total = sum(r["pred_conds"] for r in scored)
    summary = {
        "method": method,
        "name": METHODS[method],
        "mode": mode,
        "model": next((r["model"] for r in scored if r.get("model") not in (None, "-")), "-"),
        "how": sorted({r["how"] for r in scored}) if scored else [],
        "sample_total": len(rows),
        "excluded": sum(r["excluded"] for r in rows),
        "scored": len(scored),
        "failed": sum(1 for r in rows if r.get("failed") and not r.get("unavailable")),
        "unavailable": sum(1 for r in rows if r.get("unavailable")),
        "recruit_acc": pct(sum(r["recruit_ok"] for r in scored), len(scored)),
        "deadline_acc": pct(sum(r["deadline_ok"] for r in rec), len(rec)),
        "cond_recall": pct(sum(r["matched"] for r in scored), label_total),
        "cond_precision": pct(sum(r["pred_matched"] for r in scored), pred_total),
        "evidence_pass": pct(sum(r["verified"] for r in scored), pred_total),
        "fabricated": sum(r["fabricated"] for r in scored),
        "verdict_acc": pct(sum(r["verdict_ok"] for r in scored), len(scored)),
        "check_ratio": pct(
            sum(1 for r in rows if r.get("status") == "확인 필요"), sum(1 for r in rows if r.get("status"))
        ),
        "latency_avg_ms": round(sum(lat) / len(lat)) if lat else None,
        "labels_reviewed": bool(labels.get("reviewed")),
    }
    return {"summary": summary, "rows": rows}


def run_compare(methods=None, mode="auto", progress=None):
    methods = methods or [m["id"] for m in availability() if m["usable"]]
    out = {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "labels_status": load_labels().get("status"),
        "results": [],
    }
    for m in methods:
        out["results"].append(run_method(m, mode=mode, progress=progress))
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    (RESULTS / f"compare_{stamp}.json").write_text(text, encoding="utf-8")
    (RESULTS / "latest.json").write_text(text, encoding="utf-8")
    return out


def latest():
    p = RESULTS / "latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def start_background(mode="auto"):
    if not _lock.acquire(blocking=False):
        return False

    def work():
        state.update(running=True, error=None, progress="시작")
        try:
            run_compare(mode=mode, progress=lambda t: state.update(progress=t))
        except Exception as e:  # 화면에 사유를 보여 주고 서버는 계속 돈다
            state["error"] = f"{e.__class__.__name__}: {e}"
        finally:
            state.update(running=False, progress="")
            _lock.release()

    threading.Thread(target=work, daemon=True).start()
    return True


def summary_table(result):
    """터미널 출력용 표."""
    cols = [
        ("방법", "name"),
        ("채점", "scored"),
        ("모집판별%", "recruit_acc"),
        ("마감일%", "deadline_acc"),
        ("조건재현%", "cond_recall"),
        ("조건정밀%", "cond_precision"),
        ("근거통과%", "evidence_pass"),
        ("지어냄", "fabricated"),
        ("확인필요%", "check_ratio"),
        ("판정일치%", "verdict_acc"),
        ("평균ms", "latency_avg_ms"),
        ("실패", "failed"),
        ("못돌림", "unavailable"),
    ]
    lines = [" | ".join(c for c, _ in cols)]
    for r in result["results"]:
        s = r["summary"]
        lines.append(" | ".join("-" if s.get(k) is None else str(s.get(k)) for _, k in cols))
    return "\n".join(lines)


if __name__ == "__main__":  # python -m app.evaluation
    print(summary_table(run_compare(["rule"])))
