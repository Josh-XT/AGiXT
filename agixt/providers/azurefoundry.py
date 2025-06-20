import os
import base64
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
import logging
import time


class AzurefoundryProvider:
    """
    This provider uses the Azure AI Foundry Inference API to generate text from prompts. Learn more about how to set it up at <https://learn.microsoft.com/en-us/azure/ai-services/>.
    """

    def __init__(
        self,
        AZURE_API_KEY: str = "",
        AZURE_OPENAI_ENDPOINT: str = "https://your-endpoint.openai.azure.com",
        AZURE_DEPLOYMENT_NAME: str = "gpt-4o",
        AZURE_TEMPERATURE: float = 0.7,
        AZURE_TOP_P: float = 0.7,
        AZURE_MAX_TOKENS: int = 120000,
        AZURE_WAIT_BETWEEN_REQUESTS: int = 1,
        AZURE_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.friendly_name = "Azure"
        self.requirements = ["azure-ai-inference"]
        self.AZURE_API_KEY = AZURE_API_KEY
        self.AZURE_OPENAI_ENDPOINT = AZURE_OPENAI_ENDPOINT
        self.AI_MODEL = AZURE_DEPLOYMENT_NAME
        self.AI_TEMPERATURE = AZURE_TEMPERATURE if AZURE_TEMPERATURE else 0.7
        self.AI_TOP_P = AZURE_TOP_P if AZURE_TOP_P else 0.7
        self.MAX_TOKENS = AZURE_MAX_TOKENS if AZURE_MAX_TOKENS else 120000
        self.WAIT_AFTER_FAILURE = (
            AZURE_WAIT_AFTER_FAILURE if AZURE_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            AZURE_WAIT_BETWEEN_REQUESTS if AZURE_WAIT_BETWEEN_REQUESTS else 1
        )
        self.failures = 0

    @staticmethod
    def services():
        return ["llm", "vision"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        if self.AZURE_API_KEY == "" or self.AZURE_API_KEY == "YOUR_API_KEY":
            return "Please go to the Agent Management page to set your Azure AI Inference API key."
        
        try:
            client = ChatCompletionsClient(
                endpoint=self.AZURE_OPENAI_ENDPOINT,
                credential=AzureKeyCredential(self.AZURE_API_KEY),
                api_version="2024-05-01-preview"
            )
        except Exception as e:
            logging.warning(f"Azure AI Inference Client Error: {e}")
            return f"Failed to initialize Azure AI Inference client: {e}"

        messages = []
        
        if len(images) > 0:
            # Create user message with text and images
            content = [{"type": "text", "text": prompt}]
            
            for image in images:
                if image.startswith("http"):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": image,
                        },
                    })
                else:
                    file_type = image.split(".")[-1]
                    with open(image, "rb") as f:
                        image_data = f.read()
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{file_type};base64,{image_base64}"
                        },
                    })
            
            messages = [
                SystemMessage(content="You are a helpful assistant."),
                UserMessage(content=content)
            ]
        else:
            messages = [
                SystemMessage(content="You are a helpful assistant."),
                UserMessage(content=prompt)
            ]

        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        
        try:
            response = client.complete(
                messages=messages,
                model=self.AI_MODEL,
                max_tokens=min(int(self.MAX_TOKENS), 4096),
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
                presence_penalty=0.0,
                frequency_penalty=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"Azure AI Inference API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"Azure AI Inference API Error: Too many failures. {e}")
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
            return f"Error: {e}"
