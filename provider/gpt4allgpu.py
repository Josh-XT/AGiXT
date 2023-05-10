from Config import Config

try:
    from nomic.gpt4all import GPT4AllGPU as GPT4All
except ImportError:
    print("Failed to import gpt4allgpu.")

CFG = Config()


class Gpt4allgpuProvider:
    def __init__(self):
        try:
            self.max_tokens = int(CFG.MAX_TOKENS)
        except:
            self.max_tokens = 2000
        # GPT4All will just download the model, maybe save it in our workspace?
        self.model = GPT4All(llama_path=CFG.AI_MODEL)
        self.config = {
            "num_beams": 2,
            "min_new_tokens": 10,
            "max_length": 100,
            "repetition_penalty": 2.0,
        }
        # TODO: Need to reseach to add temperature, no obvious flag.

    def instruct(self, prompt):
        return self.model.generate(prompt, self.config)
