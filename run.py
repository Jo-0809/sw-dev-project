"""놓칠뻔 데모 실행: python run.py  →  브라우저에서 http://127.0.0.1:8000"""

import uvicorn

from app import config

if __name__ == "__main__":
    if config.DEMO_MODE:
        demo_id, demo_pw = config.demo_credentials()
        who = f"시연 모드 · 시연 계정 {demo_id} / {demo_pw}"
    else:
        who = "운영 모드 · 계정은 tools/create_account.py 로 만듦"
    print(f"\n  놓칠뻔 데모: {config.SELF_URL}  ({who})\n")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info")
