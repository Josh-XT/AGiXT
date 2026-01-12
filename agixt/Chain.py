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
    ServerChain,
    ServerChainStep,
    ServerChainStepArgument,
    CompanyChain,
    CompanyChainStep,
    CompanyChainStepArgument,
    UserChainOverride,
)
from Globals import getenv, DEFAULT_USER
from Prompts import Prompts
from Extensions import Extensions
from MagicalAuth import get_user_id, get_user_company_id
import logging
import asyncio
from WebhookManager import webhook_emitter

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Chain:
    def __init__(self, user=DEFAULT_USER):
        self.user = user
        self.user_id = get_user_id(self.user)
        self.company_id = get_user_company_id(self.user)

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

        if not chain_steps:
            chain_data = {
                "id": chain_db.id,
                "chain_name": chain_db.name,
                "description": chain_db.description if chain_db.description else "",
                "steps": [],
            }
            session.close()
            return chain_data

        # Batch load all related data to avoid N+1 queries
        agent_ids = {step.agent_id for step in chain_steps if step.agent_id}
        chain_ids = {
            step.target_chain_id for step in chain_steps if step.target_chain_id
        }
        command_ids = {
            step.target_command_id for step in chain_steps if step.target_command_id
        }
        prompt_ids = {
            step.target_prompt_id for step in chain_steps if step.target_prompt_id
        }
        step_ids = {step.id for step in chain_steps}

        # Batch queries
        agents_map = {}
        if agent_ids:
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agents_map = {a.id: a.name for a in agents}

        chains_map = {}
        if chain_ids:
            chains = session.query(ChainDB).filter(ChainDB.id.in_(chain_ids)).all()
            chains_map = {c.id: c.name for c in chains}

        commands_map = {}
        if command_ids:
            commands = session.query(Command).filter(Command.id.in_(command_ids)).all()
            commands_map = {c.id: c.name for c in commands}

        prompts_map = {}
        if prompt_ids:
            prompts = session.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
            prompts_map = {p.id: p.name for p in prompts}

        # Batch load all arguments for all steps
        step_arguments = {}
        if step_ids:
            all_args = (
                session.query(Argument, ChainStepArgument)
                .join(ChainStepArgument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id.in_(step_ids))
                .all()
            )
            for argument, chain_step_argument in all_args:
                if chain_step_argument.chain_step_id not in step_arguments:
                    step_arguments[chain_step_argument.chain_step_id] = {}
                step_arguments[chain_step_argument.chain_step_id][
                    argument.name
                ] = chain_step_argument.value

        steps = []
        for step in chain_steps:
            agent_name = agents_map.get(step.agent_id, "Unknown")
            prompt = {}
            if step.target_chain_id:
                prompt["chain_name"] = chains_map.get(step.target_chain_id, "Unknown")
            elif step.target_command_id:
                prompt["command_name"] = commands_map.get(
                    step.target_command_id, "Unknown"
                )
            elif step.target_prompt_id:
                prompt["prompt_name"] = prompts_map.get(
                    step.target_prompt_id, "Unknown"
                )

            # Get pre-loaded arguments
            prompt_args = step_arguments.get(step.id, {})
            prompt.update(prompt_args)

            step_data = {
                "step": step.step_number,
                "agent_name": agent_name,
                "prompt_type": step.prompt_type or "",
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

        if not chains:
            session.close()
            return []

        # Get all chain IDs for batch loading
        chain_ids = [chain.id for chain in chains]

        # Batch load all steps for all chains
        all_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id.in_(chain_ids))
            .order_by(ChainStep.step_number)
            .all()
        )

        # Collect IDs for batch loading
        agent_ids = {step.agent_id for step in all_steps if step.agent_id}
        target_chain_ids = {
            step.target_chain_id for step in all_steps if step.target_chain_id
        }
        command_ids = {
            step.target_command_id for step in all_steps if step.target_command_id
        }
        prompt_ids = {
            step.target_prompt_id for step in all_steps if step.target_prompt_id
        }
        step_ids = {step.id for step in all_steps}

        # Batch load all related entities
        agents_map = {}
        if agent_ids:
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agents_map = {a.id: a.name for a in agents}

        chains_map = {}
        if target_chain_ids:
            target_chains = (
                session.query(ChainDB).filter(ChainDB.id.in_(target_chain_ids)).all()
            )
            chains_map = {c.id: c.name for c in target_chains}

        commands_map = {}
        if command_ids:
            commands = session.query(Command).filter(Command.id.in_(command_ids)).all()
            commands_map = {c.id: c.name for c in commands}

        prompts_map = {}
        if prompt_ids:
            prompts = session.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
            prompts_map = {p.id: p.name for p in prompts}

        # Batch load all arguments
        step_arguments = {}
        if step_ids:
            all_args = (
                session.query(Argument, ChainStepArgument)
                .join(ChainStepArgument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id.in_(step_ids))
                .all()
            )
            for argument, chain_step_argument in all_args:
                if chain_step_argument.chain_step_id not in step_arguments:
                    step_arguments[chain_step_argument.chain_step_id] = {}
                step_arguments[chain_step_argument.chain_step_id][
                    argument.name
                ] = chain_step_argument.value

        # Group steps by chain_id
        steps_by_chain = {}
        for step in all_steps:
            if step.chain_id not in steps_by_chain:
                steps_by_chain[step.chain_id] = []
            steps_by_chain[step.chain_id].append(step)

        # Build chain list
        chain_list = []
        for chain in chains:
            chain_steps = []
            for step in steps_by_chain.get(chain.id, []):
                agent_name = agents_map.get(step.agent_id, "Unknown")
                prompt = {}
                if step.target_chain_id:
                    prompt["chain_name"] = chains_map.get(
                        step.target_chain_id, "Unknown"
                    )
                elif step.target_command_id:
                    prompt["command_name"] = commands_map.get(
                        step.target_command_id, "Unknown"
                    )
                elif step.target_prompt_id:
                    prompt["prompt_name"] = prompts_map.get(
                        step.target_prompt_id, "Unknown"
                    )

                prompt_args = step_arguments.get(step.id, {})
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
        """
        Get all chains available to the user with tiered resolution.
        Includes server chains, company chains, and user chains.
        User chains override company, which override server chains of the same name.
        """
        session = get_session()
        chains_set = set()  # Use set for deduplication by name

        # 1. Server-level chains (non-internal only)
        server_chains = (
            session.query(ServerChain).filter(ServerChain.is_internal == False).all()
        )
        for chain in server_chains:
            chains_set.add(chain.name)

        # 2. Company-level chains (add or override server)
        if self.company_id:
            company_chains = (
                session.query(CompanyChain)
                .filter(CompanyChain.company_id == self.company_id)
                .all()
            )
            for chain in company_chains:
                chains_set.add(chain.name)

        # 3. User-level chains (add or override company and server)
        user_chains = (
            session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        )
        for chain in user_chains:
            chains_set.add(chain.name)

        session.close()
        return list(chains_set)

    def add_chain(self, chain_name, description=""):
        session = get_session()
        # Check if a chain with this name already exists for this user
        existing_chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if existing_chain:
            session.close()
            raise Exception(f"A chain named '{chain_name}' already exists")

        chain = ChainDB(name=chain_name, user_id=self.user_id, description=description)
        session.add(chain)
        session.commit()
        chain_id = str(chain.id)

        # Emit webhook event
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="chain.created",
                user_id=self.user,
                company_id=str(self.company_id) if self.company_id else None,
                data={
                    "chain_id": chain_id,
                    "chain_name": chain_name,
                    "description": description,
                },
            )
        )

        session.close()
        return chain_id

    def rename_chain(self, chain_name, new_name):
        from DB import Extension
        from Agent import invalidate_commands_cache

        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )
        if chain:
            old_name = chain.name
            chain.name = new_name

            # Update the associated Command entry if it exists
            # Commands for chains are stored in the "Custom Automation" extension
            extension = (
                session.query(Extension).filter_by(name="Custom Automation").first()
            )
            if extension:
                command = (
                    session.query(Command)
                    .filter_by(name=old_name, extension_id=extension.id)
                    .first()
                )
                if command:
                    command.name = new_name

            session.commit()
            # Invalidate the commands cache since we renamed a command
            invalidate_commands_cache()

            # Emit webhook event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="chain.updated",
                    user_id=self.user,
                    company_id=str(self.company_id) if self.company_id else None,
                    data={
                        "chain_id": str(chain.id),
                        "old_name": old_name,
                        "new_name": new_name,
                    },
                )
            )
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
        session.close()

    def delete_chain(self, chain_name):
        from DB import Extension, AgentCommand
        from Agent import invalidate_commands_cache

        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(ChainDB.name == chain_name, ChainDB.user_id == self.user_id)
            .first()
        )

        if chain:
            chain_id = str(chain.id)

            # Delete the associated Command entry if it exists
            extension = (
                session.query(Extension).filter_by(name="Custom Automation").first()
            )
            if extension:
                command = (
                    session.query(Command)
                    .filter_by(name=chain_name, extension_id=extension.id)
                    .first()
                )
                if command:
                    # Delete any AgentCommand entries for this command
                    session.query(AgentCommand).filter_by(
                        command_id=command.id
                    ).delete()
                    session.delete(command)

            session.delete(chain)
            session.commit()
            # Invalidate the commands cache
            invalidate_commands_cache()

            # Emit webhook event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="chain.deleted",
                    user_id=self.user,
                    company_id=str(self.company_id) if self.company_id else None,
                    data={
                        "chain_id": chain_id,
                        "chain_name": chain_name,
                    },
                )
            )

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

            # Emit webhook event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="chain.updated",
                    user_id=self.user,
                    company_id=str(self.company_id) if self.company_id else None,
                    data={
                        "chain_id": str(chain.id),
                        "chain_name": chain_name,
                        "description": description,
                    },
                )
            )
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

            # Emit webhook event for chain step completion
            await webhook_emitter.emit_event(
                event_type="chain.step.completed",
                user_id=self.user,
                company_id=str(self.company_id) if self.company_id else None,
                data={
                    "chain_name": chain_name,
                    "chain_run_id": str(chain_run_id),
                    "step_number": step_number,
                    "response": (
                        response
                        if isinstance(response, (str, int, float, bool))
                        else str(response)[:500]
                    ),
                },
            )

            session.close()

    async def get_chain_run_id(self, chain_name):
        session = get_session()
        chain_data = self.get_chain(chain_name=chain_name)
        chain_run = ChainRun(
            chain_id=chain_data["id"],
            user_id=self.user_id,
        )
        session.add(chain_run)
        session.commit()
        chain_run_id = chain_run.id

        # Emit webhook event for chain execution started
        await webhook_emitter.emit_event(
            event_type="chain.execution.started",
            user_id=self.user,
            company_id=str(self.company_id) if self.company_id else None,
            data={
                "chain_id": str(chain_data["id"]),
                "chain_name": chain_name,
                "chain_run_id": str(chain_run_id),
            },
        )

        session.close()
        return chain_run_id

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

    def get_chain_by_id(self, chain_id):
        """Get chain details by ID"""
        session = get_session()
        chain_db = (
            session.query(ChainDB)
            .filter(
                ChainDB.id == chain_id,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )

        if chain_db is None:
            # Try global chains
            user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
            chain_db = (
                session.query(ChainDB)
                .filter(
                    ChainDB.id == chain_id,
                    ChainDB.user_id == user_data.id,
                )
                .first()
            )

        if chain_db is None:
            session.close()
            return None

        steps = (
            session.query(ChainStep)
            .join(Agent, ChainStep.agent_id == Agent.id)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )
        chain_steps = []
        for step in steps:
            # Get the agent name from the joined Agent table
            agent = session.query(Agent).filter(Agent.id == step.agent_id).first()
            agent_name = agent.name if agent else ""

            # Build prompt object similar to get_chain() method
            prompt = {}
            if step.target_chain_id:
                chain_obj = session.query(ChainDB).get(step.target_chain_id)
                if chain_obj:
                    prompt["chain_name"] = chain_obj.name
            elif step.target_command_id:
                command_obj = session.query(Command).get(step.target_command_id)
                if command_obj:
                    prompt["command_name"] = command_obj.name
            elif step.target_prompt_id:
                prompt_obj = session.query(Prompt).get(step.target_prompt_id)
                if prompt_obj:
                    prompt["prompt_name"] = prompt_obj.name

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
                "prompt_type": step.prompt_type or "",
                "prompt": prompt,
            }
            chain_steps.append(step_data)

        result = {
            "id": str(chain_db.id),
            "name": chain_db.name,
            "description": chain_db.description,
            "steps": chain_steps,
        }
        session.close()
        return result

    def delete_chain_by_id(self, chain_id):
        """Delete chain by ID"""
        from DB import Extension, AgentCommand
        from Agent import invalidate_commands_cache

        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(
                ChainDB.id == chain_id,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )

        if not chain:
            session.close()
            raise Exception("Chain not found")

        chain_name = chain.name

        # Delete the associated Command entry if it exists
        extension = session.query(Extension).filter_by(name="Custom Automation").first()
        if extension:
            command = (
                session.query(Command)
                .filter_by(name=chain_name, extension_id=extension.id)
                .first()
            )
            if command:
                # Delete any AgentCommand entries for this command
                session.query(AgentCommand).filter_by(command_id=command.id).delete()
                session.delete(command)

        session.delete(chain)
        session.commit()
        # Invalidate the commands cache
        invalidate_commands_cache()

        # Emit webhook event
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="chain.deleted",
                user_id=self.user,
                company_id=str(self.company_id) if self.company_id else None,
                data={
                    "chain_id": str(chain_id),
                    "chain_name": chain_name,
                },
            )
        )

        session.close()

    def update_chain_by_id(self, chain_id, chain_name, description=""):
        """Update chain by ID"""
        from DB import Extension
        from Agent import invalidate_commands_cache

        session = get_session()
        chain = (
            session.query(ChainDB)
            .filter(
                ChainDB.id == chain_id,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )

        if not chain:
            session.close()
            raise Exception("Chain not found")

        old_name = chain.name
        old_description = chain.description
        chain.name = chain_name
        chain.description = description

        # Update the associated Command entry if it exists and the name changed
        if old_name != chain_name:
            extension = (
                session.query(Extension).filter_by(name="Custom Automation").first()
            )
            if extension:
                command = (
                    session.query(Command)
                    .filter_by(name=old_name, extension_id=extension.id)
                    .first()
                )
                if command:
                    command.name = chain_name

        session.commit()
        # Invalidate the commands cache if name or description changed
        # (description is dynamically generated from chain data)
        if old_name != chain_name or old_description != description:
            invalidate_commands_cache()

        # Emit webhook event
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="chain.updated",
                user_id=self.user,
                company_id=str(self.company_id) if self.company_id else None,
                data={
                    "chain_id": str(chain_id),
                    "old_name": old_name,
                    "new_name": chain_name,
                    "description": description,
                },
            )
        )

        session.close()

    def get_chain_args_by_id(self, chain_id):
        """Get chain arguments by ID"""
        session = get_session()
        chain_db = (
            session.query(ChainDB)
            .filter(
                ChainDB.id == chain_id,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )

        if chain_db is None:
            # Try global chains
            user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
            chain_db = (
                session.query(ChainDB)
                .filter(
                    ChainDB.id == chain_id,
                    ChainDB.user_id == user_data.id,
                )
                .first()
            )

        if chain_db is None:
            session.close()
            return []

        steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == chain_db.id)
            .order_by(ChainStep.step_number)
            .all()
        )

        chain_args = []
        for step in steps:
            # Get step arguments with joined Argument to get the name
            step_args = (
                session.query(ChainStepArgument, Argument)
                .join(Argument, ChainStepArgument.argument_id == Argument.id)
                .filter(ChainStepArgument.chain_step_id == step.id)
                .all()
            )
            for step_arg, arg in step_args:
                if arg.name not in chain_args:
                    chain_args.append(arg.name)

        session.close()
        return chain_args

    # =========================================================================
    # Tiered Chain Methods - Server/Company/User hierarchy
    # =========================================================================

    def _get_chain_steps_data(self, session, chain_db, chain_type="user"):
        """Helper to extract step data from a chain (user/server/company)."""
        if chain_type == "server":
            steps = (
                session.query(ServerChainStep)
                .filter(ServerChainStep.chain_id == chain_db.id)
                .order_by(ServerChainStep.step_number)
                .all()
            )
            step_arg_model = ServerChainStepArgument
        elif chain_type == "company":
            steps = (
                session.query(CompanyChainStep)
                .filter(CompanyChainStep.chain_id == chain_db.id)
                .order_by(CompanyChainStep.step_number)
                .all()
            )
            step_arg_model = CompanyChainStepArgument
        else:
            steps = (
                session.query(ChainStep)
                .filter(ChainStep.chain_id == chain_db.id)
                .order_by(ChainStep.step_number)
                .all()
            )
            step_arg_model = ChainStepArgument

        if not steps:
            return []

        # Batch load all related data to avoid N+1 queries
        agent_ids = {step.agent_id for step in steps if step.agent_id}
        chain_ids = {step.target_chain_id for step in steps if step.target_chain_id}
        command_ids = {
            step.target_command_id for step in steps if step.target_command_id
        }
        prompt_ids = {step.target_prompt_id for step in steps if step.target_prompt_id}
        step_ids = {step.id for step in steps}

        # Batch queries
        agents_map = {}
        if agent_ids:
            agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            agents_map = {a.id: a.name for a in agents}

        chains_map = {}
        if chain_ids:
            chains = session.query(ChainDB).filter(ChainDB.id.in_(chain_ids)).all()
            chains_map = {c.id: c.name for c in chains}

        commands_map = {}
        if command_ids:
            commands = session.query(Command).filter(Command.id.in_(command_ids)).all()
            commands_map = {c.id: c.name for c in commands}

        prompts_map = {}
        if prompt_ids:
            prompts = session.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
            prompts_map = {p.id: p.name for p in prompts}

        # Batch load all arguments for all steps
        step_arguments = {}
        if step_ids:
            all_args = (
                session.query(Argument, step_arg_model)
                .join(step_arg_model, step_arg_model.argument_id == Argument.id)
                .filter(step_arg_model.chain_step_id.in_(step_ids))
                .all()
            )
            for argument, step_argument in all_args:
                if step_argument.chain_step_id not in step_arguments:
                    step_arguments[step_argument.chain_step_id] = {}
                step_arguments[step_argument.chain_step_id][
                    argument.name
                ] = step_argument.value

        chain_steps = []
        for step in steps:
            agent_name = agents_map.get(step.agent_id, "")

            prompt = {}
            if step.target_chain_id:
                chain_name = chains_map.get(step.target_chain_id)
                if chain_name:
                    prompt["chain_name"] = chain_name
            elif step.target_command_id:
                command_name = commands_map.get(step.target_command_id)
                if command_name:
                    prompt["command_name"] = command_name
            elif step.target_prompt_id:
                prompt_name = prompts_map.get(step.target_prompt_id)
                if prompt_name:
                    prompt["prompt_name"] = prompt_name

            # Get pre-loaded arguments
            prompt_args = step_arguments.get(step.id, {})
            prompt.update(prompt_args)

            chain_steps.append(
                {
                    "step": step.step_number,
                    "agent_name": agent_name,
                    "prompt_type": step.prompt_type or "",
                    "prompt": prompt,
                }
            )

        return chain_steps

    def get_all_user_chains(self):
        """
        Get all chains available to the user from all tiers.
        Returns chains with source indicators (server/company/user).
        User chains override company, which override server chains of the same name.
        """
        session = get_session()
        chains_dict = {}  # name -> chain data (for deduplication)

        # 1. Server-level chains (non-internal only)
        server_chains = (
            session.query(ServerChain).filter(ServerChain.is_internal == False).all()
        )
        for chain in server_chains:
            steps = self._get_chain_steps_data(session, chain, "server")
            chains_dict[chain.name] = {
                "id": str(chain.id),
                "name": chain.name,
                "description": chain.description,
                "steps": steps,
                "source": "server",
                "is_override": False,
            }

        # 2. Company-level chains (override server)
        if self.company_id:
            company_chains = (
                session.query(CompanyChain)
                .filter(CompanyChain.company_id == self.company_id)
                .all()
            )
            for chain in company_chains:
                steps = self._get_chain_steps_data(session, chain, "company")
                is_override = chain.server_chain_id is not None
                chains_dict[chain.name] = {
                    "id": str(chain.id),
                    "name": chain.name,
                    "description": chain.description,
                    "steps": steps,
                    "source": "company",
                    "is_override": is_override,
                    "parent_id": (
                        str(chain.server_chain_id) if chain.server_chain_id else None
                    ),
                }

        # 3. User-level chains (override company and server)
        user_chains = (
            session.query(ChainDB).filter(ChainDB.user_id == self.user_id).all()
        )
        for chain in user_chains:
            steps = self._get_chain_steps_data(session, chain, "user")

            # Check if this is an override
            override = (
                session.query(UserChainOverride)
                .filter(
                    UserChainOverride.user_id == self.user_id,
                    UserChainOverride.chain_id == chain.id,
                )
                .first()
            )
            is_override = override is not None
            parent_id = None
            if override:
                if override.server_chain_id:
                    parent_id = str(override.server_chain_id)
                elif override.company_chain_id:
                    parent_id = str(override.company_chain_id)

            chains_dict[chain.name] = {
                "id": str(chain.id),
                "name": chain.name,
                "description": chain.description,
                "steps": steps,
                "source": "user",
                "is_override": is_override,
                "parent_id": parent_id,
            }

        # 4. Legacy global chains from DEFAULT_USER
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data and user_data.id != self.user_id:
            global_chains = (
                session.query(ChainDB).filter(ChainDB.user_id == user_data.id).all()
            )
            for chain in global_chains:
                if chain.name not in chains_dict:
                    steps = self._get_chain_steps_data(session, chain, "user")
                    chains_dict[chain.name] = {
                        "id": str(chain.id),
                        "name": chain.name,
                        "description": chain.description,
                        "steps": steps,
                        "source": "global",
                        "is_override": False,
                    }

        session.close()
        return list(chains_dict.values())

    def get_chain_with_tiered_resolution(self, chain_name):
        """
        Get a chain by name with tiered resolution:
        1. User-level chain (highest priority)
        2. Company-level chain
        3. Server-level chain (global)
        4. Legacy DEFAULT_USER chain (lowest priority)
        """
        session = get_session()
        chain_name = chain_name.replace("%20", " ")

        # 1. Try user-level chain first
        chain_db = (
            session.query(ChainDB)
            .filter(ChainDB.user_id == self.user_id, ChainDB.name == chain_name)
            .first()
        )
        if chain_db:
            steps = self._get_chain_steps_data(session, chain_db, "user")
            result = {
                "id": str(chain_db.id),
                "chain_name": chain_db.name,
                "description": chain_db.description or "",
                "steps": steps,
                "source": "user",
            }
            session.close()
            return result

        # 2. Try company-level chain
        if self.company_id:
            company_chain = (
                session.query(CompanyChain)
                .filter(
                    CompanyChain.company_id == self.company_id,
                    CompanyChain.name == chain_name,
                )
                .first()
            )
            if company_chain:
                steps = self._get_chain_steps_data(session, company_chain, "company")
                result = {
                    "id": str(company_chain.id),
                    "chain_name": company_chain.name,
                    "description": company_chain.description or "",
                    "steps": steps,
                    "source": "company",
                }
                session.close()
                return result

        # 3. Try server-level chain (global, non-internal)
        server_chain = (
            session.query(ServerChain).filter(ServerChain.name == chain_name).first()
        )
        if server_chain:
            steps = self._get_chain_steps_data(session, server_chain, "server")
            result = {
                "id": str(server_chain.id),
                "chain_name": server_chain.name,
                "description": server_chain.description or "",
                "steps": steps,
                "source": "server",
            }
            session.close()
            return result

        # 4. Try legacy DEFAULT_USER chain
        user_data = session.query(User).filter(User.email == DEFAULT_USER).first()
        if user_data:
            legacy_chain = (
                session.query(ChainDB)
                .filter(ChainDB.user_id == user_data.id, ChainDB.name == chain_name)
                .first()
            )
            if legacy_chain:
                steps = self._get_chain_steps_data(session, legacy_chain, "user")
                result = {
                    "id": str(legacy_chain.id),
                    "chain_name": legacy_chain.name,
                    "description": legacy_chain.description or "",
                    "steps": steps,
                    "source": "global",
                }
                session.close()
                return result

        session.close()
        return []

    def clone_chain_to_user(self, chain_name):
        """Clone a chain from parent tier to user level for editing."""
        session = get_session()
        chain_name = chain_name.replace("%20", " ")

        server_chain_id = None
        company_chain_id = None
        source_chain = None
        source_type = None

        # Check company-level first
        if self.company_id:
            company_chain = (
                session.query(CompanyChain)
                .filter(
                    CompanyChain.company_id == self.company_id,
                    CompanyChain.name == chain_name,
                )
                .first()
            )
            if company_chain:
                source_chain = company_chain
                source_type = "company"
                company_chain_id = company_chain.id

        # Check server-level
        if not source_chain:
            server_chain = (
                session.query(ServerChain)
                .filter(ServerChain.name == chain_name)
                .first()
            )
            if server_chain:
                source_chain = server_chain
                source_type = "server"
                server_chain_id = server_chain.id

        if not source_chain:
            session.close()
            return None

        # Create user's copy of the chain
        new_chain = ChainDB(
            name=source_chain.name,
            description=source_chain.description,
            user_id=self.user_id,
        )
        session.add(new_chain)
        session.commit()

        # Copy steps
        if source_type == "server":
            source_steps = (
                session.query(ServerChainStep)
                .filter(ServerChainStep.chain_id == source_chain.id)
                .order_by(ServerChainStep.step_number)
                .all()
            )
            step_arg_model = ServerChainStepArgument
        else:
            source_steps = (
                session.query(CompanyChainStep)
                .filter(CompanyChainStep.chain_id == source_chain.id)
                .order_by(CompanyChainStep.step_number)
                .all()
            )
            step_arg_model = CompanyChainStepArgument

        for source_step in source_steps:
            new_step = ChainStep(
                chain_id=new_chain.id,
                step_number=source_step.step_number,
                agent_id=source_step.agent_id,
                prompt_type=source_step.prompt_type,
                prompt=source_step.prompt,
                target_chain_id=source_step.target_chain_id,
                target_command_id=source_step.target_command_id,
                target_prompt_id=source_step.target_prompt_id,
            )
            session.add(new_step)
            session.commit()

            # Copy step arguments
            source_args = (
                session.query(step_arg_model)
                .filter(step_arg_model.chain_step_id == source_step.id)
                .all()
            )
            for source_arg in source_args:
                new_arg = ChainStepArgument(
                    chain_step_id=new_step.id,
                    argument_id=source_arg.argument_id,
                    value=source_arg.value,
                )
                session.add(new_arg)
            session.commit()

        # Track the override
        override = UserChainOverride(
            user_id=self.user_id,
            chain_id=new_chain.id,
            server_chain_id=server_chain_id,
            company_chain_id=company_chain_id,
        )
        session.add(override)
        session.commit()

        chain_id = str(new_chain.id)
        session.close()
        return chain_id

    def revert_chain_to_default(self, chain_id: str):
        """
        Revert a user's customized chain back to the parent (server/company) version.
        Deletes the user's override and removes the tracking record.
        """
        session = get_session()

        override = (
            session.query(UserChainOverride)
            .filter(
                UserChainOverride.user_id == self.user_id,
                UserChainOverride.chain_id == chain_id,
            )
            .first()
        )

        if not override:
            session.close()
            return {"success": False, "message": "This chain is not an override"}

        # Delete the user's chain (cascade will delete steps and arguments)
        chain = session.query(ChainDB).filter(ChainDB.id == chain_id).first()
        if chain:
            session.delete(chain)

        # Delete the override tracking
        session.delete(override)
        session.commit()
        session.close()

        return {"success": True, "message": "Reverted to default"}

    # =========================================================================
    # Server-level chain management (super admin only)
    # =========================================================================

    def get_server_chains(self, include_internal: bool = False):
        """Get all server-level chains. Super admin function."""
        session = get_session()
        query = session.query(ServerChain)
        if not include_internal:
            query = query.filter(ServerChain.is_internal == False)
        chains = query.all()

        result = []
        for chain in chains:
            steps = self._get_chain_steps_data(session, chain, "server")
            result.append(
                {
                    "id": str(chain.id),
                    "name": chain.name,
                    "description": chain.description,
                    "steps": steps,
                    "is_internal": chain.is_internal,
                }
            )

        session.close()
        return result

    def get_server_chain_by_id(self, chain_id: str):
        """Get a specific server-level chain by ID. Super admin function."""
        session = get_session()
        chain = session.query(ServerChain).filter(ServerChain.id == chain_id).first()

        if not chain:
            session.close()
            return None

        steps = self._get_chain_steps_data(session, chain, "server")
        result = {
            "id": str(chain.id),
            "name": chain.name,
            "description": chain.description,
            "steps": steps,
            "is_internal": chain.is_internal,
            "created_at": str(chain.created_at) if chain.created_at else None,
            "updated_at": str(chain.updated_at) if chain.updated_at else None,
        }

        session.close()
        return result

    def add_server_chain(
        self, name: str, description: str = "", is_internal: bool = False
    ):
        """Add a server-level chain. Super admin function."""
        session = get_session()
        chain = ServerChain(
            name=name,
            description=description,
            is_internal=is_internal,
        )
        session.add(chain)
        session.commit()
        chain_id = str(chain.id)
        session.close()
        return chain_id

    def update_server_chain(
        self,
        chain_id: str,
        name: str = None,
        description: str = None,
        is_internal: bool = None,
    ):
        """Update a server-level chain. Super admin function."""
        session = get_session()
        chain = session.query(ServerChain).filter(ServerChain.id == chain_id).first()
        if not chain:
            session.close()
            raise Exception("Server chain not found")

        if name is not None:
            chain.name = name
        if description is not None:
            chain.description = description
        if is_internal is not None:
            chain.is_internal = is_internal

        session.commit()
        session.close()

    def delete_server_chain(self, chain_id: str):
        """Delete a server-level chain. Super admin function."""
        session = get_session()
        chain = session.query(ServerChain).filter(ServerChain.id == chain_id).first()
        if not chain:
            session.close()
            raise Exception("Server chain not found")
        session.delete(chain)
        session.commit()
        session.close()

    def add_server_chain_step(
        self,
        chain_id: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ):
        """Add a step to a server chain. Super admin function."""
        session = get_session()
        chain = session.query(ServerChain).filter(ServerChain.id == chain_id).first()
        if not chain:
            session.close()
            raise Exception("Server chain not found")

        # Get agent (from any user or default)
        agent = session.query(Agent).filter(Agent.name == agent_name).first()
        if not agent:
            session.close()
            raise Exception(f"Agent {agent_name} not found")

        # Determine target IDs
        target_chain_id = None
        target_command_id = None
        target_prompt_id = None
        argument_key = None

        if prompt_type.lower() == "prompt":
            argument_key = "prompt_name"
            prompt_category = prompt.get("prompt_category", "Default")
            target = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt.get("prompt_name"),
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
            )
            if target:
                target_prompt_id = target.id
        elif prompt_type.lower() == "chain":
            argument_key = "chain_name" if "chain_name" in prompt else "chain"
            target = (
                session.query(ChainDB)
                .filter(ChainDB.name == prompt.get(argument_key))
                .first()
            )
            if target:
                target_chain_id = target.id
        elif prompt_type.lower() == "command":
            argument_key = "command_name"
            target = (
                session.query(Command)
                .filter(Command.name == prompt.get("command_name"))
                .first()
            )
            if target:
                target_command_id = target.id

        step = ServerChainStep(
            chain_id=chain.id,
            step_number=step_number,
            agent_id=agent.id,
            prompt_type=prompt_type,
            prompt=prompt.get(argument_key, "") if argument_key else "",
            target_chain_id=target_chain_id,
            target_command_id=target_command_id,
            target_prompt_id=target_prompt_id,
        )
        session.add(step)
        session.commit()

        # Add step arguments
        prompt_args = {
            k: v
            for k, v in prompt.items()
            if k != argument_key and k != "prompt_category"
        }
        for arg_name, arg_value in prompt_args.items():
            argument = session.query(Argument).filter(Argument.name == arg_name).first()
            if argument:
                step_arg = ServerChainStepArgument(
                    chain_step_id=step.id,
                    argument_id=argument.id,
                    value=str(arg_value),
                )
                session.add(step_arg)

        session.commit()
        session.close()

    def delete_server_chain_step(self, chain_id: str, step_number: int):
        """Delete a step from a server chain. Super admin function."""
        session = get_session()
        chain = session.query(ServerChain).filter(ServerChain.id == chain_id).first()
        if not chain:
            session.close()
            raise Exception("Server chain not found")

        step = (
            session.query(ServerChainStep)
            .filter(
                ServerChainStep.chain_id == chain.id,
                ServerChainStep.step_number == step_number,
            )
            .first()
        )
        if step:
            session.delete(step)
            session.commit()

            # Reorder remaining steps
            session.query(ServerChainStep).filter(
                ServerChainStep.chain_id == chain.id,
                ServerChainStep.step_number > step_number,
            ).update(
                {"step_number": ServerChainStep.step_number - 1},
                synchronize_session=False,
            )
            session.commit()

        session.close()

    # =========================================================================
    # Company-level chain management (company admin only)
    # =========================================================================

    def get_company_chains(self, company_id: str = None):
        """Get all company-level chains. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            return []

        session = get_session()
        chains = (
            session.query(CompanyChain)
            .filter(CompanyChain.company_id == target_company)
            .all()
        )

        result = []
        for chain in chains:
            steps = self._get_chain_steps_data(session, chain, "company")
            result.append(
                {
                    "id": str(chain.id),
                    "name": chain.name,
                    "description": chain.description,
                    "steps": steps,
                    "server_chain_id": (
                        str(chain.server_chain_id) if chain.server_chain_id else None
                    ),
                }
            )

        session.close()
        return result

    def get_company_chain_by_id(self, chain_id: str, company_id: str = None):
        """Get a specific company-level chain by ID. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            return None

        session = get_session()
        chain = (
            session.query(CompanyChain)
            .filter(
                CompanyChain.id == chain_id, CompanyChain.company_id == target_company
            )
            .first()
        )

        if not chain:
            session.close()
            return None

        steps = self._get_chain_steps_data(session, chain, "company")
        result = {
            "id": str(chain.id),
            "name": chain.name,
            "description": chain.description,
            "steps": steps,
            "server_chain_id": (
                str(chain.server_chain_id) if chain.server_chain_id else None
            ),
            "created_at": str(chain.created_at) if chain.created_at else None,
            "updated_at": str(chain.updated_at) if chain.updated_at else None,
        }

        session.close()
        return result

    def add_company_chain(
        self, name: str, description: str = "", company_id: str = None
    ):
        """Add a company-level chain. Company admin function."""
        target_company = company_id or self.company_id
        if not target_company:
            raise Exception("No company context")

        session = get_session()
        chain = CompanyChain(
            company_id=target_company,
            name=name,
            description=description,
        )
        session.add(chain)
        session.commit()
        chain_id = str(chain.id)
        session.close()
        return chain_id

    def update_company_chain(
        self, chain_id: str, name: str = None, description: str = None
    ):
        """Update a company-level chain. Company admin function."""
        session = get_session()
        chain = (
            session.query(CompanyChain)
            .filter(
                CompanyChain.id == chain_id,
                CompanyChain.company_id == self.company_id,
            )
            .first()
        )
        if not chain:
            session.close()
            raise Exception("Company chain not found")

        if name is not None:
            chain.name = name
        if description is not None:
            chain.description = description

        session.commit()
        session.close()

    def delete_company_chain(self, chain_id: str):
        """Delete a company-level chain. Company admin function."""
        session = get_session()
        chain = (
            session.query(CompanyChain)
            .filter(
                CompanyChain.id == chain_id,
                CompanyChain.company_id == self.company_id,
            )
            .first()
        )
        if not chain:
            session.close()
            raise Exception("Company chain not found")
        session.delete(chain)
        session.commit()
        session.close()

    def share_chain_to_company(self, chain_id: str):
        """
        Share a user's chain to the company level.
        Company admin function.
        """
        session = get_session()

        # Get user's chain
        user_chain = (
            session.query(ChainDB)
            .filter(
                ChainDB.id == chain_id,
                ChainDB.user_id == self.user_id,
            )
            .first()
        )
        if not user_chain:
            session.close()
            raise Exception("Chain not found")

        if not self.company_id:
            session.close()
            raise Exception("No company context")

        # Create company version
        company_chain = CompanyChain(
            company_id=self.company_id,
            name=user_chain.name,
            description=user_chain.description,
        )
        session.add(company_chain)
        session.commit()

        # Copy steps
        user_steps = (
            session.query(ChainStep)
            .filter(ChainStep.chain_id == user_chain.id)
            .order_by(ChainStep.step_number)
            .all()
        )

        for user_step in user_steps:
            company_step = CompanyChainStep(
                chain_id=company_chain.id,
                step_number=user_step.step_number,
                agent_id=user_step.agent_id,
                prompt_type=user_step.prompt_type,
                prompt=user_step.prompt,
                target_chain_id=user_step.target_chain_id,
                target_command_id=user_step.target_command_id,
                target_prompt_id=user_step.target_prompt_id,
            )
            session.add(company_step)
            session.commit()

            # Copy step arguments
            user_args = (
                session.query(ChainStepArgument)
                .filter(ChainStepArgument.chain_step_id == user_step.id)
                .all()
            )
            for user_arg in user_args:
                company_arg = CompanyChainStepArgument(
                    chain_step_id=company_step.id,
                    argument_id=user_arg.argument_id,
                    value=user_arg.value,
                )
                session.add(company_arg)

        session.commit()
        chain_id = str(company_chain.id)
        session.close()
        return chain_id

    def add_company_chain_step(
        self,
        chain_id: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ):
        """Add a step to a company chain. Company admin function."""
        session = get_session()
        chain = (
            session.query(CompanyChain)
            .filter(
                CompanyChain.id == chain_id,
                CompanyChain.company_id == self.company_id,
            )
            .first()
        )
        if not chain:
            session.close()
            raise Exception("Company chain not found")

        # Get agent
        agent = (
            session.query(Agent)
            .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
            .first()
        )
        if not agent:
            agent = session.query(Agent).filter(Agent.name == agent_name).first()
        if not agent:
            session.close()
            raise Exception(f"Agent {agent_name} not found")

        # Determine target IDs (similar to server chain step)
        target_chain_id = None
        target_command_id = None
        target_prompt_id = None
        argument_key = None

        if prompt_type.lower() == "prompt":
            argument_key = "prompt_name"
            prompt_category = prompt.get("prompt_category", "Default")
            target = (
                session.query(Prompt)
                .filter(
                    Prompt.name == prompt.get("prompt_name"),
                    Prompt.user_id == self.user_id,
                    Prompt.prompt_category.has(name=prompt_category),
                )
                .first()
            )
            if target:
                target_prompt_id = target.id
        elif prompt_type.lower() == "chain":
            argument_key = "chain_name" if "chain_name" in prompt else "chain"
            target = (
                session.query(ChainDB)
                .filter(
                    ChainDB.name == prompt.get(argument_key),
                    ChainDB.user_id == self.user_id,
                )
                .first()
            )
            if target:
                target_chain_id = target.id
        elif prompt_type.lower() == "command":
            argument_key = "command_name"
            target = (
                session.query(Command)
                .filter(Command.name == prompt.get("command_name"))
                .first()
            )
            if target:
                target_command_id = target.id

        step = CompanyChainStep(
            chain_id=chain.id,
            step_number=step_number,
            agent_id=agent.id,
            prompt_type=prompt_type,
            prompt=prompt.get(argument_key, "") if argument_key else "",
            target_chain_id=target_chain_id,
            target_command_id=target_command_id,
            target_prompt_id=target_prompt_id,
        )
        session.add(step)
        session.commit()

        # Add step arguments
        prompt_args = {
            k: v
            for k, v in prompt.items()
            if k != argument_key and k != "prompt_category"
        }
        for arg_name, arg_value in prompt_args.items():
            argument = session.query(Argument).filter(Argument.name == arg_name).first()
            if argument:
                step_arg = CompanyChainStepArgument(
                    chain_step_id=step.id,
                    argument_id=argument.id,
                    value=str(arg_value),
                )
                session.add(step_arg)

        session.commit()
        session.close()

    def delete_company_chain_step(self, chain_id: str, step_number: int):
        """Delete a step from a company chain. Company admin function."""
        session = get_session()
        chain = (
            session.query(CompanyChain)
            .filter(
                CompanyChain.id == chain_id,
                CompanyChain.company_id == self.company_id,
            )
            .first()
        )
        if not chain:
            session.close()
            raise Exception("Company chain not found")

        step = (
            session.query(CompanyChainStep)
            .filter(
                CompanyChainStep.chain_id == chain.id,
                CompanyChainStep.step_number == step_number,
            )
            .first()
        )
        if step:
            session.delete(step)
            session.commit()

            # Reorder remaining steps
            session.query(CompanyChainStep).filter(
                CompanyChainStep.chain_id == chain.id,
                CompanyChainStep.step_number > step_number,
            ).update(
                {"step_number": CompanyChainStep.step_number - 1},
                synchronize_session=False,
            )
            session.commit()

        session.close()
