from DBConnection import Prompt, PromptCategory, Argument, User, get_session
from Defaults import DEFAULT_USER


class Prompts:
    def __init__(self, user=DEFAULT_USER):
        self.session = get_session()
        self.user = user
        user_data = self.session.query(User).filter(User.email == self.user).first()
        self.user_id = user_data.id

    def add_prompt(self, prompt_name, prompt, prompt_category="Default"):
        if not prompt_category:
            prompt_category = "Default"

        prompt_category = (
            self.session.query(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category,
                PromptCategory.user_id == self.user_id,
            )
            .first()
        )
        if not prompt_category:
            prompt_category = PromptCategory(
                name=prompt_category,
                description=f"{prompt_category} category",
                user_id=self.user_id,
            )
            self.session.add(prompt_category)
            self.session.commit()

        prompt_obj = Prompt(
            name=prompt_name,
            description="",
            content=prompt,
            prompt_category=prompt_category,
            user_id=self.user_id,
        )
        self.session.add(prompt_obj)
        self.session.commit()

        # Populate prompt arguments
        prompt_args = self.get_prompt_args(prompt)
        for arg in prompt_args:
            argument = Argument(
                prompt_id=prompt_obj.id,
                name=arg,
            )
            self.session.add(argument)
        self.session.commit()

    def get_prompt(self, prompt_name, prompt_category="Default"):
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        prompt = (
            self.session.query(Prompt)
            .filter(
                Prompt.name == prompt_name,
                Prompt.user_id == user_data.id,
                Prompt.prompt_category.has(name="Default"),
            )
            .join(PromptCategory)
            .filter(PromptCategory.name == "Default", Prompt.user_id == user_data.id)
            .first()
        )
        if not prompt:
            prompt = (
                self.session.query(Prompt)
                .filter(
                    Prompt.name == prompt_name,
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .join(PromptCategory)
                .filter(
                    PromptCategory.name == prompt_category,
                    Prompt.user_id == self.user_id,
                )
                .first()
            )
        if not prompt and prompt_category != "Default":
            # Prompt not found in specified category, try the default category
            prompt = (
                self.session.query(Prompt)
                .filter(
                    Prompt.name == prompt_name,
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name="Default"),
                )
                .join(PromptCategory)
                .filter(
                    PromptCategory.name == "Default", Prompt.user_id == self.user_id
                )
                .first()
            )
        if prompt:
            return prompt.content
        return None

    def get_prompts(self, prompt_category="Default"):
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompts = (
            self.session.query(Prompt)
            .filter(
                Prompt.user_id == user_data.id,
                Prompt.prompt_category.has(name=prompt_category),
            )
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category, Prompt.user_id == user_data.id
            )
            .all()
        )
        user_prompts = (
            self.session.query(Prompt)
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category, Prompt.user_id == self.user_id
            )
            .all()
        )
        prompts = []
        for prompt in global_prompts:
            prompts.append(prompt.name)
        for prompt in user_prompts:
            prompts.append(prompt.name)
        return prompts

    def get_prompt_args(self, prompt_text):
        prompt_args = []
        start_index = prompt_text.find("{")
        while start_index != -1:
            end_index = prompt_text.find("}", start_index)
            if end_index != -1:
                prompt_args.append(prompt_text[start_index + 1 : end_index])
                start_index = prompt_text.find("{", end_index)
            else:
                break
        return prompt_args

    def delete_prompt(self, prompt_name, prompt_category="Default"):
        prompt = (
            self.session.query(Prompt)
            .filter_by(name=prompt_name)
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category, Prompt.user_id == self.user_id
            )
            .first()
        )
        if prompt:
            self.session.delete(prompt)
            self.session.commit()

    def update_prompt(self, prompt_name, prompt, prompt_category="Default"):
        prompt_obj = (
            self.session.query(Prompt)
            .filter(
                Prompt.name == prompt_name,
                Prompt.user_id == self.user_id,
                Prompt.prompt_category.has(name=prompt_category),
            )
            .first()
        )
        if prompt_obj:
            if prompt_category:
                prompt_category = (
                    self.session.query(PromptCategory)
                    .filter(
                        PromptCategory.name == prompt_category,
                        PromptCategory.user_id == self.user_id,
                    )
                    .first()
                )
                if not prompt_category:
                    prompt_category = PromptCategory(
                        name=prompt_category,
                        description=f"{prompt_category} category",
                        user_id=self.user_id,
                    )
                    self.session.add(prompt_category)
                    self.session.commit()
                prompt_obj.prompt_category = prompt_category

            prompt_obj.content = prompt
            self.session.commit()

            # Update prompt arguments
            prompt_args = self.get_prompt_args(prompt)
            existing_args = (
                self.session.query(Argument).filter_by(prompt_id=prompt_obj.id).all()
            )
            existing_arg_names = {arg.name for arg in existing_args}

            # Delete removed arguments
            for arg in existing_args:
                if arg.name not in prompt_args:
                    self.session.delete(arg)

            # Add new arguments
            for arg in prompt_args:
                if arg not in existing_arg_names:
                    argument = Argument(
                        prompt_id=prompt_obj.id,
                        name=arg,
                    )
                    self.session.add(argument)

            self.session.commit()

    def rename_prompt(self, prompt_name, new_prompt_name, prompt_category="Default"):
        prompt = (
            self.session.query(Prompt)
            .filter(
                Prompt.name == prompt_name,
                Prompt.user_id == self.user_id,
                Prompt.prompt_category.has(name=prompt_category),
            )
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category, Prompt.user_id == self.user_id
            )
            .first()
        )
        if prompt:
            prompt.name = new_prompt_name
            self.session.commit()

    def get_prompt_categories(self):
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompt_categories = (
            self.session.query(PromptCategory)
            .filter(PromptCategory.user_id == user_data.id)
            .all()
        )
        user_prompt_categories = (
            self.session.query(PromptCategory)
            .filter(PromptCategory.user_id == self.user_id)
            .all()
        )
        prompt_categories = []
        for prompt_category in global_prompt_categories:
            prompt_categories.append(prompt_category.name)
        for prompt_category in user_prompt_categories:
            prompt_categories.append(prompt_category.name)
        return prompt_categories
