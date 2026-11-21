"""녹화된 LLM 응답만으로 다시 채점한다 (API 호출 없음). 라벨(evaluation/labels.json)을 고친 뒤 돌린다.

python tools/score.py
"""

import subprocess
import sys
from pathlib import Path

sys.exit(subprocess.call([sys.executable, str(Path(__file__).with_name("compare_llm.py")), "--mode", "replay"]))
