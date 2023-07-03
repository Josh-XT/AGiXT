from DBConnection import (
    session,
    Chain as ChainDB,
    ChainStep,
    ChainStepResponse,
    Agent,
    Argument,
    ChainStepArgument,
    Prompt,
    Command,
)
from agixtsdk import AGiXTSDK
import logging
import json

base_uri = "http://localhost:7437"
ApiClient = AGiXTSDK(base_uri=base_uri)


def import_chains():
    chain_dir = os.path.abspath("chains")

    chain_files = [
        file
        for file in os.listdir(chain_dir)
        if os.path.isfile(os.path.join(chain_dir, file)) and file.endswith(".json")
    ]

    if not chain_files:
        print(f"No JSON files found in chains directory.")
        return

    chain_importer = Chain()

    for file in chain_files:
        chain_name = os.path.splitext(file)[0]
        file_path = os.path.join(chain_dir, file)

        with open(file_path, "r") as f:
            try:
                chain_data = json.load(f)
                result = chain_importer.import_chain(chain_name, chain_data)
                print(result)
            except json.JSONDecodeError as e:
                print(f"Error importing chain from '{file}': Invalid JSON format.")
            except Exception as e:
                print(f"Error importing chain from '{file}': {str(e)}")


class Chain:
    def get_chain(self, chain_name):
        chain = (
            session.query(ChainStep)
            .join(ChainDB)
            .filter(ChainDB.name == chain_name)
            .all()
        )
        return chain

    def get_chains(self):
        chains = session.query(ChainDB).all()
        return [chain.name for chain in chains]

    def add_chain(self, chain_name):
        chain = ChainDB(name=chain_name)
        session.add(chain)
        session.commit()

    def rename_chain(self, chain_name, new_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain.name = new_name
        session.commit()

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()

        # Retrieve the agent_id based on the agent_name
        agent = session.query(Agent).filter(Agent.name == agent_name).first()
        agent_id = agent.id if agent else None

        chain_step = ChainStep(
            chain_id=chain.id,
            step_number=step_number,
            agent_id=agent_id,  # Assign the retrieved agent_id
            agent_name=agent_name,
            prompt_type=prompt_type,
            prompt=prompt,
        )
        session.add(chain_step)
        session.commit()

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        chain_step.agent_name = agent_name
        chain_step.prompt_type = prompt_type
        chain_step.prompt = prompt
        session.commit()

    def delete_step(self, chain_name, step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        session.delete(chain_step)
        session.commit()

    def delete_chain(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        session.delete(chain)
        session.commit()

    def get_step(self, chain_name, step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        return chain_step

    def get_steps(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        return chain_steps

    def move_step(self, chain_name, current_step_number, new_step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number == current_step_number,
            )
            .first()
        )
        chain_step.step_number = new_step_number
        if new_step_number < current_step_number:
            session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number >= new_step_number,
                ChainStep.step_number < current_step_number,
            ).update(
                {"step_number": ChainStep.step_number + 1}, synchronize_session=False
            )
        else:
            session.query(ChainStep).filter(
                ChainStep.chain_id == chain.id,
                ChainStep.step_number > current_step_number,
                ChainStep.step_number <= new_step_number,
            ).update(
                {"step_number": ChainStep.step_number - 1}, synchronize_session=False
            )
        session.commit()

    def get_step_response(self, chain_name, step_number="all"):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        if step_number == "all":
            chain_steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id == chain.id)
                .order_by(ChainStep.step_number)
                .all()
            )
            responses = {}
            for step in chain_steps:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                responses[str(step.step_number)] = step_responses
            return responses
        else:
            chain_step = (
                session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )
            if chain_step:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(ChainStepResponse.chain_step_id == chain_step.id)
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                return [response.content for response in chain_step_responses]
            else:
                return []

    def get_chain_responses(self, chain_name):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        responses = {}
        for step in chain_steps:
            chain_step_responses = (
                session.query(ChainStepResponse)
                .filter(ChainStepResponse.chain_step_id == step.id)
                .order_by(ChainStepResponse.timestamp)
                .all()
            )
            step_responses = [response.content for response in chain_step_responses]
            responses[str(step.step_number)] = step_responses
        return responses

    def import_chain(self, chain_name: str, steps: dict):
        chain = ChainDB(name=chain_name)
        session.add(chain)
        session.commit()

        steps = steps["steps"] if "steps" in steps else steps
        for step_data in steps:
            agent_name = step_data["agent_name"]
            agent = session.query(Agent).filter(Agent.name == agent_name).first()
            if not agent:
                # Handle the case where agent not found based on agent_name
                # You can choose to skip this step or raise an exception
                continue

            prompt = step_data["prompt"]
            if "prompt_name" in prompt:
                argument_key = "prompt_name"
                target_id = (
                    session.query(Prompt)
                    .filter(Prompt.name == prompt["prompt_name"])
                    .first()
                    .id
                )
                target_type = "prompt"
            elif "chain_name" in prompt:
                argument_key = "chain_name"
                target_id = (
                    session.query(Chain)
                    .filter(Chain.name == prompt["chain_name"])
                    .first()
                    .id
                )
                target_type = "chain"
            elif "command_name" in prompt:
                argument_key = "command_name"
                target_id = (
                    session.query(Command)
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
            session.add(chain_step)
            session.commit()

            for argument_name, argument_value in prompt_arguments.items():
                argument = (
                    session.query(Argument)
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
                session.add(chain_step_argument)
                session.commit()

        return f"Chain '{chain_name}' imported."

    def get_step_content(self, chain_name, prompt_content, user_input, agent_name):
        new_prompt_content = {}
        if isinstance(prompt_content, dict):
            for arg, value in prompt_content.items():
                if isinstance(value, str):
                    if "{user_input}" in value:
                        value = value.replace("{user_input}", user_input)
                    if "{agent_name}" in value:
                        value = value.replace("{agent_name}", agent_name)
                    if "{STEP" in value:
                        # Count how many times {STEP is in the value
                        step_count = value.count("{STEP")
                        for i in range(step_count):
                            # Get the step number from value between {STEP and }
                            new_step_number = int(value.split("{STEP")[1].split("}")[0])
                            # get the response from the step number
                            step_response = Chain().get_step_response(
                                chain_name=chain_name, step_number=new_step_number
                            )
                            # replace the {STEPx} with the response
                            if step_response:
                                resp = (
                                    step_response["response"]
                                    if "response" in step_response
                                    else f"{step_response}"
                                )
                                value = value.replace(
                                    f"{{STEP{new_step_number}}}",
                                    f"{resp}",
                                )
                new_prompt_content[arg] = value
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
                step_count = value.count("{STEP")
                for i in range(step_count):
                    # Get the step number from value between {STEP and }
                    new_step_number = int(
                        prompt_content.split("{STEP")[1].split("}")[0]
                    )
                    # get the response from the step number
                    step_response = Chain().get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    # replace the {STEPx} with the response
                    if step_response:
                        resp = (
                            step_response["response"]
                            if "response" in step_response
                            else f"{step_response}"
                        )
                        new_prompt_content = prompt_content.replace(
                            f"{{STEP{new_step_number}}}", f"{resp}"
                        )
            if new_prompt_content == {}:
                new_prompt_content = prompt_content
        return new_prompt_content

    async def run_chain_step(
        self, step: dict = {}, chain_name="", user_input="", agent_override=""
    ):
        if step:
            if "prompt_type" in step:
                if agent_override != "":
                    self.agent_name = agent_override
                else:
                    self.agent_name = step["agent_name"]
                prompt_type = step["prompt_type"]
                step_number = step["step"]
                if "prompt_name" in step["prompt"]:
                    prompt_name = step["prompt"]["prompt_name"]
                else:
                    prompt_name = ""
                args = self.get_step_content(
                    chain_name=chain_name,
                    prompt_content=step["prompt"],
                    user_input=user_input,
                    agent_name=self.agent_name,
                )
                if prompt_type == "Command":
                    return await self.agent.execute(
                        command_name=args["command_name"],
                        command_args=args,
                    )
                elif prompt_type == "Prompt":
                    result = ApiClient.prompt_agent(
                        agent_name=self.agent_name,
                        prompt_name=prompt_name,
                        prompt_args={
                            "chain_name": chain_name,
                            "step_number": step_number,
                            "user_input": user_input,
                            **args,
                        },
                    )
                elif prompt_type == "Chain":
                    result = ApiClient.run_chain(
                        chain_name=args["chain"],
                        user_input=args["input"],
                        agent_name=self.agent_name,
                        all_responses=False,
                        from_step=1,
                    )
        if result:
            return result
        else:
            return None

    async def run_chain(
        self,
        chain_name,
        user_input=None,
        all_responses=True,
        agent_override="",
        from_step=1,
    ):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        if chain is None:
            return f"Chain '{chain_name}' not found."
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        last_response = ""
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain.id, ChainStep.step_number >= from_step)
            .order_by(ChainStep.step_number)
            .all()
        )
        for chain_step in chain_steps:
            step_data = {
                "step": chain_step.step_number,
                "agent_name": (
                    agent_override if agent_override else chain_step.agent_name
                ),
                "prompt_type": chain_step.prompt_type,
                "prompt": chain_step.prompt,
            }
            logging.info(
                f"Running step {chain_step.step_number} with agent {step_data['agent_name']}."
            )
            step_response = await self.run_chain_step(
                step=step_data,
                chain_name=chain_name,
                user_input=user_input,
                agent_override=agent_override,
            )  # Get the response of the current step.
            step_data["response"] = step_response
            last_response = step_response
            responses[str(chain_step.step_number)] = step_data  # Store the response.
            logging.info(f"Response: {step_response}")
            session.add(
                ChainStepResponse(content=step_response, chain_step_id=chain_step.id)
            )
            session.commit()
        if all_responses:
            return responses
        else:
            # Return only the last response in the chain.
            return last_response
