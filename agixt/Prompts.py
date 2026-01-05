from DB import (
    Prompt,
    PromptCategory,
    Argument,
    User,
    get_session,
    ServerPrompt,
    ServerPromptCategory,
    ServerPromptArgument,
    CompanyPrompt,
    CompanyPromptCategory,
    CompanyPromptArgument,
    UserPromptOverride,
)
from Globals import DEFAULT_USER
from MagicalAuth import get_user_id, get_user_company_id
import os
import logging


class Prompts:
    def __init__(self, user=DEFAULT_USER):
        self.user = user
        self.user_id = get_user_id(user)
        self.company_id = get_user_company_id(user)

    def _get_prompt_args_from_content(self, prompt_text):
        """Extract {variable} arguments from prompt content."""
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

    # Alias for backwards compatibility
    def get_prompt_args(self, prompt_text):
        return self._get_prompt_args_from_content(prompt_text)

    # =========================================================================
    # User-level prompt methods (existing behavior with tiered fallback)
    # =========================================================================

    def add_prompt(self, prompt_name, prompt, prompt_category="Default"):
        """Add a user-level prompt."""
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
        prompt_args = self._get_prompt_args_from_content(prompt)
        for arg in prompt_args:
            argument = Argument(
                prompt_id=prompt_obj.id,
                name=arg,
            )
            session.add(argument)
        session.commit()
        prompt_id = str(prompt_obj.id)
        session.close()
        return prompt_id

    def get_prompt(self, prompt_name: str, prompt_category: str = "Default"):
        """
        Get a prompt by name with tiered resolution:
        1. User-level prompt (highest priority)
        2. Company-level prompt
        3. Server-level prompt (global)
        4. Legacy file-based prompt (lowest priority, imports to user level)

        For internal prompts, server level is always used.
        """
        session = get_session()

        # 1. Try user-level prompt first
        prompt = (
            session.query(Prompt)
            .join(PromptCategory)
            .filter(
                Prompt.name == prompt_name,
                Prompt.user_id == self.user_id,
                PromptCategory.name == prompt_category,
            )
            .first()
        )
        if prompt:
            content = prompt.content
            session.close()
            return content

        # 2. Try company-level prompt
        if self.company_id:
            company_prompt = (
                session.query(CompanyPrompt)
                .join(CompanyPromptCategory)
                .filter(
                    CompanyPrompt.name == prompt_name,
                    CompanyPrompt.company_id == self.company_id,
                    CompanyPromptCategory.name == prompt_category,
                )
                .first()
            )
            if company_prompt:
                content = company_prompt.content
                session.close()
                return content

        # 3. Try server-level prompt (including internal prompts)
        server_prompt = (
            session.query(ServerPrompt)
            .join(ServerPromptCategory)
            .filter(
                ServerPrompt.name == prompt_name,
                ServerPromptCategory.name == prompt_category,
            )
            .first()
        )
        if server_prompt:
            content = server_prompt.content
            session.close()
            return content

        # 4. Legacy: Try default user's prompts (for backwards compatibility)
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            default_prompt = (
                session.query(Prompt)
                .join(PromptCategory)
                .filter(
                    Prompt.name == prompt_name,
                    Prompt.user_id == user_data.id,
                    PromptCategory.name == prompt_category,
                )
                .first()
            )
            if default_prompt:
                content = default_prompt.content
                session.close()
                return content

        # 5. Legacy: Try file-based prompts and import to user level
        prompt_file = os.path.normpath(
            os.path.join(os.getcwd(), "prompts", prompt_category, f"{prompt_name}.txt")
        )
        base_path = os.path.join(os.getcwd(), "prompts")
        if prompt_file.startswith(base_path) and os.path.exists(prompt_file):
            with open(prompt_file, "r") as f:
                prompt_content = f.read()
            session.close()
            # Import to user level
            self.add_prompt(
                prompt_name=prompt_name,
                prompt=prompt_content,
                prompt_category=prompt_category,
            )
            return prompt_content

        session.close()
        return None

    def get_user_prompts(self):
        """
        Get all prompts available to the user from all tiers.
        Returns prompts with source indicators (server/company/user).
        User prompts override company, which override server prompts of the same name.
        """
        session = get_session()
        prompts_dict = {}  # name -> prompt data (for deduplication)

        # 1. Server-level prompts (non-internal only)
        server_prompts = (
            session.query(ServerPrompt)
            .join(ServerPromptCategory)
            .filter(ServerPrompt.is_internal == False)
            .all()
        )
        for prompt in server_prompts:
            try:
                prompt_args = [arg.name for arg in prompt.arguments]
            except:
                prompt_args = []
            prompts_dict[prompt.name] = {
                "id": str(prompt.id),
                "name": prompt.name,
                "category": prompt.category.name,
                "content": prompt.content,
                "description": prompt.description,
                "arguments": prompt_args,
                "source": "server",
                "is_override": False,
            }

        # 2. Company-level prompts (override server)
        if self.company_id:
            company_prompts = (
                session.query(CompanyPrompt)
                .filter(CompanyPrompt.company_id == self.company_id)
                .all()
            )
            for prompt in company_prompts:
                try:
                    prompt_args = [arg.name for arg in prompt.arguments]
                except:
                    prompt_args = []
                is_override = prompt.server_prompt_id is not None
                prompts_dict[prompt.name] = {
                    "id": str(prompt.id),
                    "name": prompt.name,
                    "category": prompt.category.name,
                    "content": prompt.content,
                    "description": prompt.description,
                    "arguments": prompt_args,
                    "source": "company",
                    "is_override": is_override,
                    "parent_id": (
                        str(prompt.server_prompt_id)
                        if prompt.server_prompt_id
                        else None
                    ),
                }

        # 3. User-level prompts (override company and server)
        user_prompts = (
            session.query(Prompt).filter(Prompt.user_id == self.user_id).all()
        )
        for prompt in user_prompts:
            try:
                prompt_args = [arg.name for arg in prompt.arguments]
            except:
                prompt_args = []

            # Check if this is an override
            override = (
                session.query(UserPromptOverride)
                .filter(
                    UserPromptOverride.user_id == self.user_id,
                    UserPromptOverride.prompt_id == prompt.id,
                )
                .first()
            )
            is_override = override is not None
            parent_id = None
            if override:
                if override.server_prompt_id:
                    parent_id = str(override.server_prompt_id)
                elif override.company_prompt_id:
                    parent_id = str(override.company_prompt_id)

            prompts_dict[prompt.name] = {
                "id": str(prompt.id),
                "name": prompt.name,
                "category": prompt.prompt_category.name,
                "content": prompt.content,
                "description": prompt.description,
                "arguments": prompt_args,
                "source": "user",
                "is_override": is_override,
                "parent_id": parent_id,
            }

        # 4. Legacy: Include global prompts from DEFAULT_USER that user doesn't have
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data and user_data.id != self.user_id:
            global_prompts = (
                session.query(Prompt).filter(Prompt.user_id == user_data.id).all()
            )
            for prompt in global_prompts:
                if prompt.name not in prompts_dict:
                    try:
                        prompt_args = [arg.name for arg in prompt.arguments]
                    except:
                        prompt_args = []
                    prompts_dict[prompt.name] = {
                        "id": str(prompt.id),
                        "name": prompt.name,
                        "category": prompt.prompt_category.name,
                        "content": prompt.content,
                        "description": prompt.description,
                        "arguments": prompt_args,
                        "source": "global",  # Legacy global
                        "is_override": False,
                    }

        session.close()
        return list(prompts_dict.values())

    def get_global_prompts(self):
        """
        Get server-level and legacy global prompts that the user doesn't have overridden.
        """
        session = get_session()
        prompts = []

        # Get user's prompt names for exclusion
        user_prompt_names = {
            p.name
            for p in session.query(Prompt).filter(Prompt.user_id == self.user_id).all()
        }

        # Server-level prompts (non-internal)
        server_prompts = (
            session.query(ServerPrompt).filter(ServerPrompt.is_internal == False).all()
        )
        for prompt in server_prompts:
            if prompt.name not in user_prompt_names:
                try:
                    prompt_args = [arg.name for arg in prompt.arguments]
                except:
                    prompt_args = []
                prompts.append(
                    {
                        "id": str(prompt.id),
                        "name": prompt.name,
                        "category": prompt.category.name,
                        "content": prompt.content,
                        "description": prompt.description,
                        "arguments": prompt_args,
                        "source": "server",
                    }
                )

        # Company-level prompts
        if self.company_id:
            company_prompts = (
                session.query(CompanyPrompt)
                .filter(CompanyPrompt.company_id == self.company_id)
                .all()
            )
            for prompt in company_prompts:
                if prompt.name not in user_prompt_names:
                    try:
                        prompt_args = [arg.name for arg in prompt.arguments]
                    except:
                        prompt_args = []
                    prompts.append(
                        {
                            "id": str(prompt.id),
                            "name": prompt.name,
                            "category": prompt.category.name,
                            "content": prompt.content,
                            "description": prompt.description,
                            "arguments": prompt_args,
                            "source": "company",
                        }
                    )

        # Legacy global prompts
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            global_prompts = (
                session.query(Prompt).filter(Prompt.user_id == user_data.id).all()
            )
            for prompt in global_prompts:
                if prompt.name not in user_prompt_names:
                    try:
                        prompt_args = [arg.name for arg in prompt.arguments]
                    except:
                        prompt_args = []
                    prompts.append(
                        {
                            "id": str(prompt.id),
                            "name": prompt.name,
                            "category": prompt.prompt_category.name,
                            "content": prompt.content,
                            "description": prompt.description,
                            "arguments": prompt_args,
                            "source": "global",
                        }
                    )

        session.close()
        return prompts

    def get_prompts_markdown(self):
        """Get all prompts as markdown documentation."""
        prompt_data = self.get_user_prompts()
        prompt_markdown = ""
        for prompt in prompt_data:
            prompt_markdown += f"## Prompt Name: `{prompt['name']}`\n"
            if prompt.get("description"):
                prompt_markdown += f"**Description:** {prompt['description']}\n"
            prompt_markdown += (
                f"**Arguments:** {', '.join(prompt.get('arguments', []))}\n"
            )
            prompt_markdown += f"**Source:** {prompt.get('source', 'user')}\n\n"
        return prompt_markdown

    def get_prompts(self, prompt_category="Default", include_ids: bool = False):
        """Get prompts in a category with tiered resolution."""
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()
        prompts_dict = {}

        # 1. Server-level prompts in category (non-internal)
        server_prompts = (
            session.query(ServerPrompt)
            .join(ServerPromptCategory)
            .filter(
                ServerPromptCategory.name == prompt_category,
                ServerPrompt.is_internal == False,
            )
            .all()
        )
        for prompt in server_prompts:
            if include_ids:
                prompts_dict[prompt.name] = {
                    "id": str(prompt.id),
                    "name": prompt.name,
                    "source": "server",
                }
            else:
                prompts_dict[prompt.name] = prompt.name

        # 2. Company-level prompts in category
        if self.company_id:
            company_prompts = (
                session.query(CompanyPrompt)
                .join(CompanyPromptCategory)
                .filter(
                    CompanyPromptCategory.name == prompt_category,
                    CompanyPrompt.company_id == self.company_id,
                )
                .all()
            )
            for prompt in company_prompts:
                if include_ids:
                    prompts_dict[prompt.name] = {
                        "id": str(prompt.id),
                        "name": prompt.name,
                        "source": "company",
                    }
                else:
                    prompts_dict[prompt.name] = prompt.name

        # 3. User-level prompts in category
        user_prompts = (
            session.query(Prompt)
            .join(PromptCategory)
            .filter(
                PromptCategory.name == prompt_category,
                Prompt.user_id == self.user_id,
            )
            .all()
        )
        for prompt in user_prompts:
            if include_ids:
                prompts_dict[prompt.name] = {
                    "id": str(prompt.id),
                    "name": prompt.name,
                    "source": "user",
                }
            else:
                prompts_dict[prompt.name] = prompt.name

        # 4. Legacy global prompts
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            global_prompts = (
                session.query(Prompt)
                .join(PromptCategory)
                .filter(
                    PromptCategory.name == prompt_category,
                    Prompt.user_id == user_data.id,
                )
                .all()
            )
            for prompt in global_prompts:
                if prompt.name not in prompts_dict:
                    if include_ids:
                        prompts_dict[prompt.name] = {
                            "id": str(prompt.id),
                            "name": prompt.name,
                            "source": "global",
                        }
                    else:
                        prompts_dict[prompt.name] = prompt.name

        session.close()
        return list(prompts_dict.values())

    def get_prompts_by_category_id(self, category_id: str):
        """Get prompts by category ID with full details including ID."""
        session = get_session()
        prompts = []

        # Check if this is a server category
        server_category = (
            session.query(ServerPromptCategory)
            .filter(ServerPromptCategory.id == category_id)
            .first()
        )
        if server_category:
            for prompt in server_category.prompts:
                if not prompt.is_internal:
                    prompts.append(
                        {"id": str(prompt.id), "name": prompt.name, "source": "server"}
                    )
            session.close()
            return prompts

        # Check if this is a company category
        company_category = (
            session.query(CompanyPromptCategory)
            .filter(
                CompanyPromptCategory.id == category_id,
                CompanyPromptCategory.company_id == self.company_id,
            )
            .first()
        )
        if company_category:
            for prompt in company_category.prompts:
                prompts.append(
                    {"id": str(prompt.id), "name": prompt.name, "source": "company"}
                )
            session.close()
            return prompts

        # Must be a user category
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_prompts = (
            session.query(Prompt)
            .filter(
                Prompt.user_id == user_data.id,
                Prompt.prompt_category_id == category_id,
            )
            .all()
        )
        user_prompts = (
            session.query(Prompt)
            .filter(
                Prompt.user_id == self.user_id,
                Prompt.prompt_category_id == category_id,
            )
            .all()
        )

        seen_names = {}
        for prompt in global_prompts:
            seen_names[prompt.name] = {
                "id": str(prompt.id),
                "name": prompt.name,
                "source": "global",
            }
        for prompt in user_prompts:
            seen_names[prompt.name] = {
                "id": str(prompt.id),
                "name": prompt.name,
                "source": "user",
            }

        session.close()
        return list(seen_names.values())

    def delete_prompt(self, prompt_name, prompt_category="Default"):
        """Delete a user-level prompt."""
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
            # Also delete any override tracking
            session.query(UserPromptOverride).filter(
                UserPromptOverride.prompt_id == prompt.id
            ).delete()
            session.delete(prompt)
            session.commit()
        session.close()

    def update_prompt(self, prompt_name, prompt, prompt_category="Default"):
        """Update a user-level prompt or clone from parent tier if editing inherited."""
        if not prompt_category:
            prompt_category = "Default"
        session = get_session()

        # Check if user has this prompt
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
            # User owns this prompt, update it directly
            prompt_obj.content = prompt
            session.commit()
            # Update arguments
            prompt_args = self._get_prompt_args_from_content(prompt)
            existing_args = (
                session.query(Argument).filter_by(prompt_id=prompt_obj.id).all()
            )
            existing_arg_names = {arg.name for arg in existing_args}
            for arg in existing_args:
                if arg.name not in prompt_args:
                    session.delete(arg)
            for arg in prompt_args:
                if arg not in existing_arg_names:
                    session.add(Argument(prompt_id=prompt_obj.id, name=arg))
            session.commit()
            session.close()
            return str(prompt_obj.id)

        # User doesn't have this prompt - need to clone from parent tier
        session.close()
        return self._clone_and_edit_prompt(prompt_name, prompt, prompt_category)

    def _clone_and_edit_prompt(self, prompt_name, new_content, prompt_category):
        """Clone a prompt from parent tier (server/company) to user level for editing."""
        session = get_session()

        server_prompt_id = None
        company_prompt_id = None
        source_prompt = None

        # Check company-level first
        if self.company_id:
            company_prompt = (
                session.query(CompanyPrompt)
                .join(CompanyPromptCategory)
                .filter(
                    CompanyPrompt.name == prompt_name,
                    CompanyPrompt.company_id == self.company_id,
                    CompanyPromptCategory.name == prompt_category,
                )
                .first()
            )
            if company_prompt:
                source_prompt = company_prompt
                company_prompt_id = company_prompt.id

        # Check server-level
        if not source_prompt:
            server_prompt = (
                session.query(ServerPrompt)
                .join(ServerPromptCategory)
                .filter(
                    ServerPrompt.name == prompt_name,
                    ServerPromptCategory.name == prompt_category,
                )
                .first()
            )
            if server_prompt:
                source_prompt = server_prompt
                server_prompt_id = server_prompt.id

        if not source_prompt:
            session.close()
            # No parent prompt found, create new
            return self.add_prompt(prompt_name, new_content, prompt_category)

        # Create user's copy
        session.close()
        new_prompt_id = self.add_prompt(prompt_name, new_content, prompt_category)

        # Track the override
        session = get_session()
        override = UserPromptOverride(
            user_id=self.user_id,
            prompt_id=new_prompt_id,
            server_prompt_id=server_prompt_id,
            company_prompt_id=company_prompt_id,
        )
        session.add(override)
        session.commit()
        session.close()

        return new_prompt_id

    def revert_prompt_to_default(self, prompt_id: str):
        """
        Revert a user's customized prompt back to the parent (server/company) version.
        Deletes the user's override and removes the tracking record.
        """
        session = get_session()

        override = (
            session.query(UserPromptOverride)
            .filter(
                UserPromptOverride.user_id == self.user_id,
                UserPromptOverride.prompt_id == prompt_id,
            )
            .first()
        )

        if not override:
            session.close()
            return {"success": False, "message": "This prompt is not an override"}

        # Delete the user's prompt
        prompt = session.query(Prompt).filter(Prompt.id == prompt_id).first()
        if prompt:
            session.delete(prompt)

        # Delete the override tracking
        session.delete(override)
        session.commit()
        session.close()

        return {"success": True, "message": "Reverted to default"}

    def rename_prompt(self, prompt_name, new_prompt_name, prompt_category="Default"):
        """Rename a user-level prompt."""
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

    def get_prompt_categories(self, include_ids: bool = False):
        """Get all prompt categories from all tiers."""
        session = get_session()
        categories_dict = {}

        # 1. Server categories (non-internal)
        server_categories = (
            session.query(ServerPromptCategory)
            .filter(ServerPromptCategory.is_internal == False)
            .all()
        )
        for cat in server_categories:
            if include_ids:
                categories_dict[cat.name] = {
                    "id": str(cat.id),
                    "name": cat.name,
                    "description": cat.description,
                    "source": "server",
                }
            else:
                categories_dict[cat.name] = cat.name

        # 2. Company categories
        if self.company_id:
            company_categories = (
                session.query(CompanyPromptCategory)
                .filter(CompanyPromptCategory.company_id == self.company_id)
                .all()
            )
            for cat in company_categories:
                if include_ids:
                    categories_dict[cat.name] = {
                        "id": str(cat.id),
                        "name": cat.name,
                        "description": cat.description,
                        "source": "company",
                    }
                else:
                    categories_dict[cat.name] = cat.name

        # 3. User categories
        user_categories = (
            session.query(PromptCategory)
            .filter(PromptCategory.user_id == self.user_id)
            .all()
        )
        for cat in user_categories:
            if include_ids:
                categories_dict[cat.name] = {
                    "id": str(cat.id),
                    "name": cat.name,
                    "description": cat.description,
                    "source": "user",
                }
            else:
                categories_dict[cat.name] = cat.name

        # 4. Legacy global categories
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            global_categories = (
                session.query(PromptCategory)
                .filter(PromptCategory.user_id == user_data.id)
                .all()
            )
            for cat in global_categories:
                if cat.name not in categories_dict:
                    if include_ids:
                        categories_dict[cat.name] = {
                            "id": str(cat.id),
                            "name": cat.name,
                            "description": cat.description,
                            "source": "global",
                        }
                    else:
                        categories_dict[cat.name] = cat.name

        session.close()
        return list(categories_dict.values())

    def get_prompt_by_id(self, prompt_id: str):
        """Get a prompt's content by ID across all tiers."""
        session = get_session()

        # Try user prompt
        prompt = (
            session.query(Prompt)
            .filter(
                Prompt.id == prompt_id,
                Prompt.user_id == self.user_id,
            )
            .first()
        )
        if prompt:
            session.close()
            return prompt.content

        # Try company prompt
        if self.company_id:
            company_prompt = (
                session.query(CompanyPrompt)
                .filter(
                    CompanyPrompt.id == prompt_id,
                    CompanyPrompt.company_id == self.company_id,
                )
                .first()
            )
            if company_prompt:
                session.close()
                return company_prompt.content

        # Try server prompt
        server_prompt = (
            session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
        )
        if server_prompt:
            session.close()
            return server_prompt.content

        # Try legacy global prompt
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            global_prompt = (
                session.query(Prompt)
                .filter(
                    Prompt.id == prompt_id,
                    Prompt.user_id == user_data.id,
                )
                .first()
            )
            if global_prompt:
                session.close()
                return global_prompt.content

        session.close()
        return None

    def update_prompt_by_id(
        self, prompt_id: str, prompt_name: str = None, prompt: str = None
    ):
        """Update a prompt by ID. If it's a parent prompt, clone it first."""
        session = get_session()

        # Check if user owns this prompt
        prompt_obj = (
            session.query(Prompt)
            .filter(
                Prompt.id == prompt_id,
                Prompt.user_id == self.user_id,
            )
            .first()
        )

        if prompt_obj:
            # User owns it, update directly
            if prompt_name is not None:
                prompt_obj.name = prompt_name
            if prompt is not None:
                prompt_obj.content = prompt
                # Update arguments
                session.query(Argument).filter(Argument.prompt_id == prompt_id).delete()
                for arg in self._get_prompt_args_from_content(prompt):
                    session.add(Argument(prompt_id=prompt_id, name=arg))
            session.commit()
            session.close()
            return str(prompt_obj.id)

        # Get the source prompt for cloning
        source_content = None
        source_name = None
        source_category = "Default"
        server_prompt_id = None
        company_prompt_id = None

        # Check company level
        if self.company_id:
            company_prompt = (
                session.query(CompanyPrompt)
                .filter(
                    CompanyPrompt.id == prompt_id,
                    CompanyPrompt.company_id == self.company_id,
                )
                .first()
            )
            if company_prompt:
                source_content = prompt if prompt else company_prompt.content
                source_name = prompt_name if prompt_name else company_prompt.name
                source_category = company_prompt.category.name
                company_prompt_id = company_prompt.id

        # Check server level
        if not source_content:
            server_prompt = (
                session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
            )
            if server_prompt:
                source_content = prompt if prompt else server_prompt.content
                source_name = prompt_name if prompt_name else server_prompt.name
                source_category = server_prompt.category.name
                server_prompt_id = server_prompt.id

        session.close()

        if not source_content:
            raise Exception("Prompt not found")

        # Create user copy
        new_prompt_id = self.add_prompt(source_name, source_content, source_category)

        # Track override
        session = get_session()
        override = UserPromptOverride(
            user_id=self.user_id,
            prompt_id=new_prompt_id,
            server_prompt_id=server_prompt_id,
            company_prompt_id=company_prompt_id,
        )
        session.add(override)
        session.commit()
        session.close()

        return new_prompt_id

    def delete_prompt_by_id(self, prompt_id: str):
        """Delete a user's prompt by ID."""
        session = get_session()
        prompt = (
            session.query(Prompt)
            .filter(
                Prompt.id == prompt_id,
                Prompt.user_id == self.user_id,
            )
            .first()
        )
        if not prompt:
            session.close()
            raise Exception(
                "Prompt not found or you don't have permission to delete it"
            )

        # Delete override tracking if exists
        session.query(UserPromptOverride).filter(
            UserPromptOverride.prompt_id == prompt_id
        ).delete()

        session.delete(prompt)
        session.commit()
        session.close()

    def get_prompt_details_by_id(self, prompt_id: str):
        """Get full prompt details by ID across all tiers."""
        session = get_session()

        # Try user prompt
        prompt = (
            session.query(Prompt)
            .filter(
                Prompt.id == prompt_id,
                Prompt.user_id == self.user_id,
            )
            .first()
        )
        if prompt:
            try:
                prompt_args = [arg.name for arg in prompt.arguments]
            except:
                prompt_args = []

            # Check if this is an override
            override = (
                session.query(UserPromptOverride)
                .filter(UserPromptOverride.prompt_id == prompt_id)
                .first()
            )

            result = {
                "prompt_name": prompt.name,
                "prompt_category": prompt.prompt_category.name,
                "prompt": prompt.content,
                "description": prompt.description,
                "arguments": prompt_args,
                "id": str(prompt.id),
                "source": "user",
                "is_override": override is not None,
                "can_revert": override is not None,
            }
            session.close()
            return result

        # Try company prompt
        if self.company_id:
            company_prompt = (
                session.query(CompanyPrompt)
                .filter(
                    CompanyPrompt.id == prompt_id,
                    CompanyPrompt.company_id == self.company_id,
                )
                .first()
            )
            if company_prompt:
                try:
                    prompt_args = [arg.name for arg in company_prompt.arguments]
                except:
                    prompt_args = []
                result = {
                    "prompt_name": company_prompt.name,
                    "prompt_category": company_prompt.category.name,
                    "prompt": company_prompt.content,
                    "description": company_prompt.description,
                    "arguments": prompt_args,
                    "id": str(company_prompt.id),
                    "source": "company",
                    "is_override": company_prompt.server_prompt_id is not None,
                    "can_revert": False,  # Would need company admin to revert
                }
                session.close()
                return result

        # Try server prompt
        server_prompt = (
            session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
        )
        if server_prompt:
            try:
                prompt_args = [arg.name for arg in server_prompt.arguments]
            except:
                prompt_args = []
            result = {
                "prompt_name": server_prompt.name,
                "prompt_category": server_prompt.category.name,
                "prompt": server_prompt.content,
                "description": server_prompt.description,
                "arguments": prompt_args,
                "id": str(server_prompt.id),
                "source": "server",
                "is_override": False,
                "can_revert": False,
            }
            session.close()
            return result

        # Try legacy global
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            global_prompt = (
                session.query(Prompt)
                .filter(
                    Prompt.id == prompt_id,
                    Prompt.user_id == user_data.id,
                )
                .first()
            )
            if global_prompt:
                try:
                    prompt_args = [arg.name for arg in global_prompt.arguments]
                except:
                    prompt_args = []
                result = {
                    "prompt_name": global_prompt.name,
                    "prompt_category": global_prompt.prompt_category.name,
                    "prompt": global_prompt.content,
                    "description": global_prompt.description,
                    "arguments": prompt_args,
                    "id": str(global_prompt.id),
                    "source": "global",
                    "is_override": False,
                    "can_revert": False,
                }
                session.close()
                return result

        session.close()
        return None

    # =========================================================================
    # Server-level prompt management (super admin only)
    # =========================================================================

    def get_server_prompts(self, include_internal: bool = False):
        """Get all server-level prompts. Super admin function."""
        session = get_session()
        query = session.query(ServerPrompt)
        if not include_internal:
            query = query.filter(ServerPrompt.is_internal == False)
        prompts = query.all()

        result = []
        for prompt in prompts:
            try:
                prompt_args = [arg.name for arg in prompt.arguments]
            except:
                prompt_args = []
            result.append(
                {
                    "id": str(prompt.id),
                    "name": prompt.name,
                    "category": prompt.category.name,
                    "content": prompt.content,
                    "description": prompt.description,
                    "arguments": prompt_args,
                    "is_internal": prompt.is_internal,
                }
            )

        session.close()
        return result

    def get_server_prompt_by_id(self, prompt_id: str):
        """Get a specific server-level prompt by ID. Super admin function."""
        session = get_session()
        prompt = (
            session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
        )

        if not prompt:
            session.close()
            return None

        try:
            prompt_args = [arg.name for arg in prompt.arguments]
        except:
            prompt_args = []

        result = {
            "id": str(prompt.id),
            "name": prompt.name,
            "category": prompt.category.name if prompt.category else "Default",
            "content": prompt.content,
            "description": prompt.description,
            "arguments": prompt_args,
            "is_internal": prompt.is_internal,
            "created_at": str(prompt.created_at) if prompt.created_at else None,
            "updated_at": str(prompt.updated_at) if prompt.updated_at else None,
        }

        session.close()
        return result

    def add_server_prompt(
        self,
        name: str,
        content: str,
        category: str = "Default",
        description: str = "",
        is_internal: bool = False,
    ):
        """Add a server-level prompt. Super admin function."""
        session = get_session()

        # Get or create category
        cat = (
            session.query(ServerPromptCategory)
            .filter(ServerPromptCategory.name == category)
            .first()
        )
        if not cat:
            cat = ServerPromptCategory(
                name=category,
                description=f"{category} category",
                is_internal=is_internal,
            )
            session.add(cat)
            session.commit()

        prompt = ServerPrompt(
            name=name,
            content=content,
            description=description,
            category_id=cat.id,
            is_internal=is_internal,
        )
        session.add(prompt)
        session.commit()

        # Add arguments
        for arg in self._get_prompt_args_from_content(content):
            session.add(ServerPromptArgument(prompt_id=prompt.id, name=arg))
        session.commit()

        prompt_id = str(prompt.id)
        session.close()
        return prompt_id

    def update_server_prompt(
        self,
        prompt_id: str,
        name: str = None,
        content: str = None,
        description: str = None,
        is_internal: bool = None,
    ):
        """Update a server-level prompt. Super admin function."""
        session = get_session()
        prompt = (
            session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
        )
        if not prompt:
            session.close()
            raise Exception("Server prompt not found")

        if name is not None:
            prompt.name = name
        if content is not None:
            prompt.content = content
            # Update arguments
            session.query(ServerPromptArgument).filter(
                ServerPromptArgument.prompt_id == prompt_id
            ).delete()
            for arg in self._get_prompt_args_from_content(content):
                session.add(ServerPromptArgument(prompt_id=prompt_id, name=arg))
        if description is not None:
            prompt.description = description
        if is_internal is not None:
            prompt.is_internal = is_internal

        session.commit()
        session.close()

    def delete_server_prompt(self, prompt_id: str):
        """Delete a server-level prompt. Super admin function."""
        session = get_session()
        prompt = (
            session.query(ServerPrompt).filter(ServerPrompt.id == prompt_id).first()
        )
        if not prompt:
            session.close()
            raise Exception("Server prompt not found")
        session.delete(prompt)
        session.commit()
        session.close()

    def get_server_prompt_categories(self, include_internal: bool = False):
        """Get all server-level prompt categories. Super admin function."""
        session = get_session()
        query = session.query(ServerPromptCategory)
        if not include_internal:
            query = query.filter(ServerPromptCategory.is_internal == False)
        categories = query.all()

        result = [
            {
                "id": str(cat.id),
                "name": cat.name,
                "description": cat.description,
                "is_internal": cat.is_internal,
            }
            for cat in categories
        ]
        session.close()
        return result

    def add_server_prompt_category(
        self, name: str, description: str = "", is_internal: bool = False
    ):
        """Add a server-level prompt category. Super admin function."""
        session = get_session()
        cat = ServerPromptCategory(
            name=name, description=description, is_internal=is_internal
        )
        session.add(cat)
        session.commit()
        cat_id = str(cat.id)
        session.close()
        return cat_id

    def delete_server_prompt_category(self, category_id: str):
        """Delete a server-level prompt category. Super admin function."""
        session = get_session()
        cat = (
            session.query(ServerPromptCategory)
            .filter(ServerPromptCategory.id == category_id)
            .first()
        )
        if not cat:
            session.close()
            raise Exception("Category not found")
        session.delete(cat)
        session.commit()
        session.close()

    # =========================================================================
    # Company-level prompt management (company admin only)
    # =========================================================================

    def get_company_prompts(self, company_id: str = None):
        """Get all company-level prompts. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            return []

        session = get_session()
        prompts = (
            session.query(CompanyPrompt)
            .filter(CompanyPrompt.company_id == target_company)
            .all()
        )

        result = []
        for prompt in prompts:
            try:
                prompt_args = [arg.name for arg in prompt.arguments]
            except:
                prompt_args = []
            result.append(
                {
                    "id": str(prompt.id),
                    "name": prompt.name,
                    "category": prompt.category.name,
                    "content": prompt.content,
                    "description": prompt.description,
                    "arguments": prompt_args,
                    "server_prompt_id": (
                        str(prompt.server_prompt_id)
                        if prompt.server_prompt_id
                        else None
                    ),
                }
            )

        session.close()
        return result

    def get_company_prompt_by_id(self, prompt_id: str, company_id: str = None):
        """Get a specific company-level prompt by ID. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            return None

        session = get_session()
        prompt = (
            session.query(CompanyPrompt)
            .filter(
                CompanyPrompt.id == prompt_id,
                CompanyPrompt.company_id == target_company,
            )
            .first()
        )

        if not prompt:
            session.close()
            return None

        try:
            prompt_args = [arg.name for arg in prompt.arguments]
        except:
            prompt_args = []

        result = {
            "id": str(prompt.id),
            "name": prompt.name,
            "category": prompt.category.name if prompt.category else "Default",
            "content": prompt.content,
            "description": prompt.description,
            "arguments": prompt_args,
            "server_prompt_id": (
                str(prompt.server_prompt_id) if prompt.server_prompt_id else None
            ),
            "created_at": str(prompt.created_at) if prompt.created_at else None,
            "updated_at": str(prompt.updated_at) if prompt.updated_at else None,
        }

        session.close()
        return result

    def add_company_prompt(
        self,
        name: str,
        content: str,
        category: str = "Default",
        description: str = "",
        company_id: str = None,
    ):
        """Add a company-level prompt. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            raise Exception("No company context")

        session = get_session()

        # Get or create category
        cat = (
            session.query(CompanyPromptCategory)
            .filter(
                CompanyPromptCategory.company_id == target_company,
                CompanyPromptCategory.name == category,
            )
            .first()
        )
        if not cat:
            cat = CompanyPromptCategory(
                company_id=target_company,
                name=category,
                description=f"{category} category",
            )
            session.add(cat)
            session.commit()

        prompt = CompanyPrompt(
            company_id=target_company,
            name=name,
            content=content,
            description=description,
            category_id=cat.id,
        )
        session.add(prompt)
        session.commit()

        # Add arguments
        for arg in self._get_prompt_args_from_content(content):
            session.add(CompanyPromptArgument(prompt_id=prompt.id, name=arg))
        session.commit()

        prompt_id = str(prompt.id)
        session.close()
        return prompt_id

    def update_company_prompt(
        self,
        prompt_id: str,
        name: str = None,
        content: str = None,
        description: str = None,
    ):
        """Update a company-level prompt. Company admin function."""
        session = get_session()
        prompt = (
            session.query(CompanyPrompt)
            .filter(
                CompanyPrompt.id == prompt_id,
                CompanyPrompt.company_id == self.company_id,
            )
            .first()
        )
        if not prompt:
            session.close()
            raise Exception("Company prompt not found")

        if name is not None:
            prompt.name = name
        if content is not None:
            prompt.content = content
            # Update arguments
            session.query(CompanyPromptArgument).filter(
                CompanyPromptArgument.prompt_id == prompt_id
            ).delete()
            for arg in self._get_prompt_args_from_content(content):
                session.add(CompanyPromptArgument(prompt_id=prompt_id, name=arg))
        if description is not None:
            prompt.description = description

        session.commit()
        session.close()

    def delete_company_prompt(self, prompt_id: str):
        """Delete a company-level prompt. Company admin function."""
        session = get_session()
        prompt = (
            session.query(CompanyPrompt)
            .filter(
                CompanyPrompt.id == prompt_id,
                CompanyPrompt.company_id == self.company_id,
            )
            .first()
        )
        if not prompt:
            session.close()
            raise Exception("Company prompt not found")
        session.delete(prompt)
        session.commit()
        session.close()

    def share_prompt_to_company(self, prompt_id: str):
        """
        Share a user's prompt to the company level.
        Company admin function.
        """
        session = get_session()

        # Get user's prompt
        user_prompt = (
            session.query(Prompt)
            .filter(
                Prompt.id == prompt_id,
                Prompt.user_id == self.user_id,
            )
            .first()
        )
        if not user_prompt:
            session.close()
            raise Exception("Prompt not found")

        if not self.company_id:
            session.close()
            raise Exception("No company context")

        # Create company version
        category = user_prompt.prompt_category.name
        session.close()

        return self.add_company_prompt(
            name=user_prompt.name,
            content=user_prompt.content,
            category=category,
            description=user_prompt.description,
        )

    def get_company_prompt_categories(self, company_id: str = None):
        """Get all company-level prompt categories. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            return []

        session = get_session()
        categories = (
            session.query(CompanyPromptCategory)
            .filter(CompanyPromptCategory.company_id == target_company)
            .all()
        )

        result = [
            {
                "id": str(cat.id),
                "name": cat.name,
                "description": cat.description,
                "server_category_id": (
                    str(cat.server_category_id) if cat.server_category_id else None
                ),
            }
            for cat in categories
        ]
        session.close()
        return result

    def add_company_prompt_category(
        self, name: str, description: str = "", company_id: str = None
    ):
        """Add a company-level prompt category. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            raise Exception("No company context")

        session = get_session()
        cat = CompanyPromptCategory(
            company_id=target_company,
            name=name,
            description=description,
        )
        session.add(cat)
        session.commit()
        cat_id = str(cat.id)
        session.close()
        return cat_id

    def delete_company_prompt_category(self, category_id: str):
        """Delete a company-level prompt category. Company admin function."""
        session = get_session()
        cat = (
            session.query(CompanyPromptCategory)
            .filter(
                CompanyPromptCategory.id == category_id,
                CompanyPromptCategory.company_id == self.company_id,
            )
            .first()
        )
        if not cat:
            session.close()
            raise Exception("Category not found")
        session.delete(cat)
        session.commit()
        session.close()
