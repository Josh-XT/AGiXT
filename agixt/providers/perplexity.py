import asyncio
import json
import logging
import time
from os import path

import requests
import random
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from bs4 import BeautifulSoup
from websocket import WebSocketApp
from uuid import uuid4
from threading import Thread


def souper(x):
    return BeautifulSoup(x, "lxml")


class Emailnator:
    def __init__(
        self, headers, cookies, domain=False, plus=True, dot=True, google_mail=False
    ):
        self.inbox = []
        self.inbox_ads = []

        self.s = requests.Session()
        self.s.headers.update(headers)
        self.s.cookies.update(cookies)

        data = {"email": []}

        if domain:
            data["email"].append("domain")
        if plus:
            data["email"].append("plusGmail")
        if dot:
            data["email"].append("dotGmail")
        if google_mail:
            data["email"].append("googleMail")

        response = self.s.post(
            "https://www.emailnator.com/generate-email", json=data
        ).json()
        self.email = response["email"][0]

        for ads in self.s.post(
            "https://www.emailnator.com/message-list", json={"email": self.email}
        ).json()["messageData"]:
            self.inbox_ads.append(ads["messageID"])

    def reload(self, wait=False, retry_timeout=5):
        self.new_msgs = []

        while True:
            for msg in self.s.post(
                "https://www.emailnator.com/message-list", json={"email": self.email}
            ).json()["messageData"]:
                if msg["messageID"] not in self.inbox_ads and msg not in self.inbox:
                    self.new_msgs.append(msg)

            if wait and not self.new_msgs:
                time.sleep(retry_timeout)
            else:
                break

        self.inbox += self.new_msgs
        return self.new_msgs

    def open(self, msg_id):
        return self.s.post(
            "https://www.emailnator.com/message-list",
            json={"email": self.email, "messageID": msg_id},
        ).text


class Client:
    def __init__(self, headers, cookies):
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.cookies.update(cookies)
        self.session.get(f"https://www.perplexity.ai/search/{str(uuid4())}")

        self.t = format(random.getrandbits(32), "08x")
        self.sid = json.loads(
            self.session.get(
                f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}"
            ).text[1:]
        )["sid"]
        self.frontend_uuid = str(uuid4())
        self.frontend_session_id = str(uuid4())
        self._last_answer = None
        self._last_file_upload_info = None
        self.copilot = 0
        self.file_upload = 0
        self.n = 1

        assert (
            self.session.post(
                f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
                data='40{"jwt":"anonymous-ask-user"}',
            ).text
            == "OK"
        ), "Error authenticating"

        self.ws = WebSocketApp(
            url=f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            cookie="; ".join(
                [f"{x}={y}" for x, y in self.session.cookies.get_dict().items()]
            ),
            on_open=lambda ws: ws.send("2probe"),
            on_message=self.on_message,
            on_error=lambda ws, err: print(f"Error: {err}"),
        )

        Thread(target=self.ws.run_forever).start()
        time.sleep(1)

    def create_account(self, headers, cookies):
        emailnator_cli = Emailnator(headers, cookies, dot=False, google_mail=True)
        resp = self.session.post(
            "https://www.perplexity.ai/api/auth/signin/email",
            data={
                "email": emailnator_cli.email,
                "csrfToken": self.session.cookies.get_dict()[
                    "next-auth.csrf-token"
                ].split("%")[0],
                "callbackUrl": "https://www.perplexity.ai/",
                "json": "true",
            },
        )

        if resp.ok:
            new_msgs = emailnator_cli.reload(wait=True)
            new_account_link = (
                souper(emailnator_cli.open(new_msgs[0]["messageID"]))
                .select("a")[1]
                .get("href")
            )

            self.session.get(new_account_link)
            self.session.get("https://www.perplexity.ai/")

            self.copilot = 5
            self.file_upload = 3

            return True
        return False

    def on_message(self, ws, message):
        if message == "2":
            ws.send("3")
        elif message == "3probe":
            ws.send("5")

        if message.startswith(str(430 + self.n)):
            response = json.loads(message[3:])[0]

            if "text" in response:
                response["text"] = json.loads(response["text"])
                self._last_answer = response

            else:
                self._last_file_upload_info = response

    def search(self, query, mode="concise", focus="internet", file=None):
        assert mode in ["concise", "copilot"], 'Search modes --> ["concise", "copilot"]'
        assert focus in [
            "internet",
            "scholar",
            "writing",
            "wolfram",
            "youtube",
            "reddit",
            "wikipedia",
        ], 'Search focus modes --> ["internet", "scholar", "writing", "wolfram", "youtube", "reddit", "wikipedia"]'
        assert (
            self.copilot > 0 if mode == "copilot" else True
        ), "You have used all of your copilots"
        assert (
            self.file_upload > 0 if file else True
        ), "You have used all of your file uploads"

        self.copilot = self.copilot - 1 if mode == "copilot" else self.copilot
        self.file_upload = self.file_upload - 1 if file else self.file_upload
        self.n += 1
        self._last_answer = None
        self._last_file_upload_info = None

        if file:
            self.ws.send(
                f"{420 + self.n}"
                + json.dumps(
                    [
                        "get_upload_url",
                        {
                            "content_type": {
                                "txt": "text/plane",
                                "pdf": "application/pdf",
                            }[file[1]]
                        },
                    ]
                )
            )

            while not self._last_file_upload_info:
                pass

            if not self._last_file_upload_info["success"]:
                raise Exception("File upload error", self._last_file_upload_info)

            monitor = MultipartEncoderMonitor(
                MultipartEncoder(
                    fields={
                        **self._last_file_upload_info["fields"],
                        "file": (
                            "myfile",
                            file[0],
                            {"txt": "text/plane", "pdf": "application/pdf"}[file[1]],
                        ),
                    }
                )
            )

            if not (
                upload_resp := requests.post(
                    self._last_file_upload_info["url"],
                    data=monitor,
                    headers={"Content-Type": monitor.content_type},
                )
            ).ok:
                raise Exception("File upload error", upload_resp)

            uploaded_file = self._last_file_upload_info[
                "url"
            ] + self._last_file_upload_info["fields"]["key"].replace(
                "${filename}", "myfile"
            )

            self.ws.send(
                f"{420 + self.n}"
                + json.dumps(
                    [
                        "perplexity_ask",
                        query,
                        {
                            "attachments": [uploaded_file],
                            "source": "default",
                            "mode": mode,
                            "last_backend_uuid": None,
                            "read_write_token": "",
                            "conversational_enabled": True,
                            "frontend_session_id": self.frontend_session_id,
                            "search_focus": focus,
                            "frontend_uuid": self.frontend_uuid,
                            "gpt4": False,
                            "language": "en-US",
                        },
                    ]
                )
            )

        else:
            self.ws.send(
                f"{420 + self.n}"
                + json.dumps(
                    [
                        "perplexity_ask",
                        query,
                        {
                            "source": "default",
                            "mode": mode,
                            "last_backend_uuid": None,
                            "read_write_token": "",
                            "conversational_enabled": True,
                            "frontend_session_id": self.frontend_session_id,
                            "search_focus": focus,
                            "frontend_uuid": self.frontend_uuid,
                            "gpt4": False,
                            "language": "en-US",
                        },
                    ]
                )
            )

        while not self._last_answer:
            pass

        return self._last_answer


