import requests
import json
from Config import Config
CFG = Config()

class AIProvider:
    def instruct(self, prompt):
        params = {
            'max_new_tokens': CFG.MAX_TOKENS,
            'do_sample': True,
            'temperature': CFG.AI_TEMPERATURE,
            'top_p': 0.73,
            'typical_p': 1,
            'repetition_penalty': 1.1,
            'encoder_repetition_penalty': 1.0,
            'top_k': 0,
            'min_length': 0,
            'no_repeat_ngram_size': 0,
            'num_beams': 1,
            'penalty_alpha': 0,
            'length_penalty': 1,
            'early_stopping': False,
            'seed': -1,
            'add_bos_token': True,
            'custom_stopping_strings': [],
            'truncation_length': 2048,
            'ban_eos_token': False,
        }
        payload = json.dumps([prompt, params])
        print("Sending command to API:", payload)  # Added line to print the payload
        response = requests.post(f"{CFG.AI_PROVIDER_URI}/run/textgen", json={
            "data": [
                payload
            ]
        }).json()
        data = response['data'][0]
        # Replace all backslashes in data then return it
        data = data.replace("\\n", "\n")
        data = data.replace("\\'", "'")
        data = data.replace("\\", "")
        data = data.replace("\'", "'")
        return data