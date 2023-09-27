from DBConnection import (
    get_session,
    Chain as ChainDB,
    ChainStep,
    ChainStepResponse,
    Agent,
    Argument,
    ChainStepArgument,
    Prompt,
    Command,
    User,
)


class Chain:
    def __init__(self, user="USER"):
        self.session = get_session()
        self.user = user
        user_data = self.session.query(User).filter(User.email == self.user).first()
        self.user_id = user_data.id

    def get_chain(self, chain_name):
        chain_name = chain_name.replace("%20", " ")
        chain_db = (
            self.session.query(ChainDB)
            .filter(
                ChainDB.name == chain_name,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )
        if chain_db is None:
            return None

        chain_steps = (
            self.session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )

        steps = []
        for step in chain_steps:
            agent_name = self.session.query(Agent).get(step.agent_id).name
            prompt = {}
            if step.target_chain_id:
                prompt["chain_name"] = (
                    self.session.query(ChainDB).get(step.target_chain_id).name
                )
            elif step.target_command_id:
                prompt["command_name"] = (
                    self.session.query(Command).get(step.target_command_id).name
                )
            elif step.target_prompt_id:
                prompt["prompt_name"] = (
                    self.session.query(Prompt).get(step.target_prompt_id).name
                )

            # Retrieve argument data for the step
            arguments = (
                self.session.query(Argument, ChainStepArgument)
                .join(ChainStepArgument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id == step.id)
                .all()
            )

            prompt_args = {}
            for argument, chain_step_argument in arguments:
                prompt_args[argument.name] = chain_step_argument.value

            prompt.update(prompt_args)

            step_data = {
                "step": step.step_number,
                "agent_name": agent_name,
                "prompt_type": step.prompt_type,
                "prompt": prompt,
            }
            steps.append(step_data)

        chain_data = {
            "chain_name": chain_db.name,
            "steps": steps,
        }

        return chain_data

    def get_chains(self):
        chains = (
            self.session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        )
        return [chain.name for chain in chains]

    def add_chain(self, chain_name):
        chain = ChainDB(name=chain_name)
        self.session.add(chain)
        self.session.commit()

    def rename_chain(self, chain_name, new_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain.name = new_name
        self.session.commit()

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        agent = (
            self.session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
            .first()
        )
        if "prompt_category" in prompt:
            prompt_category = prompt["prompt_category"]
        else:
            prompt_category = "Default"
        if "prompt_name" in prompt:
            argument_key = "prompt_name"
            target_id = (
                self.session.query(Prompt)
                .filter(
                    Prompt.name == prompt["prompt_name"],
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
                .id
            )
            target_type = "prompt"
        elif "chain_name" in prompt:
            argument_key = "chain_name"
            target_id = (
                self.session.query(Chain)
                .filter(
                    Chain.name == prompt["chain_name"], Chain.user_id == self.user_id
                )
                .first()
                .id
            )
            target_type = "chain"
        elif "command_name" in prompt:
            argument_key = "command_name"
            target_id = (
                self.session.query(Command)
                .filter(Command.name == prompt["command_name"])
                .first()
                .id
            )
            target_type = "command"

        argument_value = prompt[argument_key]
        prompt_arguments = prompt.copy()
        del prompt_arguments[argument_key]

        chain_step = ChainStep(
            chain_id=chain.id,
            step_number=step_number,
            agent_id=agent.id,
            prompt_type=prompt_type,
            prompt=argument_value,
            target_chain_id=target_id if target_type == "chain" else None,
            target_command_id=target_id if target_type == "command" else None,
            target_prompt_id=target_id if target_type == "prompt" else None,
        )
        self.session.add(chain_step)
        self.session.commit()

        for argument_name, argument_value in prompt_arguments.items():
            argument = (
                self.session.query(Argument)
                .filter(Argument.name == argument_name)
                .first()
            )
            if not argument:
                # Handle the case where argument not found based on argument_name
                # You can choose to skip this argument or raise an exception
                continue

            chain_step_argument = ChainStepArgument(
                chain_step_id=chain_step.id,
                argument_id=argument.id,
                value=argument_value,
            )
            self.session.add(chain_step_argument)
            self.session.commit()

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain_step = (
            self.session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )

        agent = (
            self.session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
            .first()
        )
        agent_id = agent.id if agent else None

        target_chain_id = None
        target_command_id = None
        target_prompt_id = None

        if prompt_type == "Command":
            command_name = prompt.get("command_name")
            command_args = prompt.copy()
            del command_args["command_name"]
            command = (
                self.session.query(Command).filter(Command.name == command_name).first()
            )
            if command:
                target_command_id = command.id
        elif prompt_type == "Prompt":
            prompt_name = prompt.get("prompt_name")
            prompt_category = prompt_name = prompt.get("prompt_name", "Default")
            prompt_args = prompt.copy()
            del prompt_args["prompt_name"]
            prompt_obj = (
                self.session.query(Prompt)
                .filter(
                    Prompt.name == prompt_name,
                    Prompt.prompt_category.has(name=prompt_category),
                    Prompt.user_id == self.user_id,
                )
                .first()
            )
            if prompt_obj:
                target_prompt_id = prompt_obj.id
        elif prompt_type == "Chain":
            chain_name = prompt.get("chain_name")
            chain_args = prompt.copy()
            del chain_args["chain_name"]
            chain_obj = (
                self.session.query(ChainDB)
                .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
                .first()
            )
            if chain_obj:
                target_chain_id = chain_obj.id

        chain_step.agent_id = agent_id
        chain_step.prompt_type = prompt_type
        chain_step.prompt = prompt.get("prompt_name", None)
        chain_step.target_chain_id = target_chain_id
        chain_step.target_command_id = target_command_id
        chain_step.target_prompt_id = target_prompt_id

        self.session.commit()

        # Update the arguments for the step
        self.session.query(ChainStepArgument).filter(
            ChainStepArgument.chain_step_id == chain_step.id
        ).delete()

        for argument_name, argument_value in prompt_args.items():
            argument = (
                self.session.query(Argument)
                .filter(Argument.name == argument_name)
                .first()
            )
            if argument:
                chain_step_argument = ChainStepArgument(
                    chain_step_id=chain_step.id,
                    argument_id=argument.id,
                    value=argument_value,
                )
                self.session.add(chain_step_argument)
                self.session.commit()

    def delete_step(self, chain_name, step_number):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )

        if chain:
            chain_step = (
                self.session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )
            if chain_step:
                self.session.delete(
                    chain_step
                )  # Remove the chain step from the session
                self.session.commit()
            else:
                print(
                    f"No step found with number {step_number} in chain '{chain_name}'"
                )
        else:
            print(f"No chain found with name '{chain_name}'")

    def delete_chain(self, chain_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        self.session.delete(chain)
        self.session.commit()

    def get_step(self, chain_name, step_number):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain_step = (
            self.session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        return chain_step

    def get_steps(self, chain_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain_steps = (
            self.session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        return chain_steps

    def move_step(self, chain_name, current_step_number, new_step_number):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain_step = (
            self.session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number == current_step_number,
            )
            .first()
        )
        chain_step.step_number = new_step_number
        if new_step_number < current_step_number:
            self.session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number >= new_step_number,
                ChainStep.step_number < current_step_number,
            ).update(
                {"step_number": ChainStep.step_number + 1}, synchronize_session=False
            )
        else:
            self.session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number > current_step_number,
                ChainStep.step_number <= new_step_number,
            ).update(
                {"step_number": ChainStep.step_number - 1}, synchronize_session=False
            )
        self.session.commit()

    def get_step_response(self, chain_name, step_number="all"):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )

        if step_number == "all":
            chain_steps = (
                self.session.query(ChainStep)
                .filter(ChainStep.chain_id == chain.id)
                .order_by(ChainStep.step_number)
                .all()
            )

            responses = {}
            for step in chain_steps:
                chain_step_responses = (
                    self.session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                responses[str(step.step_number)] = step_responses

            return responses
        else:
            chain_step = (
                self.session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )

            if chain_step:
                chain_step_responses = (
                    self.session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == chain_step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                return step_responses
            else:
                return None

    def get_chain_responses(self, chain_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        chain_steps = (
            self.session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        responses = {}
        for step in chain_steps:
            chain_step_responses = (
                self.session.query(ChainStepResponse)
                .filter(ChainStepResponse.chain_step_id == step.id)
                .order_by(ChainStepResponse.timestamp)
                .all()
            )
            step_responses = [response.content for response in chain_step_responses]
            responses[str(step.step_number)] = step_responses
        return responses

    def import_chain(self, chain_name: str, steps: dict):
        chain = ChainDB(name=chain_name, user_id=self.user_id)
        self.session.add(chain)
        self.session.commit()

        steps = steps["steps"] if "steps" in steps else steps
        for step_data in steps:
            agent_name = step_data["agent_name"]
            agent = (
                self.session.query(Agent)
                .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
                .first()
            )
            if not agent:
                # Handle the case where agent not found based on agent_name
                # You can choose to skip this step or raise an exception
                continue

            prompt = step_data["prompt"]
            if "prompt_name" in prompt:
                argument_key = "prompt_name"
                prompt_category = prompt.get("prompt_category", "Default")
                target_id = (
                    self.session.query(Prompt)
                    .filter(
                        Prompt.name == prompt["prompt_name"],
                        Prompt.user_id == self.user_id,
                        Prompt.prompt_category.has(name=prompt_category),
                    )
                    .first()
                    .id
                )
                target_type = "prompt"
            elif "chain_name" in prompt:
                argument_key = "chain_name"
                target_id = (
                    self.session.query(Chain)
                    .filter(
                        Chain.name == prompt["chain_name"],
                        Chain.user_id == self.user_id,
                    )
                    .first()
                    .id
                )
                target_type = "chain"
            elif "command_name" in prompt:
                argument_key = "command_name"
                target_id = (
                    self.session.query(Command)
                    .filter(Command.name == prompt["command_name"])
                    .first()
                    .id
                )
                target_type = "command"
            else:
                # Handle the case where the argument key is not found
                # You can choose to skip this step or raise an exception
                continue

            argument_value = prompt[argument_key]
            prompt_arguments = prompt.copy()
            del prompt_arguments[argument_key]

            chain_step = ChainStep(
                chain_id=chain.id,
                step_number=step_data["step"],
                agent_id=agent.id,
                prompt_type=step_data["prompt_type"],
                prompt=argument_value,
                target_chain_id=target_id if target_type == "chain" else None,
                target_command_id=target_id if target_type == "command" else None,
                target_prompt_id=target_id if target_type == "prompt" else None,
            )
            self.session.add(chain_step)
            self.session.commit()

            for argument_name, argument_value in prompt_arguments.items():
                argument = (
                    self.session.query(Argument)
                    .filter(Argument.name == argument_name)
                    .first()
                )
                if not argument:
                    # Handle the case where argument not found based on argument_name
                    # You can choose to skip this argument or raise an exception
                    continue

                chain_step_argument = ChainStepArgument(
                    chain_step_id=chain_step.id,
                    argument_id=argument.id,
                    value=argument_value,
                )
                self.session.add(chain_step_argument)
                self.session.commit()

        return f"Chain '{chain_name}' imported."

    def get_step_content(self, chain_name, prompt_content, user_input, agent_name):
        if isinstance(prompt_content, dict):
            new_prompt_content = {}
            for arg, value in prompt_content.items():
                if isinstance(value, str):
                    if "{user_input}" in value:
                        value = value.replace("{user_input}", user_input)
                    if "{agent_name}" in value:
                        value = value.replace("{agent_name}", agent_name)
                    if "{STEP" in value:
                        step_count = value.count("{STEP")
                        for i in range(step_count):
                            new_step_number = int(value.split("{STEP")[1].split("}")[0])
                            step_response = self.get_step_response(
                                chain_name=chain_name, step_number=new_step_number
                            )
                            if step_response:
                                resp = (
                                    step_response[0]
                                    if isinstance(step_response, list)
                                    else step_response
                                )
                                value = value.replace(
                                    f"{{STEP{new_step_number}}}", f"{resp}"
                                )
                new_prompt_content[arg] = value
            return new_prompt_content
        elif isinstance(prompt_content, str):
            new_prompt_content = prompt_content
            if "{user_input}" in prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{user_input}", user_input
                )
            if "{agent_name}" in new_prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{agent_name}", agent_name
                )
            if "{STEP" in prompt_content:
                step_count = prompt_content.count("{STEP")
                for i in range(step_count):
                    new_step_number = int(
                        prompt_content.split("{STEP")[1].split("}")[0]
                    )
                    step_response = self.get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    if step_response:
                        resp = (
                            step_response[0]
                            if isinstance(step_response, list)
                            else step_response
                        )
                        new_prompt_content = new_prompt_content.replace(
                            f"{{STEP{new_step_number}}}", f"{resp}"
                        )
            return new_prompt_content
        else:
            return prompt_content

    async def update_chain_responses(self, chain_name, responses):
        for response in responses:
            step_data = responses[response]
            chain_step = self.get_step(chain_name, step_data["step"])
            response_content = {
                "chain_step_id": chain_step.id,
                "content": step_data["response"],
            }
            chain_step_response = ChainStepResponse(**response_content)
            self.session.add(chain_step_response)
            self.session.commit()
