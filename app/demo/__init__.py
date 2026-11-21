"""시연·측정용 코드 (클래스 다이어그램 밖, 계층 밖). 운영 코드(app/hci·pd·dm)는 이 패키지를 불러오지 않는다.
app/main.py 가 시연 모드(DEMO_MODE=1)일 때만 demo_routes.install() 로 넣는다.

mockboard.py / mockdata.py : 모의 게시판 (경상국립대 게시판과 같은 주소·화면 구조)
examples.py                : 키도 녹화도 없을 때 쓰는 예시 결과 (사람이 작성, LLM 출력 아님) + 대체 결과 제공자
rule_based.py              : 규칙 기반 추출 (정규식). 예시 결과도 없을 때, 채점의 기준선
evaluation.py              : 추출 API 비교·채점
seed.py                    : 시연 계정·실패 확인 출처·모의 출처 넣기, 시연 초기화
demo_routes.py             : 지금 수집, 시연 초기화, 추출 API 비교 화면, 관심 출처·공고 목록 화면의 시연 패널
fixtures/, templates/      : 예시 결과 데이터, 시연 화면 템플릿
시연 날짜 고정(DEMO_TODAY)과 시연 모드(DEMO_MODE)는 app/config.py 에 있다.
"""
