import json
import ssl
import httpx
import websockets.client as websockets
from selenium import webdriver
from Config import Config

CFG = Config()

class AIProvider:
    def __init__(self):
        if CFG.AI_PROVIDER.lower() == "bing":
            self.wss = None
            driver = webdriver.Chrome()
            driver.get("https://www.bing.com/")
            self.cookies = driver.get_cookies()
            driver.quit()
            self.conversation = self._create_conversation()
            self.wss_link = "wss://sydney.bing.com/sydney/ChatHub"

    def _create_conversation(self):
        session = httpx.Client()
        for cookie in self.cookies:
            session.cookies.set(cookie["name"], cookie["value"])
        response = session.get(
            url="https://edgeservices.bing.com/edgesvc/turing/conversation/create",
        )
        if response.status_code != 200:
            raise Exception("Authentication failed")
        return response.json()

    def instruct(self, prompt: str):
        if CFG.BING_CONVERSATION_STYLE == "creative":
            style_value = "h3imaginative,clgalileo,gencontentv3"
        elif CFG.BING_CONVERSATION_STYLE == "balanced":
            style_value = "galileo"
        elif CFG.BING_CONVERSATION_STYLE == "precise":
            style_value = "h3precise,clgalileo"
        else:
            style_value = "galileo"

        with websockets.connect(self.wss_link, ssl=ssl.create_default_context()) as websocket:
            websocket.send(json.dumps({"protocol": "json", "version": 1}))
            websocket.recv()
            request = {
                "arguments": [
                    {
                        "source": "cib",
                        "optionsSets": [style_value],
                        "message": {
                            "author": "user",
                            "inputMethod": "Keyboard",
                            "text": prompt,
                            "messageType": "Chat",
                        },
                        "conversationSignature": self.conversation["conversationSignature"],
                        "participant": {
                            "id": self.conversation["clientId"],
                        },
                        "conversationId": self.conversation["conversationId"],
                    },
                ],
                "target": "chat",
                "type": 4,
            }
            websocket.send(json.dumps(request))
            response = websocket.recv()
        response_data = json.loads(response)
        return response_data["item"]["messages"][1]["adaptiveCards"][0]["body"][0]["text"]
