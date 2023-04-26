import requests
import random
import re
from Config import Config

CFG = Config()

class AIProvider:
    def instruct(self, prompt, seed=None):
        if seed is None:
            seed = random.randint(1, 1000000000)
        
        params = {
            'prompt': prompt,
            'max_new_tokens': int(CFG.MAX_TOKENS),
            'do_sample': True,
            'temperature': float(CFG.AI_TEMPERATURE),
            'top_p': 0.73,
            'typical_p': 1,
            'repetition_penalty': 1.1,
            'top_k': 0,
            'min_length': 0,
            'no_repeat_ngram_size': 0,
            'num_beams': 1,
            'penalty_alpha': 0,
            'length_penalty': 1,
            'early_stopping': False,
            'seed': seed,
            'add_bos_token': True,
            'truncation_length': 4096,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'stopping_strings': []
        }
        response = requests.post(f"{CFG.AI_PROVIDER_URI}/api/v1/generate", json=params)
        data = None
        if response.status_code == 200:
            data = response.json()['results'][0]['text']
            data = re.sub(r"(?<!\\)\\(?!n)", "", data)
        return data