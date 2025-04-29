from Extensions import Extensions
from agixtsdk import AGiXTSDK
from openai import OpenAI
from Globals import getenv
import os


class ai(Extensions):
    """
    The AI extension for AGiXT. This extension provides a set of actions that can be performed by the AI agent.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Chat Completion": self.chat_completions,
            "Generate Image": self.generate_image,
            "Convert Text to Speech": self.text_to_speech,
        }
        self.command_name = (
            kwargs["command_name"] if "command_name" in kwargs else "Smart Prompt"
        )
        self.user = kwargs["user"] if "user" in kwargs else ""
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )

        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )
        self.api_key = kwargs["api_key"] if "api_key" in kwargs else ""
        self.failures = 0

    async def chat_completions(
        self,
        base_url,
        api_key,
        model,
        message_content,
        max_output_tokens=4096,
        temperature=0.7,
        top_p=1.0,
    ):
        """
        Chat completions using a custom API. This command is best used in an automation chain to connect agents to other agents or OpenAI style APIs.

        Args:
            base_url (str): The base URL of the API.
            api_key (str): Your API key for authentication.
            model (str): The model to use for chat completions.
            message_content (str): The content of the message.
            max_output_tokens (int, optional): The maximum number of output tokens. Defaults to 4096.
            temperature (float, optional): The temperature for sampling. Defaults to 0.7.
            top_p (float, optional): The top-p sampling parameter. Defaults to 1.0.

        Returns:
            str: The response from the API.
        """
        try:
            int(max_output_tokens)
        except:
            max_output_tokens = 4096
        try:
            float(temperature)
        except:
            temperature = 0.7
        try:
            float(top_p)
        except:
            top_p = 1.0

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": message_content,
                }
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
            top_p=top_p,
        )
        return response.choices[0].message.content

    async def generate_image(self, prompt):
        """
        Generate an image from a prompt.

        Args:
            prompt (str): The prompt to generate the image from.

        Returns:
            str: The URL of the generated image.
        Note:
            The assistant should send the image URL to the user so they can listen to it, it will embed the image in the chat when the assistant sends the URL.
        """
        return self.ApiClient.generate_image(
            prompt=prompt,
            model=self.agent_name,
        )

    async def text_to_speech(self, text):
        """
        Convert text to speech. The assistant can use its voice to read the text aloud to the user.

        Args:
            text (str): The text to convert to speech.

        Returns:
            str: The URL of the generated audio.

        Note:
            The assistant should send the audio URL to the user so they can listen to it, it will embed the audio in the chat when the assistant sends the URL.
        """
        return self.ApiClient.text_to_speech(
            text=text,
            agent_name=self.agent_name,
        )
