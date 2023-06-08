import socket, errno, subprocess, os, logging

def verify_backend():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.connect(("127.0.0.1", 7437))
        s.close()
    except socket.error as e:
        if e.errno == errno.EADDRINUSE:
            print("Port is already in use")
        else:
            subprocess.Popen(os.system("cd ../agixt/ && poetry run uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4 && cd ../streamlit/"))
            logging.info("LAUNCHED FOR YOU")
            s=None

    if s!=None:
        s.close()