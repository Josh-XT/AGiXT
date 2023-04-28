from Config import Config
from requests.sessions import Session
from json import loads

CFG = Config()


class AIProvider:
    def instruct(self, prompt: str) -> str:
        session = Session()
        session.get(url="https://huggingface.co/chat/")
        res = session.post(url="https://huggingface.co/chat/conversation")
        assert res.status_code == 200, "Failed to create new conversation"
        conversation_id = res.json()["conversationId"]
        url = f"https://huggingface.co/chat/conversation/{conversation_id}"
        max_tokens = int(CFG.MAX_TOKENS) - len(prompt)

        if max_tokens > 1904:
            max_tokens = 1904

        res = session.post(
            url=url,
            json={
                "inputs": prompt,
                "parameters": {
                    "temperature": float(CFG.AI_TEMPERATURE),
                    "top_p": 0.95,
                    "repetition_penalty": 1.2,
                    "top_k": 50,
                    "truncate": 1024,
                    "watermark": False,
                    "max_new_tokens": max_tokens - len(prompt),
                    "stop": ["<|endoftext|>"],
                    "return_full_text": False,
                },
                "stream": True,
                "options": {"use_cache": False},
            },
            stream=True,
        )

        assert res.status_code == 200, "Failed to send message"

        last_response = None
        for chunk in res.iter_content(chunk_size=None):
            if chunk:
                data = loads(chunk.decode("utf-8")[5:])
                if "error" not in data:
                    last_response = data
                else:
                    print("error: ", data["error"])
                    break
        return last_response["generated_text"]
