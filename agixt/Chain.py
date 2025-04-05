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
    TaskCategory,
    TaskItem,
)
from Globals import getenv, DEFAULT_USER
from Prompts import Prompts
from Extensions import Extensions
from MagicalAuth import get_user_id
import logging
import asyncio

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Chain:
    def __init__(self, user=DEFAULT_USER):
        self.user = user
        self.user_id = get_user_id(self.user)

    def get_chain(self, chain_name):
        session = get_session()
        chain_name = chain_name.replace("%20", " ")
        user_data = session.query(User).filter(User.id == self.user_id).first()
        chain_db = (
            session.query(ChainDB)
            .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db is None:
            chain_db = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
        if chain_db is None:
            session.close()
            return []
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
            "id": chain_db.id,
            "chain_name": chain_db.name,
            "description": chain_db.description if chain_db.description else "",
            "steps": steps,
        }
        session.close()
        return chain_data

    def get_global_chains(self):
        session = get_session()
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_chains = (
            session.query(ChainDB).filter(ChainDB.user_id == user_data.id).all()
        )
        chains = session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        chain_list = []
        for chain in global_chains:
            if chain in chains:
                continue
            chain_list.append(
                {
                    "name": chain.name,
                    "description": chain.description,
                    "steps": chain.steps,
                    "runs": chain.runs,
                }
            )
        session.close()
        return chain_list

    def get_user_chains(self):
        session = get_session()
        chains = session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        chain_list = []
        for chain in chains:
            steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id == chain.id)
                .order_by(ChainStep.step_number)
                .all()
            )
            chain_steps = []
            for step in steps:
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
                    .join(
                        ChainStepArgument,
                        ChainStepArgument.argument_id == Argument.id,
                    )
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
                chain_steps.append(step_data)
            chain_list.append(
                {
                    "id": str(chain.id),
                    "name": chain.name,
                    "description": chain.description,
                    "steps": chain_steps,
                    "runs": chain.runs,
                }
            )
        session.close()
        return chain_list

    def get_chains(self):
        session = get_session()
        """
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        global_chains = (
            session.query(ChainDB).filter(ChainDB.user_id == user_data.id).all()
        )
        """
        chains = session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        chain_list = []
        for chain in chains:
            chain_list.append(chain.name)
        # for chain in global_chains:
        # chain_list.append(chain.name)
        session.close()
        return chain_list

    def add_chain(self, chain_name):
        session = get_session()
        chain = ChainDB(name=chain_name, user_id=self.user_id)
        session.add(chain)
        session.commit()
        session.close()

    def rename_chain(self, chain_name, new_name):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
            chain.name = new_name
            session.commit()
        session.close()

    def add_chain_step(
        self,
        chain_name: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if not chain:
            # Check if it is a global
            chain = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id
                    == session.query(User)
                    .filter(User.email == DEFAULT_USER)
                    .first()
                    .id,
                )
                .first()
            )
        if not chain:
            logging.error(f"Chain {chain_name} not found.")
            return
        agent = (
            session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
            .first()
        )
        if not agent:
            agent = (
                session.query(Agent)
                .filter(
                    Agent.name == agent_name,
                    Agent.user_id
                    == session.query(User)
                    .filter(User.email == DEFAULT_USER)
                    .first()
                    .id,
                )
                .first()
            )
        if "prompt_category" in prompt:
            prompt_category = prompt["prompt_category"]
        else:
            prompt_category = "Default"
        argument_key = None
        if prompt_type.lower() == "prompt":
            argument_key = "prompt_name"
            target = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt["prompt_name"],
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
            )
            if not target:
                target = (
                    session.query(Prompt)
                    .filter(
                        Prompt.name == prompt["prompt_name"],
                        Prompt.user_id
                        == session.query(User)
                        .filter(User.email == DEFAULT_USER)
                        .first()
                        .id,
                    )
                    .first()
                )
            target_type = "prompt"
        elif prompt_type.lower() == "chain":
            argument_key = "chain_name"
            if argument_key not in prompt:
                argument_key = "chain"
            target = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == prompt[argument_key],
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
            if not target:
                target = (
                    session.query(ChainDB)
                    .filter(
                        ChainDB.name == prompt[argument_key],
                        ChainDB.user_id
                        == session.query(User)
                        .filter(User.email == DEFAULT_USER)
                        .first()
                        .id,
                    )
                    .first()
                )
            target_type = "chain"
        elif prompt_type.lower() == "command":
            argument_key = "command_name"
            target = (
                session.query(Command)
                .filter(Command.name == prompt["command_name"])
                .first()
            )
            target_type = "command"
        else:
            logging.warning(
                f"Invalid prompt {prompt} with prompt type {prompt_type}. Using default prompt."
            )
            prompt["prompt_name"] = "User Input"
            prompt["prompt_category"] = "Default"
            prompt_type = "Prompt"
            prompt["user_input"] = (
                prompt["input"]
                if "input" in prompt
                else prompt["user_input"] if "user_input" in prompt else ""
            )
            if "input" in prompt:
                del prompt["input"]
            argument_key = "prompt_name"
            target = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt["prompt_name"],
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
            )
            target_type = "prompt"
        target_id = None
        if not target:
            logging.error(
                f"Target {prompt[argument_key]} not found. Using default prompt."
            )
            logging.info(f"Prompt: {prompt}")
            logging.info(f"Prompt Type: {prompt_type}")
            logging.info(f"Argument Key: {argument_key}")
        else:
            target_id = target.id
        argument_value = prompt[argument_key]
        prompt_arguments = prompt.copy()
        if argument_key in prompt_arguments:
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
                chain_step_id=str(chain_step.id),
                argument_id=str(argument.id),
                value=str(argument_value),
            )
            session.add(chain_step_argument)
            session.commit()
        session.close()

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        logging.info(f"Updating step {step_number} in chain {chain_name}")
        logging.info(f"Agent: {agent_name}")
        logging.info(f"Prompt Type: {prompt_type}")
        logging.info(f"Prompt: {prompt}")
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if not chain:
            logging.error(f"Chain '{chain_name}' not found for user.")
            session.close()
            return  # Or raise an exception

        chain_step = (
            session.query(ChainStep)
            .filter(
                ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
            )
            .first()
        )
        if not chain_step:
            logging.error(f"Step {step_number} not found in chain '{chain_name}'.")
            session.close()
            return  # Or raise an exception

        agent = (
            session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
            .first()
        )
        default_user = session.query(User).filter(User.email == DEFAULT_USER).first()
        # Fallback to default user agent if not found for current user
        if not agent:
            if default_user:
                agent = (
                    session.query(Agent)
                    .filter(Agent.name == agent_name, Agent.user_id == default_user.id)
                    .first()
                )
        if not agent:
            logging.error(f"Agent '{agent_name}' not found for user or default user.")
            session.close()
            return  # Or raise an exception

        agent_id = agent.id
        target_chain_id = None
        target_command_id = None
        target_prompt_id = None
        prompt_value_to_store = (
            None  # Variable to hold the name to store in chain_step.prompt
        )

        # Make a copy to modify for arguments
        prompt_args = prompt.copy()

        if prompt_type == "Command":
            command_name = prompt.get("command_name")
            if command_name:
                prompt_value_to_store = command_name  # Store command name
                if "command_name" in prompt_args:
                    del prompt_args["command_name"]
                command = (
                    session.query(Command).filter(Command.name == command_name).first()
                )
                if command:
                    target_command_id = command.id
                else:
                    logging.warning(
                        f"Command '{command_name}' not found. Step target might be invalid."
                    )
            else:
                # If command_name is missing but type is Command, fallback or raise error
                logging.warning(
                    "Command type selected but 'command_name' is missing. Defaulting to Prompt."
                )
                prompt_type = "Prompt"  # Fallback to prompt

        elif prompt_type == "Chain":
            chain_key = "chain_name" if "chain_name" in prompt else "chain"
            chain_val = prompt.get(chain_key)
            if chain_val:
                prompt_value_to_store = chain_val  # Store chain name
                if "chain" in prompt_args:
                    del prompt_args["chain"]
                if "chain_name" in prompt_args:
                    del prompt_args["chain_name"]
                chain_obj = (
                    session.query(ChainDB)
                    .filter(ChainDB.name == chain_val, ChainDB.user_id == self.user_id)
                    .first()
                )
                # Try default user if not found
                if not chain_obj and default_user:
                    chain_obj = (
                        session.query(ChainDB)
                        .filter(
                            ChainDB.name == chain_val,
                            ChainDB.user_id == default_user.id,
                        )
                        .first()
                    )
                if chain_obj:
                    target_chain_id = chain_obj.id
                else:
                    logging.warning(
                        f"Chain '{chain_val}' not found. Step target might be invalid."
                    )
            else:
                # Fallback or raise error if chain name missing
                logging.warning(
                    f"Chain type selected but '{chain_key}' is missing. Defaulting to Prompt."
                )
                prompt_type = "Prompt"  # Fallback

        # Handle Prompt type (or fallback)
        if prompt_type == "Prompt":
            prompt_name = prompt.get("prompt_name", "Think About It")
            prompt_value_to_store = prompt_name  # Store prompt name
            prompt_category = prompt.get("prompt_category", "Default")
            if "prompt_name" in prompt_args:
                del prompt_args["prompt_name"]
            if "prompt_category" in prompt_args:
                del prompt_args["prompt_category"]
            prompt_obj = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt_name,
                    Prompt.prompt_category.has(name=prompt_category),
                    Prompt.user_id == self.user_id,
                )
                .first()
            )
            # Try default user if not found
            if not prompt_obj and default_user:
                prompt_obj = (
                    session.query(Prompt)
                    .filter(
                        Prompt.name == prompt_name,
                        Prompt.prompt_category.has(name=prompt_category),
                        Prompt.user_id == default_user.id,
                    )
                    .first()
                )
            if prompt_obj:
                target_prompt_id = prompt_obj.id
            else:
                logging.warning(
                    f"Prompt '{prompt_name}' in category '{prompt_category}' not found. Step target might be invalid."
                )

        # Ensure prompt_value_to_store has a value before updating
        if prompt_value_to_store is None:
            logging.error(
                "Could not determine the value to store in chain_step.prompt."
            )
            # Decide how to handle this: maybe default, maybe skip update, maybe raise error
            # For now, let's keep the old value if we can't determine the new one
            prompt_value_to_store = chain_step.prompt

        # Update ChainStep object
        chain_step.agent_id = agent_id
        chain_step.prompt_type = prompt_type
        chain_step.prompt = prompt_value_to_store
        chain_step.target_chain_id = target_chain_id
        chain_step.target_command_id = target_command_id
        chain_step.target_prompt_id = target_prompt_id

        if prompt_type == "Command" and target_command_id is None:
            command_name = prompt.get("command_name")
            if command_name:
                command = (
                    session.query(Command).filter(Command.name == command_name).first()
                )
                if command:
                    chain_step.target_command_id = command.id  # Re-set it here

        session.commit()  # Commit the primary ChainStep updates first

        # Clean up any invalid argument keys before saving
        keys_to_remove = [
            "prompt_name",
            "command_name",
            "chain_name",
            "chain",
            "prompt_category",
        ]
        cleaned_prompt_args = {
            k: v for k, v in prompt_args.items() if k not in keys_to_remove
        }

        # Update the arguments for the step
        # Delete existing arguments first
        session.query(ChainStepArgument).filter(
            ChainStepArgument.chain_step_id == str(chain_step.id)
        ).delete()
        session.commit()  # Commit deletion

        # Add new arguments
        for (
            argument_name,
            argument_value,
        ) in cleaned_prompt_args.items():  # Use cleaned args
            argument = (
                session.query(Argument).filter(Argument.name == argument_name).first()
            )
            if argument:
                chain_step_argument = ChainStepArgument(
                    chain_step_id=str(chain_step.id),
                    argument_id=str(argument.id),
                    value=str(argument_value),  # Ensure value is string
                )
                session.add(chain_step_argument)
            else:
                logging.warning(
                    f"Argument '{argument_name}' not found in Argument table. Skipping."
                )
        session.commit()  # Commit new arguments
        session.close()

    def delete_step(self, chain_name, step_number):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
            chain_step = (
                session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain.id, ChainStep.step_number == step_number
                )
                .first()
            )
            if chain_step:
                # Store the deleted step's number before removing it
                deleted_step_number = chain_step.step_number

                # Delete the chain step
                session.delete(chain_step)
                session.commit()

                # Update all step numbers greater than the deleted step's number
                # Decrement them by 1 to close the gap
                session.query(ChainStep).filter(
                    ChainStep.chain_id == chain.id,
                    ChainStep.step_number > deleted_step_number,
                ).update(
                    {"step_number": ChainStep.step_number - 1},
                    synchronize_session=False,
                )
                session.commit()

                logging.info(
                    f"Deleted step {deleted_step_number} from chain '{chain_name}' and reordered remaining steps"
                )
            else:
                logging.info(
                    f"No step found with number {step_number} in chain '{chain_name}'"
                )
        else:
            logging.info(f"No chain found with name '{chain_name}'")
        session.close()

    def delete_chain(self, chain_name):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        session.delete(chain)
        session.commit()
        session.close()

    def get_steps(self, chain_name):
        session = get_session()
        chain_name = chain_name.replace("%20", " ")
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        chain_db = (
            session.query(ChainDB)
            .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db is None:
            chain_db = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == chain_name,
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
        if chain_db is None:
            session.close()
            return []
        chain_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        session.close()
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
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
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
        session.close()

    def get_step_response(self, chain_name, chain_run_id=None, step_number="all"):
        if chain_run_id is None:
            chain_run_id = self.get_last_chain_run_id(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        session = get_session()
        if step_number == "all":
            chain_steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id == chain_data["id"])
                .order_by(ChainStep.step_number)
                .all()
            )

            responses = {}
            for step in chain_steps:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(
                        ChainStepResponse.chain_step_id == step.id,
                        ChainStepResponse.chain_run_id == chain_run_id,
                    )
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                responses[str(step.step_number)] = step_responses
            session.close()
            return responses
        else:
            step_number = int(step_number)
            chain_step = (
                session.query(ChainStep)
                .filter(
                    ChainStep.chain_id == chain_data["id"],
                    ChainStep.step_number == step_number,
                )
                .first()
            )

            if chain_step:
                chain_step_responses = (
                    session.query(ChainStepResponse)
                    .filter(
                        ChainStepResponse.chain_step_id == chain_step.id,
                        ChainStepResponse.chain_run_id == chain_run_id,
                    )
                    .order_by(ChainStepResponse.timestamp)
                    .all()
                )
                step_responses = [response.content for response in chain_step_responses]
                session.close()
                return step_responses
            else:
                session.close()
                return None

    def get_chain_responses(self, chain_name):
        chain_steps = self.get_steps(chain_name=chain_name)
        responses = {}
        session = get_session()
        for step in chain_steps:
            chain_step_responses = (
                session.query(ChainStepResponse)
                .filter(ChainStepResponse.chain_step_id == step.id)
                .order_by(ChainStepResponse.timestamp)
                .all()
            )
            step_responses = [response.content for response in chain_step_responses]
            responses[str(step.step_number)] = step_responses
        session.close()
        return responses

    def update_description(self, chain_name, description):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
            chain.description = description
            session.commit()
        session.close()
        return chain

    def import_chain(self, chain_name: str, steps: dict):
        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
            # Check if the chain has steps
            chain_steps = (
                session.query(ChainStep).filter(ChainStep.chain_id == chain.id).all()
            )
            if chain_steps:
                logging.error(f"Chain {chain_name} already exists.")
                session.close()
                return None
        else:
            chain = ChainDB(name=chain_name, user_id=self.user_id)
            session.add(chain)
            session.commit()
        steps = steps["steps"] if "steps" in steps else steps
        for step_data in steps:
            agent_name = step_data["agent_name"]
            agent = (
                session.query(Agent)
                .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
                .first()
            )
            if not agent:
                # Use the first agent in the database
                agent = (
                    session.query(Agent).filter(Agent.user_id == self.user_id).first()
                )
            prompt = step_data["prompt"]
            if "prompt_type" not in step_data:
                step_data["prompt_type"] = "prompt"
            prompt_type = step_data["prompt_type"].lower()
            target_id = None
            if prompt_type == "prompt":
                argument_key = "prompt_name"
                prompt_category = prompt.get("prompt_category", "Default")
                target = (
                    session.query(Prompt)
                    .filter(
                        Prompt.name == prompt[argument_key],
                        Prompt.user_id == self.user_id,
                        Prompt.prompt_category.has(name=prompt_category),
                    )
                    .first()
                )
                if target:
                    target_id = target.id
            elif prompt_type == "chain":
                argument_key = "chain_name"
                if "chain" in prompt:
                    argument_key = "chain"
                target = (
                    session.query(ChainDB)
                    .filter(
                        ChainDB.name == prompt[argument_key],
                        ChainDB.user_id == self.user_id,
                    )
                    .first()
                )
                if target:
                    target_id = target.id
            elif prompt_type == "command":
                argument_key = "command_name"
                target = (
                    session.query(Command)
                    .filter(Command.name == prompt[argument_key])
                    .first()
                )
                if target:
                    target_id = target.id
            else:
                # Handle the case where the prompt_type is not recognized
                logging.error(f"Unrecognized prompt_type: {prompt_type}")
                continue

            if target_id is None:
                # Handle the case where the target is not found
                logging.error(
                    f"Target not found for {prompt_type}: {prompt[argument_key]}"
                )
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
                target_chain_id=target_id if prompt_type == "chain" else None,
                target_command_id=target_id if prompt_type == "command" else None,
                target_prompt_id=target_id if prompt_type == "prompt" else None,
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
                    argument = Argument(name=argument_name)
                    session.add(argument)
                    session.commit()

                chain_step_argument = ChainStepArgument(
                    chain_step_id=chain_step.id,
                    argument_id=argument.id,
                    value=argument_value,
                )
                session.add(chain_step_argument)
                session.commit()
        session.close()
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
        if chain_step and response:
            session = get_session()
            existing_response = (
                session.query(ChainStepResponse)
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
                    session.commit()
                elif isinstance(existing_response.content, list) and isinstance(
                    response, list
                ):
                    existing_response.content.extend(response)
                    session.commit()
                else:
                    existing_response.content = response
                    session.commit()
            else:
                chain_step_response = ChainStepResponse(
                    chain_step_id=chain_step.id,
                    chain_run_id=chain_run_id,
                    content=response,
                )
                session.add(chain_step_response)
                session.commit()
            session.close()

    async def get_chain_run_id(self, chain_name):
        session = get_session()
        chain_run = ChainRun(
            chain_id=self.get_chain(chain_name=chain_name)["id"],
            user_id=self.user_id,
        )
        session.add(chain_run)
        session.commit()
        chain_id = chain_run.id
        session.close()
        return chain_id

    async def get_last_chain_run_id(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        session = get_session()
        chain_run = (
            session.query(ChainRun)
            .filter(ChainRun.chain_id == chain_data["id"])
            .order_by(ChainRun.timestamp.desc())
            .first()
        )
        if chain_run:
            chain_run_id = chain_run.id
            session.close()
            return chain_run_id
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
        logging.info(f"Chain Data: {chain_data}")
        try:
            steps = chain_data["steps"]
        except:
            return []
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

    def new_task(
        self,
        conversation_id,
        chain_name,
        task_category,
        task_description,
        estimated_hours,
    ):
        session = get_session()
        task_category = (
            session.query(TaskCategory)
            .filter(
                TaskCategory.name == task_category, TaskCategory.user_id == self.user_id
            )
            .first()
        )
        if not task_category:
            task_category = TaskCategory(name=task_category, user_id=self.user_id)
            session.add(task_category)
            session.commit()
        task = TaskItem(
            user_id=self.user_id,
            category_id=task_category.id,
            title=chain_name,
            description=task_description,
            estimated_hours=estimated_hours,
            memory_collection=str(conversation_id),
        )
        session.add(task)
        session.commit()
        task_id = task.id
        session.close()
        return task_id
