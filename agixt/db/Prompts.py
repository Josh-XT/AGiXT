from DBConnection import Prompt, PromptCategory, Argument, session


class Prompts:
    def add_prompt(self, prompt_name, prompt, prompt_category_name=None):
        if not prompt_category_name:
            prompt_category_name = "Default"

        prompt_category = (
            session.query(PromptCategory).filter_by(name=prompt_category_name).first()
        )
        if not prompt_category:
            prompt_category = PromptCategory(
                name=prompt_category_name,
                description=f"{prompt_category_name} category",
            )
            session.add(prompt_category)
            session.commit()

        prompt_obj = Prompt(
            name=prompt_name,
            description="",
            content=prompt,
            prompt_category=prompt_category,
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

    def get_prompt(self, prompt_name, prompt_category="Default"):
        prompt = (
            session.query(Prompt)
            .filter_by(name=prompt_name)
            .join(PromptCategory)
            .filter(PromptCategory.name == prompt_category)
            .first()
        )
        if not prompt and prompt_category != "Default":
            # Prompt not found in specified category, try the default category
            prompt = (
                session.query(Prompt)
                .filter_by(name=prompt_name)
                .join(PromptCategory)
                .filter(PromptCategory.name == "Default")
                .first()
            )
        if prompt:
            return prompt.content
        return None

    def get_prompts(self):
        prompts = session.query(Prompt).all()
        return [prompt.name for prompt in prompts]

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

    def delete_prompt(self, prompt_name):
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            # Delete associated arguments
            arguments = session.query(Argument).filter_by(prompt_id=prompt.id).all()
            for argument in arguments:
                session.delete(argument)

            session.delete(prompt)
            session.commit()

    def update_prompt(self, prompt_name, prompt, prompt_category_name=None):
        prompt_obj = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt_obj:
            if prompt_category_name:
                prompt_category = (
                    session.query(PromptCategory)
                    .filter_by(name=prompt_category_name)
                    .first()
                )
                if not prompt_category:
                    prompt_category = PromptCategory(
                        name=prompt_category_name,
                        description=f"{prompt_category_name} category",
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

    def rename_prompt(self, prompt_name, new_prompt_name):
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            prompt.name = new_prompt_name
            session.commit()
