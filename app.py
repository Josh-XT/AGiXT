import os
import shutil
import json
from flask import Flask, request
from flask_cors import CORS
from babyagi import babyagi
from AgentLLM import AgentLLM
from Config import Config
from flask_restful import Api, Resource
from flask_swagger_ui import get_swaggerui_blueprint
from Commands import Commands
import threading
from threading import Lock

CFG = Config()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
api = Api(app)
babyagi_instances = {}
babyagi_outputs = {}
output_lock = Lock()
SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Agent-LLM Flask API"
    }
)

app.register_blueprint(swaggerui_blueprint)

class AddAgent(Resource):
    def post(self, agent_name):
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        i = 0
        agent_file = f"{agent_name}.yaml"
        while os.path.exists(os.path.join(memories_dir, agent_file)):
            i += 1
            agent_file = f"{agent_name}_{i}.yaml"
        with open(os.path.join(memories_dir, agent_file), "w") as f:
            f.write("")
        # Make agents/{agent_name}/config.json
        agent_folder = f"agents/{agent_name}"
        if not os.path.exists(agent_folder):
            os.makedirs(agent_folder)
        agent_config = os.path.join(agent_folder, "config.json")
        with open(agent_config, "w") as f:
            commands = Commands(load_commands_flag=False)
            commands_list = commands.load_commands(agent_name=agent_name)
            config_data = {"commands": {command: "true" for command in commands_list}}
            json.dump(config_data, f)
        return {"message": "Agent added", "agent_file": agent_file}, 200

class DeleteAgent(Resource):
    def delete(self, agent_name):
        agent_file = f"agents/{agent_name}.yaml"
        agent_folder = f"agents/{agent_name}/"
        agent_file = os.path.abspath(agent_file)
        agent_folder = os.path.abspath(agent_folder)
        try:
            os.remove(agent_file)
        except FileNotFoundError:
            return {"message": f"Agent file {agent_file} not found."}, 404

        if os.path.exists(agent_folder):
            shutil.rmtree(agent_folder)

        return {"message": f"Agent {agent_name} deleted."}, 200

class GetAgents(Resource):
    def get(self):
        memories_dir = "agents"
        agents = []
        for file in os.listdir(memories_dir):
            if file.endswith(".yaml"):
                agents.append(file.replace(".yaml", ""))
        # Check agent status and return {"agents": [{"name": "agent_name", "status": "running"}]
        output = []
        for agent in agents:
            try:
                babyagi_instance = babyagi_instances[agent]
                status = babyagi_instance.get_status()
            except:
                status = False
            output.append({"name": agent, "status": status})
        return {"agents": output}, 200

class GetChatHistory(Resource):
    def get(self, agent_name):
        with open(os.path.join("agents", f"{agent_name}.yaml"), "r") as f:
            chat_history = f.read()
        return {"chat_history": chat_history}, 200

class WipeAgentMemories(Resource):
    def delete(self, agent_name):
        # Delete the folder agents/{agent_name}/memories
        agent_folder = f"agents/{agent_name}/"
        agent_folder = os.path.abspath(agent_folder)
        memories_folder = os.path.join(agent_folder, "memories")
        if os.path.exists(memories_folder):
            shutil.rmtree(memories_folder)
        return {"message": f"Memories for agent {agent_name} deleted."}, 200

class Instruct(Resource):
    def post(self, agent_name):
        objective = request.json.get("prompt")
        agent = AgentLLM(agent_name)
        response = agent.run(objective, max_context_tokens=500, long_term_access=False)
        return {"response": str(response)}, 200
    
class GetCommands(Resource):
    def get(self, agent_name):
        commands = Commands(agent_name)
        available_commands = commands.get_available_commands()
        return {"commands": available_commands}, 200

class EnableCommand(Resource):
    def post(self, agent_name, command_name):
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "true"
        with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
            json.dump(commands.agent_config, agent_config)
        return {"message": f"Command '{command_name}' enabled for agent '{agent_name}'."}, 200

class DisableCommand(Resource):
    def post(self, agent_name, command_name):
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "false"
        with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
            json.dump(commands.agent_config, agent_config)
        return {"message": f"Command '{command_name}' disabled for agent '{agent_name}'."}, 200

class EnableAllCommands(Resource):
    def post(self, agent_name):
        try:
            commands = Commands(agent_name)
            for command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][command_name] = "false"
            with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
                json.dump(commands.agent_config, agent_config)
            return {"message": f"All commands disabled for agent '{agent_name}'."}, 200
        except Exception as e:
            return {"message": f"Error disabling all commands for agent '{agent_name}': {str(e)}"}, 500

