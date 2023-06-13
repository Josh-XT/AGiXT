import os


def get_prompt_file_path(prompt_name, model="default"):
    base_path = os.path.join(os.getcwd(), "prompts")
    base_model_path = os.path.normpath(os.path.join(os.getcwd(), "prompts", model))
    model_prompt_file = os.path.normpath(
        os.path.join(base_model_path, f"{prompt_name}.txt")
    )
    default_prompt_file = os.path.normpath(
        os.path.join(base_path, f"{prompt_name}.txt")
    )
    if (
        not base_model_path.startswith(base_path)
        or not model_prompt_file.startswith(base_model_path)
        or not default_prompt_file.startswith(base_path)
    ):
        raise ValueError(
            "Invalid file path. Prompt name cannot contain '/', '\\' or '..' in"
        )
    if not os.path.exists(base_path):
        os.mkdir(base_path)
    if not os.path.exists(base_model_path):
        os.mkdir(base_model_path)
    prompt_file = (
        model_prompt_file if os.path.isfile(model_prompt_file) else default_prompt_file
    )
    return prompt_file


class Prompts:
    def add_prompt(self, prompt_name, prompt):
        # if prompts folder does not exist, create it
        file_path = get_prompt_file_path(prompt_name=prompt_name)
        # if prompt file does not exist, create it
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write(prompt)

    def get_prompt(self, prompt_name, model="default"):
        prompt_file = get_prompt_file_path(prompt_name=prompt_name, model=model)
        with open(prompt_file, "r") as f:
            prompt = f.read()
            return prompt

    def get_prompts(self):
        # Get all files in prompts folder that end in .txt and replace .txt with empty string
        prompts = []
        for file in os.listdir("prompts"):
            if file.endswith(".txt"):
                prompts.append(file.replace(".txt", ""))
        return prompts

    def get_prompt_args(self, prompt_name):
        prompt = self.get_prompt(prompt_name=prompt_name)
        # Find anything in the file between { and } and add them to a list to return
        prompt_vars = []
        for word in prompt.split():
            if word.startswith("{") and word.endswith("}"):
                prompt_vars.append(word[1:-1])
        return prompt_vars

    def delete_prompt(self, prompt_name):
        prompt_file = get_prompt_file_path(prompt_name=prompt_name)
        os.remove(prompt_file)

    def update_prompt(self, prompt_name, prompt):
        prompt_file = get_prompt_file_path(prompt_name=prompt_name)
        with open(prompt_file, "w") as f:
            f.write(prompt)

    def get_model_prompt(self, prompt_name, model="default"):
        prompt_file = get_prompt_file_path(prompt_name=prompt_name, model=model)
        with open(prompt_file, "r") as f:
            return f.read()
