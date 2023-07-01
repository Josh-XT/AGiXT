from DBConnection import Base, Prompt, PromptCategory, db


class Prompts:
    def add_prompt(self, prompt_name, prompt):
        session = db.session
        prompt_category = (
            session.query(PromptCategory).filter_by(name="Default").first()
        )
        if not prompt_category:
            prompt_category = PromptCategory(
                name="Default", description="Default category"
            )
            session.add(prompt_category)
            session.commit()

        prompt = Prompt(
            name=prompt_name,
            description="",
            content=prompt,
            prompt_category=prompt_category,
        )
        session.add(prompt)
        session.commit()

    def get_prompt(self, prompt_name, model="default"):
        session = db.session
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            return prompt.content
        return None

    def get_prompts(self):
        session = db.session
        prompts = session.query(Prompt).all()
        return [prompt.name for prompt in prompts]

    def get_prompt_args(self, prompt_name):
        session = db.session
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            prompt_text = prompt.content
            prompt_vars = []
            start_index = prompt_text.find("{")
            while start_index != -1:
                end_index = prompt_text.find("}", start_index)
                if end_index != -1:
                    prompt_vars.append(prompt_text[start_index + 1 : end_index])
                    start_index = prompt_text.find("{", end_index)
                else:
                    break
            return prompt_vars
        return []

    def delete_prompt(self, prompt_name):
        session = db.session
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            session.delete(prompt)
            session.commit()

    def update_prompt(self, prompt_name, prompt):
        session = db.session
        prompt = session.query(Prompt).filter_by(name=prompt_name).first()
        if prompt:
            prompt.content = prompt
            session.commit()
