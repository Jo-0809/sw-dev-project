"""시연 시나리오 전체 흐름 (UC1 → UC2 → UC3 → UC4 → UC5). 처음에 시연 초기화를 해서 다른 테스트 순서와 상관없이 돈다."""

import requests
from conftest import BASE


def test_full_scenario(server):
    from app.demo import mockdata, seed
    from app.pd.collect.collect_ctl import collector
    from app.pd.notice import query_ctl
    from app.pd.source import source
    from app.pd.user import account

    seed.reset_demo_data()
    collector.reset_last_run()
    s = requests.Session()
    # UC1 예외 2, 예외 1, 정상
    assert "필수 항목을 입력하세요" in s.post(BASE + "/login", data={"login_id": "", "password": ""}).text
    assert "올바르지 않습니다" in s.post(BASE + "/login", data={"login_id": "demo-t", "password": "x"}).text
    r = s.post(BASE + "/login", data={"login_id": "demo-t", "password": "Tq7-demo-pw", "auto": "on"})
    assert r.url.endswith("/profile?first=1")  # 메인 진입(/) → 프로필 없음 → 2-1
    assert "프로필을 먼저 입력하세요" in r.text
    # UC2 예외 1 → 정상
    assert "학과와 학년은 반드시" in s.post(BASE + "/profile", data={"first": 1, "status": "재학"}).text
    r = s.post(
        BASE + "/profile",
        data={
            "first": 1,
            "university": "경상국립대학교",
            "department": "소프트웨어공학과",
            "grade": "2",
            "status": "재학",
        },
    )
    assert "관심 출처를 먼저 등록하세요" in r.text  # 5-6 (관심 출처 없음)
    # UC3 예외 1, 예외 2, 정상
    t = s.post(BASE + "/sources/address", data={"address": BASE + "/nope/na/ntt/selectNttList.do?mi=1&bbsId=2"}).text
    assert "해당 주소에 접속할 수 없습니다" in t
    t = s.post(
        BASE + "/sources/address", data={"address": BASE + "/mock/edu/na/ntt/selectNttList.do?mi=9001&bbsId=9999"}
    ).text
    assert "수집이 허용되지 않는 게시판입니다" in t
    mock_ids = [x["id"] for x in source.all() if "[모의]" in x["name"]]
    s.post(BASE + "/sources/register", data={"source_ids": mock_ids})
    # UC4: 수집 (동기 실행)
    res = collector.start()["results"]
    assert sum(r["new"] for r in res) == 9 and sum(r["failed"] for r in res) == 1
    assert {r["path"] for r in res} == {"RSS", "목록 HTML"}
    # UC5
    aid = account.match("demo-t", "Tq7-demo-pw")
    lst = query_ctl.request_list(aid)
    titles = [i["notice"]["title"] for i in lst["items"]]
    assert titles == [
        "소프트웨어공학과 전공 멘토링 멘티 모집",
        "2026 GNU SW 해커톤 참가자 모집",
        "2026 동계 해외 단기연수 프로그램 참가자 모집",
        "2027학년도 1학기 교환학생 선발 공고",
    ]
    allv = {i["notice"]["title"]: i["verdict"] for i in query_ctl.request_all(aid)["items"]}
    assert allv["2026 동계 산학협력 현장실습(인턴십) 참여 학생 모집"] == "지원 불가"
    assert allv["대학 홍보 서포터즈 '경상누리' 7기 모집"] == "확인 필요"
    assert allv["2027학년도 1학기 학습 튜터링 튜터 모집"] == "확인 필요"
    assert "2026학년도 2학기 국가근로장학생 선발 명단 안내" not in allv  # 모집 공고 아님은 판정 목록에 없음
    folded = [i["notice"]["title"] for i in query_ctl.request_all(aid)["not_recruit"]]
    assert folded == ["2026학년도 2학기 국가근로장학생 선발 명단 안내"]  # 맨 아래에 접어 둠
    page = s.get(BASE + "/notices?view=all").text
    assert "판정 대상이 아닌 공지 1건" in page and 'badge na">모집 공고 아님' not in page
    # 상세 + 열람 기록
    nid = lst["items"][1]["notice"]["id"]
    page = s.get(f"{BASE}/notices/{nid}").text
    assert "지원할 수 있어요" in page and "원문 공지 보기" in page
    assert query_ctl.request_list(aid)["items"][1]["viewed"]
    # 새 공지 게시 → 다시 수집 → 1건만 추가(중복 없음)
    mockdata.publish("8800108")
    res = collector.start()["results"]
    assert sum(r["new"] for r in res) == 1
    # LLM이 원문에 없는 조건을 낸 경우 → 근거 대조기가 걸러 확인 필요
    mockdata.publish("8800109")
    collector.start()
    allv = {i["notice"]["title"]: i for i in query_ctl.request_all(aid)["items"]}
    x = allv["○○장학재단 2027년도 장학생 모집"]
    assert x["verdict"] == "확인 필요" and "원문에 근거 없음" in x["notice"]["extract_note"]
    assert len(query_ctl.request_list(aid)["items"]) == 5
    # 메인 진입(/)은 프로필이 있으면 공고 목록 화면(5-1)으로
    assert s.get(BASE + "/").url.endswith("/notices")
