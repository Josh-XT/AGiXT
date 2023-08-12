import os


def get_prompt_file_path(prompt_name, prompt_category="Default"):
    base_path = os.path.join(os.getcwd(), "prompts")
    base_model_path = os.path.normpath(
        os.path.join(os.getcwd(), "prompts", prompt_category)
    )
    model_prompt_file = os.path.normpath(
        os.path.join(base_model_path, f"{prompt_name}.txt")
    )
    default_prompt_file = os.path.normpath(
        os.path.join(base_path, "Default", f"{prompt_name}.txt")
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
    def add_prompt(self, prompt_name, prompt, prompt_category="Default"):
        # if prompts folder does not exist, create it
        file_path = get_prompt_file_path(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        # if prompt file does not exist, create it
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write(prompt)

    def get_prompt(self, prompt_name, prompt_category="Default"):
        prompt_file = get_prompt_file_path(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        with open(prompt_file, "r") as f:
            prompt = f.read()
        return prompt

    def get_prompts(self, prompt_category="Default"):
        # Get all files in prompts folder that end in .txt and replace .txt with empty string
        prompts = []
        # For each folder in prompts folder, get all files that end in .txt and replace .txt with empty string
        base_path = os.path.join("prompts", prompt_category)
        base_path = os.path.join(os.getcwd(), "prompts")
        base_model_path = os.path.normpath(
            os.path.join(os.getcwd(), "prompts", prompt_category)
        )
        if not base_model_path.startswith(base_path) or not base_model_path.startswith(
            base_model_path
        ):
            raise ValueError(
                "Invalid file path. Prompt name cannot contain '/', '\\' or '..' in"
            )
        if not os.path.exists(base_model_path):
            os.mkdir(base_model_path)
        for file in os.listdir(base_model_path):
            if file.endswith(".txt"):
                prompts.append(file.replace(".txt", ""))
        return prompts

    def get_prompt_categories(self):
        prompt_categories = []
        for folder in os.listdir("prompts"):
            if os.path.isdir(os.path.join("prompts", folder)):
                prompt_categories.append(folder)
        return prompt_categories

    def get_prompt_args(self, prompt_text):
        # Find anything in the file between { and } and add them to a list to return
        prompt_vars = []
        for word in prompt_text.split():
            if word.startswith("{") and word.endswith("}"):
                prompt_vars.append(word[1:-1])
        return prompt_vars

    def delete_prompt(self, prompt_name, prompt_category="Default"):
        prompt_file = get_prompt_file_path(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        os.remove(prompt_file)

    def update_prompt(self, prompt_name, prompt, prompt_category="Default"):
        prompt_file = get_prompt_file_path(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        with open(prompt_file, "w") as f:
            f.write(prompt)

    def rename_prompt(self, prompt_name, new_prompt_name, prompt_category="Default"):
        prompt_file = get_prompt_file_path(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        new_prompt_file = get_prompt_file_path(
            prompt_name=new_prompt_name, prompt_category=prompt_category
        )
        os.rename(prompt_file, new_prompt_file)
