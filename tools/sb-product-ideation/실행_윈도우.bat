@echo off
chcp 65001 > nul
cd /d "%~dp0"
where py > nul 2>&1 && (set PY=py -3) || (set PY=python)
%PY% --version > nul 2>&1
if errorlevel 1 (
  echo 파이썬이 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서 설치해 주세요.
  echo 설치할 때 "Add python.exe to PATH"를 꼭 체크해 주세요.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo 처음 실행이라 필요한 프로그램을 설치합니다. 몇 분 걸립니다...
  %PY% -m venv .venv
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo 설치 중 오류가 났습니다. 인터넷 연결을 확인해 주세요.
  pause
  exit /b 1
)
echo 브라우저에서 프로그램이 열립니다. 이 창을 닫으면 프로그램이 종료됩니다.
".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats false
pause
