#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "파이썬이 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서 설치해 주세요."
  read -r -p "엔터를 누르면 닫힙니다."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "처음 실행이라 필요한 프로그램을 설치합니다. 몇 분 걸립니다..."
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || { echo "설치 중 오류가 났습니다. 인터넷 연결을 확인해 주세요."; read -r; exit 1; }
echo "브라우저에서 프로그램이 열립니다. 이 창을 닫으면 프로그램이 종료됩니다."
.venv/bin/python -m streamlit run app.py --browser.gatherUsageStats false
