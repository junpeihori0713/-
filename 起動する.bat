@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt -q
py -m streamlit run app.py
pause
