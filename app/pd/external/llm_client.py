"""<<boundary>> LLM API 연결 — 공지 제목·본문에서 참여 조건을 뽑는다 (기술 선정 06-1).

제공자 두 곳을 같은 질문(PROMPT)과 같은 응답 형식(SCHEMA)으로 부른다.
  gemini    : Google Gemini generateContent, responseSchema 로 JSON 강제
  anthropic : Anthropic Messages API, 도구 호출(tool_choice)로 JSON 강제
어느 쪽이든 값마다 원문 근거 문장을 함께 받고, 근거가 원문에 있는지는 근거 대조기(verifier)가 따로 확인한다.

녹화·재생 (.env 의 LLM_MODE)
  auto   : recordings/llm/ 에 같은 공지·같은 모델의 녹화가 있으면 그것을 쓰고(API 호출 없음), 없으면 호출 후 녹화
  live   : 항상 호출하고 녹화
  replay : 녹화만 쓴다. 키가 있어도 호출하지 않는다 (발표장 네트워크가 불안할 때)
녹화 파일에는 응답 원문 JSON, 모델 이름, 녹화 시각, 걸린 시간이 들어 있다. API 키는 저장하지 않는다.
"""

import hashlib
import json
import time
from datetime import datetime

import requests

from ... import config

ITEMS = ["소속 대학", "학과", "학년", "재학 상태", "기타"]
PROMPT_VERSION = "v3"  # v3 (2026-11-21): 학사 절차 신청은 모집 공고 아님, 제목도 근거로 씀

PROMPT = """너는 대학 공지에서 '지원 자격'을 뽑는 도우미다. 아래 공지의 제목과 본문만 보고 답하라.
조건이나 마감일이 제목에만 있을 수도 있다 (예: 제목의 '(~9/30)', '구)○○대 학생 대상').

규칙
1. is_recruitment: 장학금·공모전·대외활동·행사·프로그램처럼 학생이 신청·지원·참가할 수 있는 모집 공고면 true.
   결과 발표·명단 안내·일정 안내·제출 의무 안내면 false.
   성적포기·수강신청·수강정정·휴학·복학·졸업 신청 같은 학사 절차 신청 안내도 false (모집이 아님).
2. deadline: 신청(접수) 마감 일시. "YYYY-MM-DD HH:MM" 형식. 시각이 없으면 "YYYY-MM-DD". 제목·본문에 없으면 null.
   deadline_evidence: 마감일이 적힌 제목 또는 본문 문장을 글자 그대로 복사한다.
3. conditions: 지원 자격 조건. item은 다음 중 하나: 소속 대학, 학과, 학년, 재학 상태, 기타.
   - 학년: "1~3학년", "2학년 이상"처럼 원문 표현대로.
   - 학과: 특정 학과·단과대학 제한. 제한이 없다고 명시돼 있으면 "전공 무관".
   - 재학 상태: 재학생, 휴학생 포함 여부, 졸업예정자 등.
   - 기타: 학점(평점), 소득 구간, 어학 성적, 국적 등 위 항목이 아닌 조건. 조건 하나당 한 줄.
   - '우대'는 자격 조건이 아니므로 넣지 않는다.
   - evidence: 그 조건이 적힌 제목 또는 본문 문장을 글자 그대로 복사한다. 원문에 없는 내용은 절대 만들지 않는다.
   공지에 언급이 없는 항목은 넣지 않는다.

공지 제목: {title}
공지 본문:
{body}
"""

# Gemini responseSchema 형식 (대문자 형 이름)
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_recruitment": {"type": "BOOLEAN"},
        "deadline": {"type": "STRING", "nullable": True},
        "deadline_evidence": {"type": "STRING", "nullable": True},
        "conditions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "item": {"type": "STRING", "enum": ITEMS},
                    "value": {"type": "STRING"},
                    "evidence": {"type": "STRING"},
                },
                "required": ["item", "value", "evidence"],
            },
        },
    },
    "required": ["is_recruitment", "conditions"],
}

# Anthropic 도구 입력 형식 (JSON Schema)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_recruitment": {"type": "boolean"},
        "deadline": {"type": ["string", "null"]},
        "deadline_evidence": {"type": ["string", "null"]},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "enum": ITEMS},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["item", "value", "evidence"],
            },
        },
    },
    "required": ["is_recruitment", "conditions"],
}

PROVIDERS = {
    "gemini": {"name": "Gemini", "key": lambda: config.GEMINI_API_KEY, "model": lambda: config.GEMINI_MODEL},
    "anthropic": {
        "name": "Anthropic (Claude)",
        "key": lambda: config.ANTHROPIC_API_KEY,
        "model": lambda: config.ANTHROPIC_MODEL,
    },
}


class LLMError(Exception):
    """호출은 했지만 실패 (응답 없음, HTTP 오류, 형식 오류). 조건 추출 제어가 최대 3회 다시 시도한다."""


class LLMUnavailableError(Exception):
    """키도 녹화도 없어서 이 제공자를 쓸 수 없음. 조건 추출 제어는 다른 방법으로 넘어간다."""


def _pid(provider):
    p = (provider or config.LLM_PROVIDER or "gemini").lower()
    if p not in PROVIDERS:
        raise LLMUnavailableError(f"알 수 없는 제공자 {p}")
    return p


def has_key(provider=None):
    return bool(PROVIDERS[_pid(provider)]["key"]())


def model_of(provider=None):
    return PROVIDERS[_pid(provider)]["model"]()


# ---------------------------------------------------------------- 녹화
def _key(provider, model, title, body):
    raw = "\n".join([provider, model, PROMPT_VERSION, title, body])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _rec_path(provider, model, title, body):
    return config.LLM_RECORD_DIR / provider / f"{_key(provider, model, title, body)}.json"


