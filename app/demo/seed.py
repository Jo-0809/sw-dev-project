"""시연 데이터 넣기·지우기 (시연 모드 전용). 운영 코드는 이 모듈을 부르지 않는다 (app/main.py 만 부름).

run()             실패 확인 출처, 시연 계정, 모의 게시판 출처를 넣는다 (예전 판의 흔한 비밀번호 계정 정리 포함)
reset_demo_data() 수집한 공지·조건·기록·프로필·관심 출처·직접 입력 출처를 지운다 (계정은 남김)
"""

from .. import config
from ..dm.db import connect
from ..pd.source import source
from ..pd.user import account
from . import mockdata

# 시연용 실패 확인 출처 (게시판 번호 오타 → '시스템안내' 화면 → 번호 확보 실패)
TEST_SOURCES = [
    ("[실패 확인] 대학 공지 – 장학 (bbsId 오타 1076)", "https://www.gnu.ac.kr/main", "1376", "1076", 1),
]
# v2.4까지의 시연 계정. 흔한 비밀번호라 브라우저가 '유출된 비밀번호' 경고를 띄워서 정리한다.
LEGACY_DEMO_ACCOUNTS = [("demo", "demo1234"), ("test", "test1234")]
MOCK_BOARDS = ("scholar", "external", "sw")


def retag_test_sources():
    """v2.1까지는 실패 확인 출처(bbsId 오타 1076)를 'preset' 으로 넣었다. 시연용임을 구분하려고 'test' 로 바꾼다."""
    with connect() as c:
        c.execute("UPDATE source SET kind='test' WHERE kind='preset' AND mi='1376' AND bbs_id='1076'")


def _clean_legacy_accounts(demo_id, demo_pw):
    for old_id, old_pw in LEGACY_DEMO_ACCOUNTS:
        if (old_id, old_pw) == (demo_id, demo_pw) or not account.match(old_id, old_pw):
            continue
        if old_id == "demo" and account.rename(old_id, demo_id):
            continue  # 예전 시연 계정은 새 아이디로 (프로필·관심 출처 유지)
        account.remove(old_id)


def run():
    retag_test_sources()
    for name, site, mi, bbs, rss in TEST_SOURCES:
        source.seed("test", name, site, mi, bbs, rss)
    demo_id, demo_pw = config.demo_credentials()  # 시연 계정 (회원가입은 범위 밖)
    _clean_legacy_accounts(demo_id, demo_pw)
    account.set_password(demo_id, demo_pw)  # 비밀번호가 바뀌었으면 적용하고 예전 세션을 끊음
    for key in MOCK_BOARDS:
        b = mockdata.BOARDS[key]
        source.seed(
            "mock",
            f"[모의] {b['name']}" + ("" if b["rss"] else " (RSS 없음)"),
            f"{config.SELF_URL}/mock/{b['site']}",
            b["mi"],
            b["bbs"],
            1 if b["rss"] else 0,
        )


def reset_demo_data():
    """시연 초기화. DB 전체를 지우므로 시연 모드에서만 부른다."""
    with connect() as c:
        for t in ("view_log", "condition", "notice", "failure_log", "subscription", "profile"):
            c.execute(f"DELETE FROM {t}")
        c.execute("DELETE FROM source WHERE kind='custom'")
    mockdata.reset()
