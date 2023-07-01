from DBConnection import Prompt, PromptCategory, Argument, session


class Prompts:
    def add_prompt(self, prompt_name, prompt):
        prompt_category = (
            session.query(PromptCategory).filter_by(name="Default").first()
        )
        if not prompt_category:
            prompt_category = PromptCategory(
                name="Default", description="Default category"
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

    def get_prompt(self, prompt_name, model="default"):
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
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
            session.delete(prompt)
            session.commit()

    def update_prompt(self, prompt_name, prompt):
        prompt_obj = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt_obj:
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
            session.commit()

            # Add new arguments
            for arg in prompt_args:
                if arg not in existing_arg_names:
                    argument = Argument(
                        prompt_id=prompt_obj.id,
                        name=arg,
                    )
                    session.add(argument)
            session.commit()
