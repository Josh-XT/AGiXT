import os
import logging

NGROK_TOKEN = os.environ.get("NGROK_TOKEN", "")
if NGROK_TOKEN:
    from pyngrok import ngrok

    try:
        ngrok.set_auth_token(NGROK_TOKEN)
        public_url = ngrok.connect(7437)
        logging.info(f"[ngrok] Public Tunnel: {public_url.public_url}")
        ngrok_url = public_url.public_url
    except Exception as e:
        logging.error(f"[ngrok] Error: {e}")
        ngrok_url = ""

    def get_ngrok_url():
        global ngrok_url
        return ngrok_url

else:

    def get_ngrok_url():
        return "http://localhost:7437"


if __name__ == "__main__":
    print(get_ngrok_url())
