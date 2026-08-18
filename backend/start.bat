@echo off
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install wheel
pip install greenlet --prefer-binary
pip install -r requirements.txt --prefer-binary
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
