from openai import AzureOpenAI
import logging
import time


class AzureProvider:
    def __init__(
        self,
        AZURE_API_KEY: str = "",
        AZURE_OPENAI_ENDPOINT: str = "https://your-endpoint.openai.azure.com",
        AZURE_DEPLOYMENT_NAME: str = "gpt-4o",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 120000,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AZURE_API_KEY = AZURE_API_KEY
        self.AZURE_OPENAI_ENDPOINT = AZURE_OPENAI_ENDPOINT
        self.AI_MODEL = AZURE_DEPLOYMENT_NAME
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 120000
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.failures = 0

    @staticmethod
    def services():
        return ["llm", "vision"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        if not self.AZURE_OPENAI_ENDPOINT.endswith("/"):
            self.AZURE_OPENAI_ENDPOINT += "/"
        openai = AzureOpenAI(
            api_key=self.AZURE_API_KEY,
            api_version="2024-02-01",
            azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
            azure_deployment=self.AI_MODEL,
        )
        if self.AZURE_API_KEY == "" or self.AZURE_API_KEY == "YOUR_API_KEY":
            if self.AZURE_OPENAI_ENDPOINT == "https://your-endpoint.openai.azure.com":
                return "Please go to the Agent Management page to set your Azure OpenAI API key."
        messages = []
        if len(images) > 0:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            )
            for image in images:
                if image.startswith("http"):
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image,
                            },
                        }
                    )
                else:
                    file_type = image.split(".")[-1]
                    with open(image, "rb") as f:
                        image_base64 = f.read()
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{file_type};base64,{image_base64}"
                            },
                        }
                    )
        else:
            messages.append({"role": "user", "content": prompt})
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        try:
            response = openai.chat.completions.create(
                model=self.AI_MODEL,
                messages=messages,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=4096,
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=False,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"Azure OpenAI API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                return "Azure OpenAI API Error: Too many failures."
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens)
            return str(response)