class DisableAllCommands(Resource):
    def post(self, agent_name):
        try:
            commands = Commands(agent_name)
            for command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][command_name] = "true"
            with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
                json.dump(commands.agent_config, agent_config)
            return {"message": f"All commands enabled for agent '{agent_name}'."}, 200
        except Exception as e:
            return {"message": f"Error enabling all commands for agent '{agent_name}': {str(e)}"}, 500

class StartTaskAgent(Resource):
    def post(self, agent_name):
        objective = request.json.get("objective")
        if agent_name not in babyagi_instances:
            babyagi_instances[agent_name] = babyagi()
        babyagi_instance = babyagi_instances[agent_name]
        babyagi_instance.set_agent_name(agent_name)  # Set the agent_name for the babyagi instance
        babyagi_instance.set_objective(objective)
        agent_thread = threading.Thread(target=babyagi_instance.run)
        agent_thread.start()
        return {"message": "Task agent started"}, 200

class StopTaskAgent(Resource):
    def post(self, agent_name):
        if agent_name not in babyagi_instances:
            return {"message": "Task agent not found"}, 404
        babyagi_instance = babyagi_instances[agent_name]
        babyagi_instance.stop_running()
        return {"message": "Task agent stopped"}, 200

class GetTaskOutput(Resource):
    def get(self, agent_name):
        if agent_name not in babyagi_instances:
            return {"message": "Task agent not found"}, 404
        babyagi_instance = babyagi_instances[agent_name]
        output = babyagi_instance.get_output()
        with open(os.path.join("model-prompts", "default", "system.txt"), "r") as f:
            system_prompt = f.read()
        if system_prompt in output:
            output = output.replace(system_prompt, "")
        if babyagi_instance.get_status():
            return {"output": output, "message": "Task agent is still running"}, 200
        return {"output": output}, 200

class GetTaskStatus(Resource):
    def get(self, agent_name):
        if agent_name not in babyagi_instances:
            return {"status": False}
        babyagi_instance = babyagi_instances[agent_name]
        status = babyagi_instance.get_status()
        return {"status": status}, 200

class GetChains(Resource):
    def get(self):
        chains = os.listdir("chains")
        chain_data = {}
        for chain in chains:
            chain_steps = os.listdir(os.path.join("chains", chain))
            for step in chain_steps:
                step_number = step.split("-")[0]
                prompt_type = step.split("-")[1]
                with open(os.path.join("chains", chain, step), "r") as f:
                    prompt = f.read()
                if chain not in chain_data:
                    chain_data[chain] = {}
                if step_number not in chain_data[chain]:
                    chain_data[chain][step_number] = {}
                chain_data[chain][step_number][prompt_type] = prompt
        return chain_data, 200
    
class GetChain(Resource):
    def get(self):
        chain_name = request.json.get("chain_name")
        chain_steps = os.listdir(os.path.join("chains", chain_name))
        chain_data = {}
        for step in chain_steps:
            step_number = step.split("-")[0]
            prompt_type = step.split("-")[1]
            with open(os.path.join("chains", chain_name, step), "r") as f:
                prompt = f.read()
            if step_number not in chain_data:
                chain_data[step_number] = {}
            chain_data[step_number][prompt_type] = prompt
        return chain_data, 200

class AddChain(Resource):
    def post(self):
        # Get the chain name from the request
        chain_name = request.json.get("chain_name")
        # Create the chain directory
        os.mkdir(os.path.join("chains", chain_name))
        return {"message": f"Chain '{chain_name}' created"}, 200
    
class AddChainStep(Resource):
    def post(self):
        chain_name = request.json.get("chain_name")
        # Get the step number from the request
        step_number = request.json.get("step_number")
        # Get the prompt type from the request
        prompt_type = request.json.get("prompt_type")
        # Get the prompt from the request
        prompt = request.json.get("prompt")
        # Create the step file
        with open(os.path.join("chains", chain_name, f"{step_number}-{prompt_type}.txt"), "w") as f:
            f.write(prompt)
        return {"message": f"Step '{step_number}' created for chain '{chain_name}'"}, 200
    
class UpdateStep(Resource):
    def post(self):
        chain_name = request.json.get("chain_name")
        # Get the old step number from the request
        old_step_number = request.json.get("old_step_number")
        # Get the new step number from the request
        new_step_number = request.json.get("new_step_number")
        # Get the prompt type from the request
        prompt_type = request.json.get("prompt_type")
        # Create the step file
        os.rename(os.path.join("chains", chain_name, f"{old_step_number}-{prompt_type}.txt"), os.path.join("chains", chain_name, f"{new_step_number}-{prompt_type}.txt"))
        return {"message": f"Step '{old_step_number}' changed to '{new_step_number}' for chain '{chain_name}' with prompt type {prompt_type}."}, 200

