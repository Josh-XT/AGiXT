from Extensions import Extensions
import os


class macostts(Extensions):
    def __init__(
        self,
        USE_MAC_OS_TTS: bool = False,
        **kwargs,
    ):
        self.USE_MAC_OS_TTS = USE_MAC_OS_TTS
        self.commands = {"Speak with MacOS TTS": self.speak_with_macos_speech}

    def speak_with_macos_speech(self, text: str, voice_index: int = 0) -> bool:
        if voice_index == 0:
            os.system(f'say "{text}"')
        elif voice_index == 1:
            os.system(f'say -v "Ava (Premium)" "{text}"')
        else:
            os.system(f'say -v Samantha "{text}"')
        return True
