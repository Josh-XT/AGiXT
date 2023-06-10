import socket, errno, subprocess, os, logging
import streamlit as st


def verify_backend():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.connect(("127.0.0.1", 7437))
        s.close()
    except socket.error as e:
        if e.errno == errno.EADDRINUSE:
            print("Port is already in use")
        else:
            try:
                subprocess.Popen(
                    os.system(
                        "cd ../agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4 && cd ../streamlit/"
                    )
                )
                logging.info("LAUNCHED FOR YOU")
                s = None
                st.experimental_rerun()
            except Exception as e:
                logging.info(e)
                print("Press CTRL + C to exit.")
                s.close()

    if s != None:
        s.close()
