#!/bin/bash
#Tested with xterm as well, but no guarantees.
git pull
poetry install --with gpt4free
#If you have problems, comment below line and install playwright for your OS, or increase sleep time
poetry run playwright install
cd agixt
konsole -e "poetry run uvicorn app:app --port 7437 --workders 2" &
uvicorn_pid=$!
sleep 3
cd ../streamlit
konsole -e "poetry run streamlit run Main.py" &
streamlit_pid=$!
read -p "Press any key to exit..."
kill $uvicorn_pid $streamlit_pid
wait $uvicorn_pid $streamlit_pid