class DeleteChain(Resource):
    def delete(self):
        chain_name = request.json.get("chain_name")
        # Delete the chain directory
        shutil.rmtree(os.path.join("chains", chain_name))
        return {"message": f"Chain '{chain_name}' deleted"}, 200
    
class DeleteChainStep(Resource):
    def delete(self, step_number):
        chain_name = request.json.get("chain_name")
        # Remove the step file, it will be {step_number}-{prompt_type}.txt
        os.remove(os.path.join("chains", chain_name, f"{step_number}-*.txt"))
        return {"message": f"Step '{step_number}' deleted for chain '{chain_name}'"}, 200

class RunChain(Resource):
    def post(self, agent_name):
        # Get the agent name from the request
        chain_name = request.json.get("chain_name")
        # Get the chain steps
        chain_steps = os.listdir(os.path.join("chains", chain_name))
        # Get the chain steps sorted by step number
        chain_steps = sorted(chain_steps, key=lambda x: int(x.split("-")[0]))
        # Iterate over the chain steps
        for step in chain_steps:
            # Get the prompt type
            prompt_type = step.split("-")[1]
            # Get the prompt
            with open(os.path.join("chains", chain_name, step), "r") as f:
                prompt = f.read()
            if prompt_type == "instruction":
                prompter = AgentLLM(agent_name)
                prompter.run(prompt)
            elif prompt_type == "task":
                babyagi_instances[agent_name].run(prompt)
        return {"message": "Prompt chain started"}, 200

# Agents
api.add_resource(GetAgents, '/api/get_agents')
# Output: {"agents": ["agent1", "agent2", "agent3"]}
api.add_resource(AddAgent, '/api/add_agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' added"}
api.add_resource(DeleteAgent, '/api/delete_agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' deleted"}
api.add_resource(GetCommands, '/api/get_commands/<string:agent_name>')
# Output: {"commands": [ {"friendly_name": "Friendly Name", "name": "command1", "enabled": True}, {"friendly_name": "Friendly Name 2", "name": "command2", "enabled": False }]}
api.add_resource(EnableCommand, '/api/enable_command/<string:agent_name>/<string:command_name>')
# Output: {"message": "Command 'command1' enabled for agent 'agent1'"}
api.add_resource(DisableCommand, '/api/disable_command/<string:agent_name>/<string:command_name>')
# Output: {"message": "Command 'command1' disabled for agent 'agent1'"}
api.add_resource(DisableAllCommands, '/api/disable_all_commands/<string:agent_name>')
# Output: {"message": "All commands disabled for agent 'agent1'"}
api.add_resource(EnableAllCommands, '/api/enable_all_commands/<string:agent_name>')
# Output: {"message": "All commands enabled for agent 'agent1'"}
api.add_resource(GetChatHistory, '/api/get_chat_history/<string:agent_name>')
# Output: {"chat_history": ["chat1", "chat2", "chat3"]}
api.add_resource(Instruct, '/api/instruct/<string:agent_name>')
# Output: {"message": "Prompt sent to agent 'agent1'"}
api.add_resource(WipeAgentMemories, '/api/wipe_agent_memories/<string:agent_name>')
# Output: {"message": "Agent 'agent1' memories wiped"}

# Tasks
api.add_resource(StartTaskAgent, '/api/task/start/<string:agent_name>')
# Output: {"message": "Task agent 'agent1' started"}
api.add_resource(StopTaskAgent, '/api/task/stop/<string:agent_name>')
# Output: {"message": "Task agent 'agent1' stopped"}
api.add_resource(GetTaskOutput, '/api/task/output/<string:agent_name>')
# Output: {"output": "output"}
api.add_resource(GetTaskStatus, '/api/task/status/<string:agent_name>')
# Output: {"status": "status"}

# Chains
api.add_resource(GetChains, '/api/get_chains')
# Output: {chain_name: {step_number: {prompt_type: prompt}}}
api.add_resource(GetChain, '/api/get_chain')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(AddChain, '/api/add_chain')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(AddChainStep, '/api/add_chain_step')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(UpdateStep, '/api/update_step')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(DeleteChain, '/api/delete_chain')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(DeleteChainStep, '/api/delete_chain_step/<string:step_number>')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(RunChain, '/api/run_chain/<string:agent_name>')
# Output: {step_number: {prompt_type: prompt}}

if __name__ == '__main__':
    app.run(debug=True)