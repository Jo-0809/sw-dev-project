"""계정 만들기 — 회원가입 화면은 범위 밖이라, 시연 모드가 아닐 때(DEMO_MODE=0) 쓸 계정을 여기서 만든다.

    python tools/create_account.py 아이디
비밀번호는 화면에 보이지 않게 두 번 입력받는다. 같은 아이디가 있으면 만들지 않는다.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import entity  # noqa: E402
from app.entity import Account  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("사용법: python tools/create_account.py 아이디")
login_id = sys.argv[1].strip()
entity.init_db()
pw = getpass.getpass("비밀번호: ")
if len(pw) < 8:
    sys.exit("비밀번호는 8자 이상으로 하세요.")
if pw != getpass.getpass("비밀번호 확인: "):
    sys.exit("두 비밀번호가 다릅니다.")
before = Account.count()
Account.create(login_id, pw)
print("계정을 만들었습니다." if Account.count() > before else "같은 아이디가 이미 있습니다.")
