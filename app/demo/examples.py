"""예시 결과 — API 키도 LLM 녹화도 없을 때 조건 추출 제어가 쓰는 값. 사람이 LLM 응답 형식으로 썼다 (LLM 출력 아님).

  모의 게시판 공지  : fixtures/extractions.json  (날짜 자리표시 {D+n} 를 오늘 기준으로 바꿈)
  저장된 실제 공지  : fixtures/examples_real.json
"""
import json
from pathlib import Path

from . import mockdata

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
LABEL = "예시 결과 (사람이 작성 · LLM 출력 아님)"


def example_result(notice):
    if "/mock/" in notice["url"]:
        path, render = FIXTURE_DIR / "extractions.json", True
    elif "gnu.ac.kr" in notice["url"]:
        path, render = FIXTURE_DIR / "examples_real.json", False
    else:
        return None
    if not path.exists():
        return None
    tpl = json.loads(path.read_text(encoding="utf-8")).get(str(notice["ntt_sn"]))
    if tpl is None:
        return None
    tpl = {k: v for k, v in tpl.items() if not k.startswith("_")}
    return json.loads(mockdata.render(json.dumps(tpl, ensure_ascii=False))) if render else tpl
