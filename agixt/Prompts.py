import os


class Prompts:
    def add_prompt(self, prompt_name, prompt):
        # if prompts folder does not exist, create it
        if not os.path.exists("prompts"):
            os.mkdir("prompts")
        # if prompt file does not exist, create it
        if not os.path.exists(os.path.join("prompts", f"{prompt_name}.txt")):
            with open(os.path.join("prompts", f"{prompt_name}.txt"), "w") as f:
                f.write(prompt)

    def get_prompt(self, prompt_name, model="default"):
        try:
            with open(f"prompts/{model}/{prompt_name}.txt", "r") as f:
                return f.read()
        except:
            try:
                with open(os.path.join("prompts", f"{prompt_name}.txt"), "r") as f:
                    prompt = f.read()
                return prompt
            except:
                return ""

    def get_prompts(self):
        # Get all files in prompts folder that end in .txt and replace .txt with empty string
        prompts = []
        for file in os.listdir("prompts"):
            if file.endswith(".txt"):
                prompts.append(file.replace(".txt", ""))
        return prompts

    def get_prompt_args(self, prompt_name):
        prompt = self.get_prompt(prompt_name)
        # Find anything in the file between { and } and add them to a list to return
        prompt_vars = []
        for word in prompt.split():
            if word.startswith("{") and word.endswith("}"):
                prompt_vars.append(word[1:-1])
        return prompt_vars

    def delete_prompt(self, prompt_name):
        os.remove(os.path.join("prompts", f"{prompt_name}.txt"))

    def update_prompt(self, prompt_name, prompt):
        with open(os.path.join("prompts", f"{prompt_name}.txt"), "w") as f:
            f.write(prompt)

    def get_model_prompt(self, prompt_name, model="default"):
        with open(f"prompts/{model}/{prompt_name}.txt", "r") as f:
            return f.read()
