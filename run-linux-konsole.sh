#!/bin/bash
git pull
playwright install
cd agixt
pip install --upgrade pip
pip install -r requirements.txt
cd ../streamlit
konsole -e "streamlit run Main.py" &
streamlit_pid=$!
read -p "Press any key to exit..."
kill $streamlit_pid
wait $streamlit_pid