def recorded(provider, title, body):
    p = _rec_path(provider, model_of(provider), title, body)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_recording(provider, model, title, body, data, latency_ms):
    p = _rec_path(provider, model, title, body)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "provider": provider,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "latency_ms": latency_ms,
                "title": title,
                "response": data,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def recording_count(provider):
    d = config.LLM_RECORD_DIR / provider
    return len(list(d.glob("*.json"))) if d.exists() else 0


def can_use(provider=None):
    """키가 있거나(live/auto) 녹화가 하나라도 있으면(auto/replay) 쓸 수 있다."""
    p = _pid(provider)
    if config.LLM_MODE == "replay":
        return recording_count(p) > 0
    return has_key(p) or (config.LLM_MODE == "auto" and recording_count(p) > 0)


def available():
    """화면 아래 상태 표시용: 지금 설정된 제공자를 쓸 수 있는지."""
    try:
        return can_use()
    except LLMUnavailableError:
        return False


def provider_name(provider=None):  # 설계 외: 화면·기록용 이름
    """화면·기록에 쓰는 제공자 이름 (예: Gemini)."""
    try:
        return PROVIDERS[_pid(provider)]["name"]
    except LLMUnavailableError:
        return str(provider or config.LLM_PROVIDER)


def status_text():
    try:
        p = _pid(None)
    except LLMUnavailableError as e:
        return str(e)
    name, model = PROVIDERS[p]["name"], model_of(p)
    fallback = "예시 결과·규칙 기반" if config.DEMO_MODE else "확인 필요로 저장"
    if config.LLM_MODE == "replay":
        return f"{name} 녹화 재생 ({recording_count(p)}건, API 호출 안 함)"
    if has_key(p):
        return f"{name} API ({model}) · 녹화 {recording_count(p)}건"
    if recording_count(p):
        return f"{name} 키 없음 → 녹화 {recording_count(p)}건만 재생, 나머지는 {fallback}"
    return f"API 키 없음 → {fallback}"


# ---------------------------------------------------------------- 제공자별 호출
def _call_gemini(title, body):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": PROMPT.format(title=title, body=body[:12000])}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    try:
        r = requests.post(
            url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=payload, timeout=config.LLM_TIMEOUT
        )
    except requests.RequestException as e:
        raise LLMError(f"응답 없음: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("응답 형식 오류") from e


def _call_anthropic(title, body):
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "temperature": 0,
        "tools": [
            {
                "name": "report_conditions",
                "description": "공지에서 뽑은 모집 여부, 마감일, 지원 자격 조건을 보고한다.",
                "input_schema": TOOL_SCHEMA,
            }
        ],
        "tool_choice": {"type": "tool", "name": "report_conditions"},
        "messages": [{"role": "user", "content": PROMPT.format(title=title, body=body[:12000])}],
    }
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=config.LLM_TIMEOUT
        )
    except requests.RequestException as e:
        raise LLMError(f"응답 없음: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        for block in r.json()["content"]:
            if block.get("type") == "tool_use":
                return block["input"]
    except (KeyError, ValueError) as e:
        raise LLMError("응답 형식 오류") from e
    raise LLMError("응답에 도구 호출이 없음")


_CALL = {"gemini": _call_gemini, "anthropic": _call_anthropic}


def check_shape(data):
    """응답 형식 검사. JSON 스키마를 강제해도 형식이 어긋난 응답이 올 수 있어(예: conditions가 문자열 목록)
    여기서 걸러 LLMError로 돌려보낸다 → 조건 추출 제어가 최대 3회 재시도 (UC4 예외 2)."""
    if not isinstance(data, dict):
        raise LLMError("응답 형식 오류: 객체가 아님")
    if not isinstance(data.get("is_recruitment", True), bool):
        raise LLMError("응답 형식 오류: is_recruitment")
    conds = data.get("conditions")
    if not isinstance(conds, list):
        raise LLMError("응답 형식 오류: conditions 없음")
    for c in conds:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) for k in ("item", "value", "evidence")):
            raise LLMError("응답 형식 오류: 조건이 item·value·evidence 객체가 아님")
        if c["item"] not in ITEMS:
            raise LLMError(f"응답 형식 오류: 알 수 없는 항목 {c['item']}")
    for k in ("deadline", "deadline_evidence"):
        if data.get(k) is not None and not isinstance(data[k], str):
            raise LLMError(f"응답 형식 오류: {k}")
    return data


def extract_conditions(title, body, provider=None, mode=None):  # 조건을 추출한다(본문) : 응답
    """(응답, 정보). 정보 = provider, model, how('live'|'replay'), recorded_at, latency_ms."""
    p = _pid(provider)
    mode = (mode or config.LLM_MODE).lower()
    model = model_of(p)
    if mode in ("auto", "replay"):
        rec = recorded(p, title, body)
        if rec is not None:
            return check_shape(rec["response"]), {
                "provider": p,
                "model": rec["model"],
                "how": "replay",
                "recorded_at": rec["recorded_at"],
                "latency_ms": rec.get("latency_ms"),
            }
        if mode == "replay":
            raise LLMUnavailableError("녹화 없음")
    if not has_key(p):
        raise LLMUnavailableError(f"{PROVIDERS[p]['name']} API 키 없음")
    t0 = time.perf_counter()
    data = _CALL[p](title, body)
    latency = int((time.perf_counter() - t0) * 1000)
    check_shape(data)  # 형식이 틀린 응답은 녹화하지 않는다
    _save_recording(p, model, title, body, data, latency)
    return data, {"provider": p, "model": model, "how": "live", "recorded_at": None, "latency_ms": latency}
