"""추출 API 비교 — 저장된 실제 공지 10건으로 규칙 기반·Gemini·Anthropic 을 같은 정답 라벨로 채점한다.

    python tools/compare_llm.py                     # 쓸 수 있는 방법 모두 (녹화가 있으면 재생, 없으면 API 호출 후 녹화)
    python tools/compare_llm.py --mode live         # 녹화를 무시하고 다시 호출 (요금 발생)
    python tools/compare_llm.py --mode replay       # 녹화만으로 채점 (API 호출 없음)
    python tools/compare_llm.py --only gemini,rule  # 일부만

키는 .env 의 GEMINI_API_KEY / ANTHROPIC_API_KEY 에서 읽는다. 결과는 evaluation/results/ 에 저장된다.
표본이 10건(채점 8건)이라 '중간 측정값'이다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # Windows 콘솔에서 한글 깨짐 방지

from app.demo import evaluation  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mode", default="auto", choices=["auto", "live", "replay"])
ap.add_argument("--only", default="")
a = ap.parse_args()

usable = {m["id"]: m for m in evaluation.availability()}
for m in usable.values():
    print(f"  {m['name']:<22} {m['note']}")
methods = [x.strip() for x in a.only.split(",") if x.strip()] or [k for k, m in usable.items() if m["usable"]]
if a.mode == "live":
    methods = [m for m in methods if m == "rule" or usable[m]["has_key"]]
print(f"\n실행: {', '.join(methods)}  (mode={a.mode})\n")
res = evaluation.run_compare(methods, mode=a.mode, progress=lambda t: print("  ", t, end="\r"))
print(" " * 60)
print(evaluation.summary_table(res))
s = res["results"][0]["summary"]
print(f"\n표본 {s['sample_total']}건 중 채점 {s['scored']}건 (이미지 본문 {s['excluded']}건 제외) · 중간 측정값")
print(f"정답 라벨: {res['labels_status']}")
print("결과 파일: evaluation/results/latest.json")
