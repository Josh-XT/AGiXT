from ApiClient import ApiClient


class Voice:
    def __init__(self, agent_name, agent_config):
        self.agent_name = agent_name
        self.agent_config = agent_config

    def voice_chat(self, base64_audio, conversation_name="", **kwargs):
        # Transcribe the audio to text.
        prompt = ApiClient.execute_command(
            agent_name=self.agent_name,
            command_name="Transcribe Base64 Audio",
            command_args={"base64_audio": base64_audio},
        )
        if conversation_name == "":
            conversation_name = f"Voice Chat with {self.agent_name}"
        if "conversation_name" not in kwargs:
            kwargs["conversation_name"] = conversation_name
        if "conversation_results" not in kwargs:
            kwargs["conversation_results"] = 3
        if "context_results" not in kwargs:
            kwargs["context_results"] = 10
        if "prompt_name" not in kwargs:
            kwargs["prompt_name"] = "Voice Chat"
        if "prompt_category" not in kwargs:
            kwargs["prompt_category"] = "Default"
        kwargs["user_input"] = prompt
        # Send the transcribed text to the agent.
        text_response = ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name=kwargs["prompt_name"],
            prompt_args=kwargs,
        )
        # Send the text response to the TTS engine for the agent.
        command_name = "Speak with TTS with Streamlabs Text to Speech"
        if "settings" in self.agent_config:
            # This hierarchy is intentional for the event that multiple TTS engines are enabled for the agent.
            if "USE_STREAMLABS_TTS" in self.agent_config["settings"]:
                if (
                    self.agent_config["settings"]["USE_STREAMLABS_TTS"].lower()
                    == "true"
                ):
                    command_name = "Speak with TTS with Streamlabs Text to Speech"
            if "USE_GTTS" in self.agent_config["settings"]:
                if self.agent_config["settings"]["USE_GTTS"].lower() == "true":
                    command_name = "Speak with GTTS"
            if "USE_HUGGINGFACE_TTS" in self.agent_config["settings"]:
                if (
                    self.agent_config["settings"]["USE_HUGGINGFACE_TTS"].lower()
                    == "true"
                    and "HUGGINGFACE_API_KEY" in self.agent_config["settings"]
                ):
                    if self.agent_config["settings"]["HUGGINGFACE_API_KEY"] != "":
                        command_name = "Read Audio with Huggingface"
            # If there is an elevenlabs API key, it will take precedence over the other TTS engines.
            if "ELEVENLABS_API_KEY" in self.agent_config["settings"]:
                if self.agent_config["settings"]["ELEVENLABS_API_KEY"] != "":
                    command_name = "Speak with TTS Using Elevenlabs"
        # Get the audio response from the TTS engine and return it.
        audio_response = ApiClient.execute_command(
            agent_name=self.agent_name,
            command_name=command_name,
            command_args={"text": text_response},
        )
        return audio_response
