from DB import (
    get_session,
    Chain as ChainDB,
    ChainStep,
    ChainStepResponse,
    ChainRun,
    Agent,
    Argument,
    ChainStepArgument,
    Prompt,
    Command,
    User,
)
from Globals import getenv, DEFAULT_USER
from Prompts import Prompts
from Extensions import Extensions
import logging
import asyncio

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Chain:
    def __init__(self, user=DEFAULT_USER, ApiClient=None):
        self.session = get_session()
        self.user = user
        self.ApiClient = ApiClient
        try:
            user_data = self.session.query(User).filter(User.email == self.user).first()
            self.user_id = user_data.id
        except:
            user_data = (
                self.session.query(User).filter(User.email == DEFAULT_USER).first()
            )
            self.user_id = user_data.id

    def get_chain(self, chain_name):
        chain_name = chain_name.replace("%20", " ")
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        chain_db = (
            self.session.query(ChainDB)
            .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db is None:
            chain_db = (
                self.session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
        if chain_db is None:
            return []
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
            "id": chain_db.id,
            "chain_name": chain_db.name,
            "steps": steps,
        }

        return chain_data

    def get_chains(self):
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        global_chains = (
            self.session.query(ChainDB).filter(ChainDB.user_id == user_data.id).all()
        )
        chains = (
            self.session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        )
        chain_list = []
        for chain in chains:
            chain_list.append(chain.name)
        for chain in global_chains:
            chain_list.append(chain.name)
        return chain_list

    def add_chain(self, chain_name):
        chain = ChainDB(name=chain_name, user_id=self.user_id)
        self.session.add(chain)
        self.session.commit()

    def rename_chain(self, chain_name, new_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
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
        argument_key = None
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
        else:
            prompt["prompt_name"] = "User Input"
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
                logging.info(
                    f"No step found with number {step_number} in chain '{chain_name}'"
                )
        else:
            logging.info(f"No chain found with name '{chain_name}'")

    def delete_chain(self, chain_name):
        chain = (
            self.session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        self.session.delete(chain)
        self.session.commit()

    def get_steps(self, chain_name):
        chain_name = chain_name.replace("%20", " ")
        user_data = self.session.query(User).filter(User.email == DEFAULT_USER).first()
        chain_db = (
            self.session.query(ChainDB)
            .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db is None:
            chain_db = (
                self.session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
        if chain_db is None:
            return []
        chain_steps = (
            self.session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        return chain_steps

    def get_step(self, chain_name, step_number):
        steps = self.get_steps(chain_name=chain_name)
        chain_step = None
        for step in steps:
            if step.step_number == step_number:
                chain_step = step
                break
        return chain_step

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

    def get_step_response(self, chain_name, chain_run_id=None, step_number="all"):
        if chain_run_id is None:
            chain_run_id = self.get_last_chain_run_id(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        if step_number == "all":
            chain_steps = (
                self.session.query(ChainStep)
                .filter(ChainStep.chain_id == chain_data["id"])
                .order_by(ChainStep.step_number)
                .all()
            )

            responses = {}
            for step in chain_steps:
                chain_step_responses = (
                    self.session.query(ChainStepResponse)
                    .filter(
                        ChainStepResponse.chain_step_id == step.id,
                        ChainStepResponse.chain_run_id == chain_run_id,
                    )
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                responses[str(step.step_number)] = step_responses

            return responses
        else:
            step_number = int(step_number)
            chain_step = (
                self.session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain_data["id"],
                    ChainStep.step_number == step_number,
                )
                .first()
            )

            if chain_step:
                chain_step_responses = (
                    self.session.query(ChainStepResponse)
                    .filter(
                        ChainStepResponse.chain_step_id == chain_step.id,
                        ChainStepResponse.chain_run_id == chain_run_id,
                    )
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                return step_responses
            else:
                return None

    def get_chain_responses(self, chain_name):
        chain_steps = self.get_steps(chain_name=chain_name)
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
                # Use the first agent in the database
                agent = (
                    self.session.query(Agent)
                    .filter(Agent.user_id == self.user_id)
                    .first()
                )
            prompt = step_data["prompt"]
            if "prompt_type" not in step_data:
                step_data["prompt_type"] = "prompt"
            prompt_type = step_data["prompt_type"].lower()
            if prompt_type == "prompt":
                argument_key = "prompt_name"
                prompt_category = prompt.get("prompt_category", "Default")
                target_id = (
                    self.session.query(Prompt)
                    .filter(
                        Prompt.name == prompt[argument_key],
                        Prompt.user_id == self.user_id,
                        Prompt.prompt_category.has(name=prompt_category),
                    )
                    .first()
                    .id
                )
                target_type = "prompt"
            elif prompt_type == "chain":
                argument_key = "chain_name"
                if "chain" in prompt:
                    argument_key = "chain"
                target_id = (
                    self.session.query(ChainDB)
                    .filter(
                        ChainDB.name == prompt[argument_key],
                        ChainDB.user_id == self.user_id,
                    )
                    .first()
                    .id
                )
                target_type = "chain"
            elif prompt_type == "command":
                argument_key = "command_name"
                target_id = (
                    self.session.query(Command)
                    .filter(Command.name == prompt[argument_key])
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
        return f"Imported chain: {chain_name}"

    def get_chain_step_dependencies(self, chain_name):
        chain_steps = self.get_steps(chain_name=chain_name)
        prompts = Prompts(user=self.user)
        chain_dependencies = {}
        for step in chain_steps:
            step_dependencies = []
            prompt = step.prompt
            if not isinstance(prompt, dict) and not isinstance(prompt, str):
                prompt = str(prompt)
            if isinstance(prompt, dict):
                for key, value in prompt.items():
                    if "{STEP" in value:
                        step_count = value.count("{STEP")
                        for i in range(step_count):
                            new_step_number = int(value.split("{STEP")[1].split("}")[0])
                            step_dependencies.append(new_step_number)
                if "prompt_name" in prompt:
                    prompt_text = prompts.get_prompt(
                        prompt_name=prompt["prompt_name"],
                        prompt_category=(
                            prompt["prompt_category"]
                            if "prompt_category" in prompt
                            else "Default"
                        ),
                    )
                    # See if "{context}" is in the prompt
                    if "{context}" in prompt_text:
                        # Add all prior steps in the chain as deps
                        for i in range(step.step_number):
                            step_dependencies.append(i)
            elif isinstance(prompt, str):
                if "{STEP" in prompt:
                    step_count = prompt.count("{STEP")
                    for i in range(step_count):
                        new_step_number = int(prompt.split("{STEP")[1].split("}")[0])
                        step_dependencies.append(new_step_number)
                    if "{context}" in prompt:
                        # Add all prior steps in the chain as deps
                        for i in range(step.step_number):
                            step_dependencies.append(i)
            chain_dependencies[str(step.step_number)] = step_dependencies
        return chain_dependencies

    async def check_if_dependencies_met(
        self, chain_run_id, chain_name, step_number, dependencies=[]
    ):
        if dependencies == []:
            chain_dependencies = self.get_chain_step_dependencies(chain_name=chain_name)
            dependencies = chain_dependencies[str(step_number)]

        async def check_dependencies_met(dependencies):
            for dependency in dependencies:
                try:
                    step_responses = self.get_step_response(
                        chain_name=chain_name,
                        chain_run_id=chain_run_id,
                        step_number=int(dependency),
                    )
                except:
                    return False
                if not step_responses:
                    return False
            return True

        dependencies_met = await check_dependencies_met(dependencies)
        while not dependencies_met:
            await asyncio.sleep(1)
            dependencies_met = await check_dependencies_met(dependencies)
        return True

    def get_step_content(
        self, chain_run_id, chain_name, prompt_content, user_input, agent_name
    ):
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
                                chain_run_id=chain_run_id,
                                chain_name=chain_name,
                                step_number=new_step_number,
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
                        chain_run_id=chain_run_id,
                        chain_name=chain_name,
                        step_number=new_step_number,
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

    async def update_step_response(
        self, chain_run_id, chain_name, step_number, response
    ):
        chain_step = self.get_step(chain_name=chain_name, step_number=step_number)
        if chain_step:
            existing_response = (
                self.session.query(ChainStepResponse)
                .filter(
                    ChainStepResponse.chain_step_id == chain_step.id,
                    ChainStepResponse.chain_run_id == chain_run_id,
                )
                .order_by(ChainStepResponse.timestamp.desc())
                .first()
            )
            if existing_response:
                if isinstance(existing_response.content, dict) and isinstance(
                    response, dict
                ):
                    existing_response.content.update(response)
                    self.session.commit()
                elif isinstance(existing_response.content, list) and isinstance(
                    response, list
                ):
                    existing_response.content.extend(response)
                    self.session.commit()
                else:
                    chain_step_response = ChainStepResponse(
                        chain_step_id=chain_step.id,
                        chain_run_id=chain_run_id,
                        content=response,
                    )
                    self.session.add(chain_step_response)
                    self.session.commit()
            else:
                chain_step_response = ChainStepResponse(
                    chain_step_id=chain_step.id,
                    chain_run_id=chain_run_id,
                    content=response,
                )
                self.session.add(chain_step_response)
                self.session.commit()

    async def get_chain_run_id(self, chain_name):
        chain_run = ChainRun(
            chain_id=self.get_chain(chain_name=chain_name)["id"],
            user_id=self.user_id,
        )
        self.session.add(chain_run)
        self.session.commit()
        return chain_run.id

    async def get_last_chain_run_id(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        chain_run = (
            self.session.query(ChainRun)
            .filter(ChainRun.chain_id == chain_data["id"])
            .order_by(ChainRun.timestamp.desc())
            .first()
        )
        if chain_run:
            return chain_run.id
        else:
            return await self.get_chain_run_id(chain_name=chain_name)

    def get_chain_args(self, chain_name):
        skip_args = [
            "command_list",
            "context",
            "COMMANDS",
            "date",
            "conversation_history",
            "agent_name",
            "working_directory",
            "helper_agent_name",
        ]
        chain_data = self.get_chain(chain_name=chain_name)
        steps = chain_data["steps"]
        prompt_args = []
        args = []
        for step in steps:
            try:
                prompt = step["prompt"]
                if "prompt_name" in prompt:
                    prompt_text = Prompts(user=self.user).get_prompt(
                        prompt_name=prompt["prompt_name"]
                    )
                    args = Prompts(user=self.user).get_prompt_args(
                        prompt_text=prompt_text
                    )
                elif "command_name" in prompt:
                    args = Extensions().get_command_args(
                        command_name=prompt["command_name"]
                    )
                elif "chain_name" in prompt:
                    args = self.get_chain_args(chain_name=prompt["chain_name"])
                for arg in args:
                    if arg not in prompt_args and arg not in skip_args:
                        prompt_args.append(arg)
            except Exception as e:
                logging.error(f"Error getting chain args: {e}")
        return prompt_args
