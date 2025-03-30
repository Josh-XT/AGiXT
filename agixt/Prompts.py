from DB import Prompt, PromptCategory, Argument, User, get_session
from Globals import DEFAULT_USER
from MagicalAuth import get_user_id
import os


class Prompts:
    def __init__(self, user=DEFAULT_USER):
        self.user = user
        self.user_id = get_user_id(user)

    def add_prompt(self, prompt_name, prompt, prompt_category="Default"):
        session = get_session()
        if not prompt_category or prompt_category == "":
            prompt_category = "Default"
        pc = (
            session.query(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category,
                PromptCategory.user_id == self.user_id,
            )
            .first()
        )
        if not pc:
            pc = PromptCategory(
                name=prompt_category,
                description=f"{prompt_category} category",
                user_id=self.user_id,
            )
            session.add(pc)
            session.commit()
        prompt_obj = Prompt(
            name=prompt_name,
            description="",
            content=prompt,
            prompt_category_id=pc.id,
            user_id=self.user_id,
        )
        session.add(prompt_obj)
        session.commit()

        # Populate prompt arguments
        prompt_args = self.get_prompt_args(prompt)
        for arg in prompt_args:
            argument = Argument(
                prompt_id=prompt_obj.id,
                name=arg,
            )
            session.add(argument)
        session.commit()
        session.close()

    def get_prompt(self, prompt_name: str, prompt_category: str = "Default"):
        session = get_session()
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        prompt = (
            session.query(Prompt)
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
                session.query(Prompt)
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
                session.query(Prompt)
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
        if not prompt:
            prompt_file = os.path.normpath(
                os.path.join(os.getcwd(), "prompts", "Default", f"{prompt_name}.txt")
            )
            base_path = os.path.join(os.getcwd(), "prompts")
            if not prompt_file.startswith(base_path):
                return None
            if os.path.exists(prompt_file):
                with open(prompt_file, "r") as f:
                    prompt_content = f.read()
                self.add_prompt(
                    prompt_name=prompt_name,
                    prompt=prompt_content,
                    prompt_category="Default",
                )
                prompt = (
                    session.query(Prompt)
                    .filter(
                        Prompt.name == prompt_name,
                        Prompt.user_id == self.user_id,
                        Prompt.prompt_category.has(name="Default"),
                    )
                    .join(PromptCategory)
                    .filter(
                        PromptCategory.name == "Default",
                        Prompt.user_id == self.user_id,
                    )
                    .first()
                )
        if prompt:
            prompt_content = prompt.content
            session.close()
            return prompt_content
        session.close()
        return None

    def get_global_prompts(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompts = (
            session.query(Prompt).filter(Prompt.user_id == user_data.id).all()
        )
        prompts = []
        for prompt in global_prompts:
            # If the user has this, don't add it to prompts, if they don't, add it
            if (
                not session.query(Prompt)
                .filter(
                    Prompt.name == prompt.name,
                    Prompt.user_id == self.user_id,
                )
                .first()
            ):
                try:
                    prompt_args = [
                        arg.name
                        for arg in prompt.arguments
                        if arg.prompt_id == prompt.id
                    ]
                except:
                    prompt_args = []
                prompts.append(
                    {
                        "name": prompt.name,
                        "category": prompt.prompt_category.name,
                        "content": prompt.content,
                        "description": prompt.description,
                        "arguments": prompt_args,
                    }
                )
        session.close()
        return prompts

    def get_user_prompts(self):
        session = get_session()
        user_prompts = (
            session.query(Prompt).filter(Prompt.user_id == self.user_id).all()
        )
        prompts = []
        for prompt in user_prompts:
            try:
                prompt_args = [
                    arg.name for arg in prompt.arguments if arg.prompt_id == prompt.id
                ]
            except:
                prompt_args = []
            prompts.append(
                {
                    "name": prompt.name,
                    "category": prompt.prompt_category.name,
                    "content": prompt.content,
                    "description": prompt.description,
                    "arguments": prompt_args,
                }
            )
        session.close()
        global_prompts = self.get_global_prompts()
        prompts += global_prompts
        return prompts

    def get_prompts(self, prompt_category="Default"):
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompts = (
            session.query(Prompt)
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
            session.query(Prompt)
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
        session.close()
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
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()
        prompt = (
            session.query(Prompt)
            .filter_by(name=prompt_name)
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category, Prompt.user_id == self.user_id
            )
            .first()
        )
        if prompt:
            session.delete(prompt)
            session.commit()
        session.close()

    def update_prompt(self, prompt_name, prompt, prompt_category="Default"):
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()
        prompt_obj = (
            session.query(Prompt)
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
                    session.query(PromptCategory)
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
                    session.add(prompt_category)
                    session.commit()
                prompt_obj.prompt_category = prompt_category
            prompt_obj.content = prompt
            session.commit()
            # Update prompt arguments
            prompt_args = self.get_prompt_args(prompt)
            existing_args = (
                session.query(Argument).filter_by(prompt_id=prompt_obj.id).all()
            )
            existing_arg_names = {arg.name for arg in existing_args}
            # Delete removed arguments
            for arg in existing_args:
                if arg.name not in prompt_args:
                    session.delete(arg)
            # Add new arguments
            for arg in prompt_args:
                if arg not in existing_arg_names:
                    argument = Argument(
                        prompt_id=prompt_obj.id,
                        name=arg,
                    )
                    session.add(argument)
            session.commit()
        session.close()

    def rename_prompt(self, prompt_name, new_prompt_name, prompt_category="Default"):
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()
        prompt = (
            session.query(Prompt)
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
            session.commit()
        session.close()

    def get_prompt_categories(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompt_categories = (
            session.query(PromptCategory)
            .filter(PromptCategory.user_id == user_data.id)
            .all()
        )
        user_prompt_categories = (
            session.query(PromptCategory)
            .filter(PromptCategory.user_id == self.user_id)
            .all()
        )
        prompt_categories = []
        for prompt_category in global_prompt_categories:
            prompt_categories.append(prompt_category.name)
        for prompt_category in user_prompt_categories:
            prompt_categories.append(prompt_category.name)
        session.close()
        return prompt_categories
