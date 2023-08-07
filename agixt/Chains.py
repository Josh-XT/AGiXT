import os
import logging
from agixtsdk import AGiXTSDK
from Extensions import Extensions
from dotenv import load_dotenv

load_dotenv()

db_connected = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
if db_connected:
    from db.Chain import Chain
    from db.Prompts import Prompts
else:
    from fb.Chain import Chain
    from fb.Prompts import Prompts

ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY", None)
)

chain = Chain()


class Chains:
    async def run_chain_step(
        self,
        step: dict = {},
        chain_name="",
        user_input="",
        agent_override="",
        chain_args={},
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
                args = chain.get_step_content(
                    chain_name=chain_name,
                    prompt_content=step["prompt"],
                    user_input=user_input,
                    agent_name=step["agent_name"],
                )
                if chain_args != {}:
                    for arg, value in chain_args.items():
                        args[arg] = value

                if "conversation_name" not in args:
                    args["conversation_name"] = f"Chain Execution History: {chain_name}"
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
                        all_responses=args["all_responses"]
                        if "all_responses" in args
                        else False,
                        from_step=args["from_step"] if "from_step" in args else 1,
                    )
        if result:
            if isinstance(result, dict) and "response" in result:
                result = result["response"]
            if result == "Unable to retrieve data.":
                result = None
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
        chain_args={},
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
                    step["step"] = step_data["step"]
                    logging.info(
                        f"Running step {step_data['step']} with agent {step['agent_name']}."
                    )
                    try:
                        step_response = await self.run_chain_step(
                            step=step,
                            chain_name=chain_name,
                            user_input=user_input,
                            agent_override=agent_override,
                            chain_args=chain_args,
                        )  # Get the response of the current step.
                    except Exception as e:
                        logging.error(e)
                        step_response = None
                    if step_response == None:
                        return f"Chain failed to complete, it failed on step {step_data['step']}. You can resume by starting the chain from the step that failed."
                    step["response"] = step_response
                    last_response = step_response
                    logging.info(f"Last response: {last_response}")
                    responses[step_data["step"]] = step  # Store the response.
                    logging.info(f"Step {step_data['step']} response: {step_response}")
                    # Write the response to the chain responses file.
                    await chain.update_chain_responses(
                        chain_name=chain_name, responses=responses
                    )
        if all_responses:
            return responses
        else:
            # Return only the last response in the chain.
            return last_response

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
        chain_data = chain.get_chain(chain_name=chain_name)
        steps = chain_data["steps"]
        prompt_args = []
        args = []
        for step in steps:
            try:
                prompt = step["prompt"]
                if "prompt_name" in prompt:
                    prompt_text = Prompts().get_prompt(
                        prompt_name=prompt["prompt_name"]
                    )
                    args = Prompts().get_prompt_args(prompt_text=prompt_text)
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
                logging.error(e)
        return prompt_args