# Code above is copied from https://github.com/helallao/perplexity-ai/blob/main/perplexity.py

DEFAULT_PERPLEXITY_COOKIE_PATH = "./perplexity-cookies.json"
DEFAULT_EMAILNATOR_COOKIE_PATH = "./emailnator-cookies.json"


class PerplexityProvider:
    def __init__(
        self,
        FOCUS: str = "internet",
        PERPLEXITY_COOKIE_PATH: str = DEFAULT_PERPLEXITY_COOKIE_PATH,
        EMAILNATOR_COOKIE_PATH: str = DEFAULT_EMAILNATOR_COOKIE_PATH,
        **kwargs,
    ):
        self.perplexity_cli = None
        self.requirements = ["requests", "bs4", "websocket-client", "requests-toolbelt"]
        self.PERPLEXITY_COOKIE_PATH = (
            PERPLEXITY_COOKIE_PATH
            if PERPLEXITY_COOKIE_PATH
            else DEFAULT_PERPLEXITY_COOKIE_PATH
        )
        self.EMAILNATOR_COOKIE_PATH = (
            EMAILNATOR_COOKIE_PATH
            if EMAILNATOR_COOKIE_PATH
            else DEFAULT_EMAILNATOR_COOKIE_PATH
        )
        self.FOCUS = FOCUS
        self.exec_nb = 5  # set to 5 as default to automatically renewed copilot
        self.AI_MODEL = "perplexity"
        self.MAX_TOKENS = 4096

    def load_account(
        self,
    ):
        try:
            with open(
                self.PERPLEXITY_COOKIE_PATH,
                "r",
            ) as f:
                curl = json.loads(f.read())
            cookies = curl["cookies"]
            headers = curl["headers"]
            self.perplexity_cli = Client(headers, cookies)

        except Exception as e:
            print("Error loading account you must renew cookies", e)
            logging.info(e)

    def reload_account(self):
        if self.exec_nb > 5:
            if path.isfile(self.EMAILNATOR_COOKIE_PATH):
                with open(
                    self.EMAILNATOR_COOKIE_PATH,
                    "r",
                ) as f:
                    curl = json.loads(f.read())
                cookies = curl["cookies"]
                headers = curl["headers"]
                if not self.perplexity_cli.create_account(headers, cookies):
                    print("Error creating account")
                else:
                    print("Account successfully created")
                self.exec_nb = 1

    async def instruct(self, prompt, tokens: int = 0):
        self.exec_nb += 1
        if self.perplexity_cli is None:
            self.load_account()
        self.reload_account()
        response = self.perplexity_cli.search(
            prompt,
            mode="copilot",
            focus=self.FOCUS,
        )
        if response["status"] == "completed":
            return response
        return "Error not completed"


if __name__ == "__main__":
    perplexity = PerplexityProvider()
    response = {}
    perplexity.load_account()

    async def run_test():
        global response
        response = await perplexity.instruct(
            "Tell me what's going on in the world today?"
        )
        print(response)

    asyncio.run(run_test())
