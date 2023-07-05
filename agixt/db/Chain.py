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
from Extensions import Extensions
import logging
import os
from dotenv import load_dotenv

load_dotenv()
ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY")
)


class Chain:
    def get_chain(self, chain_name):
        chain_name = chain_name.replace("%20", " ")
        chain_db = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        if chain_db is None:
            return None

        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )

        steps = []
        for step in chain_steps:
            agent_name = session.query(Agent).get(step.agent_id).name
            prompt = {}
            if step.target_chain_id:
                prompt["chain_name"] = (
                    session.query(ChainDB).get(step.target_chain_id).name
                )
            elif step.target_command_id:
                prompt["command_name"] = (
                    session.query(Command).get(step.target_command_id).name
                )
            elif step.target_prompt_id:
                prompt["prompt_name"] = (
                    session.query(Prompt).get(step.target_prompt_id).name
                )

            # Retrieve argument data for the step
            arguments = (
                session.query(Argument, ChainStepArgument)
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
        agent = session.query(Agent).filter(Agent.name == agent_name).first()
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
        session.add(chain_step)
        session.commit()

        for argument_name, argument_value in prompt_arguments.items():
            argument = (
                session.query(Argument).filter(Argument.name == argument_name).first()
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

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()
        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )

        agent = session.query(Agent).filter(Agent.name == agent_name).first()
        agent_id = agent.id if agent else None

        target_chain_id = None
        target_command_id = None
        target_prompt_id = None

        if prompt_type == "Command":
            command_name = prompt.get("command_name")
            command_args = prompt.copy()
            del command_args["command_name"]
            command = (
                session.query(Command).filter(Command.name == command_name).first()
            )
            if command:
                target_command_id = command.id
        elif prompt_type == "Prompt":
            prompt_name = prompt.get("prompt_name")
            prompt_args = prompt.copy()
            del prompt_args["prompt_name"]
            prompt_obj = (
                session.query(Prompt).filter(Prompt.name == prompt_name).first()
            )
            if prompt_obj:
                target_prompt_id = prompt_obj.id
        elif prompt_type == "Chain":
            chain_name = prompt.get("chain_name")
            chain_args = prompt.copy()
            del chain_args["chain_name"]
            chain_obj = (
                session.query(ChainDB).filter(ChainDB.name == chain_name).first()
            )
            if chain_obj:
                target_chain_id = chain_obj.id

        chain_step.agent_id = agent_id
        chain_step.prompt_type = prompt_type
        chain_step.prompt = prompt.get("prompt_name", None)
        chain_step.target_chain_id = target_chain_id
        chain_step.target_command_id = target_command_id
        chain_step.target_prompt_id = target_prompt_id

        session.commit()

        # Update the arguments for the step
        session.query(ChainStepArgument).filter(
            ChainStepArgument.chain_step_id == chain_step.id
        ).delete()

        for argument_name, argument_value in prompt_args.items():
            argument = (
                session.query(Argument).filter(Argument.name == argument_name).first()
            )
            if argument:
                chain_step_argument = ChainStepArgument(
                    chain_step_id=chain_step.id,
                    argument_id=argument.id,
                    value=argument_value,
                )
                session.add(chain_step_argument)
                session.commit()

    def delete_step(self, chain_name, step_number):
        chain = session.query(ChainDB).filter(ChainDB.name == chain_name).first()

        if chain:
            chain_step = (
                session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )
            if chain_step:
                session.delete(chain_step)  # Remove the chain step from the session
                session.commit()
            else:
                print(
                    f"No step found with number {step_number} in chain '{chain_name}'"
                )
        else:
            print(f"No chain found with name '{chain_name}'")

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
                step_responses = [response.content for response in chain_step_responses]
                return step_responses
            else:
                return None

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

    async def run_chain_step(
        self, step: dict = {}, chain_name="", user_input="", agent_override=""
    ):
        if step:
            if "prompt_type" in step:
                if agent_override != "":
                    agent_name = agent_override
                else:
                    agent_name = step["agent_name"]
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
                    agent_name=step["agent_name"],
                )

                if prompt_type == "Command":
                    return await Extensions().execute_command(
                        command_name=step["prompt"]["command_name"], command_args=args
                    )

                elif prompt_type == "Prompt":
                    result = ApiClient.prompt_agent(
                        agent_name=agent_name,
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
                        agent_name=agent_name,
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
        chain_data = ApiClient.get_chain(chain_name=chain_name)
        if chain_data == {}:
            return f"Chain `{chain_name}` not found."
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        last_response = ""
        for step_data in chain_data["steps"]:
            if int(step_data["step"]) >= int(from_step):
                if "prompt" in step_data and "step" in step_data:
                    step = {}
                    step["agent_name"] = (
                        agent_override
                        if agent_override != ""
                        else step_data["agent_name"]
                    )
                    step["prompt_type"] = step_data["prompt_type"]
                    step["prompt"] = step_data["prompt"]
                    logging.info(
                        f"Running step {step_data['step']} with agent {step['agent_name']}."
                    )

                    # Get the chain step based on the step number
                    chain_step = self.get_step(chain_name, step_data["step"])

                    step_response = await self.run_chain_step(
                        step=step_data,
                        chain_name=chain_name,
                        user_input=user_input,
                        agent_override=agent_override,
                    )  # Get the response of the current step.
                    step["response"] = step_response
                    last_response = step_response
                    responses[step_data["step"]] = step  # Store the response.
                    logging.info(f"Response: {step_response}")
                    # Write the response to the json file.
                    response_content = {
                        "chain_step_id": chain_step.id,
                        "content": step_response,
                    }
                    chain_step_response = ChainStepResponse(**response_content)
                    session.add(chain_step_response)
                    session.commit()

        if all_responses:
            return responses
        else:
            # Return only the last response in the chain.
            return last_response
