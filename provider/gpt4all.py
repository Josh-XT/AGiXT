from pathlib import Path

from Config import Config

try:
    from nomic.gpt4all import GPT4All
except ImportError:
    print("Failed to import gpt4all.")

CFG = Config()


class Gpt4allProvider:
    def __init__(self):
        if not CFG.MODEL_PATH and not Path(CFG.MODEL_PATH).exists():
            raise Exception(
                "No MODEL_PATH specified. Download the Model on your machine and mount the directory.\n"
                "Re-downloading the file every time causes server load. Exiting"
            )
        self.model_path = Path(CFG.MODEL_PATH)
        self.model = GPT4All(model_path=self.model_path)
        self.model.open()
        # TODO: Need to research to add temperature, no obvious flag.

    def instruct(self, prompt):
        try:
            return self.model.prompt(prompt)
        except Exception as e:
            return f"GPT4ALL Error: {e}"
