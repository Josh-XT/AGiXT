#!/bin/bash
pip install poetry==1.5.1
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
cd AGiXT
poetry install --with gpt4free
poetry run playwright install
cd agixt
poetry run uvicorn app:app --host 0.0.0.0 --port 7437 --workers 2 &
uvicorn_pid=$!
cd ../streamlit
poetry run streamlit run Main.py &
streamlit_pid=$!
read -p "Press any key to exit..."
kill $streamlit_pid $uvicorn_pid
wait $streamlit_pid $uvicorn_pid