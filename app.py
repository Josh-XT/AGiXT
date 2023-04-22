from flask import Flask, request
from flask_cors import CORS
from AgentLLM import AgentLLM
from Config import Config
from flask_restful import Api, Resource
from flask_swagger_ui import get_swaggerui_blueprint
from Commands import Commands
import threading

CFG = Config()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
api = Api(app)
agent_instances = CFG.agent_instances
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

class GetProviders(Resource):
    def get(self):
        providers = CFG.get_providers()
        return {"providers": providers}, 200

class AddAgent(Resource):
    def post(self):
        agent_name = request.json['agent_name']
        agent_info = CFG.add_agent(agent_name)
        return {"message": "Agent added", "agent_file": agent_info['agent_file']}, 200

class RenameAgent(Resource):
    def put(self, agent_name):
        new_name = request.json['new_name']
        CFG.rename_agent(agent_name, new_name)
        return {"message": f"Agent {agent_name} renamed to {new_name}."}, 200

class DeleteAgent(Resource):
    def delete(self, agent_name):
        result = CFG.delete_agent(agent_name)
        return result

class GetAgents(Resource):
    def get(self):
        agents = CFG.get_agents()
        return {"agents": agents}, 200

class GetAgentConfig(Resource):
    def get(self, agent_name):
        agent_config = CFG.get_agent_config(agent_name)
        return {"agent": agent_config}, 200
class GetChatHistory(Resource):
    def get(self, agent_name):
        chat_history = CFG.get_chat_history(agent_name)
        return {"chat_history": chat_history}, 200

class WipeAgentMemories(Resource):
    def delete(self, agent_name):
        CFG.wipe_agent_memories(agent_name)
        return {"message": f"Memories for agent {agent_name} deleted."}, 200

class Instruct(Resource):
    def post(self, agent_name):
        objective = request.json.get("prompt")
        agent = AgentLLM(agent_name)
        response = agent.run(objective, max_context_tokens=500, long_term_access=False)
        return {"response": str(response)}, 200

class Chat(Resource):
    def post(self, agent_name):
        # TODO: Change this from using the normal instruct and add a chat method to AgentLLM
        objective = request.json.get("prompt")
        agent = AgentLLM(agent_name)
        response = agent.run(objective, max_context_tokens=500, long_term_access=False)
        return {"response": str(response)}, 200

class GetCommands(Resource):
    def get(self, agent_name):
        commands = Commands(agent_name)
        available_commands = commands.get_available_commands()
        return {"commands": available_commands}, 200

class ToggleCommand(Resource):
    def patch(self, agent_name):
        enable = request.json.get("enable")
        command_name = request.json.get("command_name")
        try:
            if command_name == "*":
                    commands = Commands(agent_name)
                    for each_command_name in commands.agent_config["commands"]:
                        commands.agent_config["commands"][each_command_name] = enable
                    CFG.update_agent_config(agent_name, commands.agent_config)
                    return {"message": f"All commands enabled for agent '{agent_name}'."}, 200
            else:
                commands = Commands(agent_name)
                commands.agent_config["commands"][command_name] = enable
                CFG.update_agent_config(agent_name, commands.agent_config)
                return {"message": f"Command '{command_name}' toggled for agent '{agent_name}'."}, 200
        except Exception as e:
                    return {"message": f"Error enabled all commands for agent '{agent_name}': {str(e)}"}, 500        

class ToggleTaskAgent(Resource):
    def post(self, agent_name):
        if agent_name not in agent_instances:
            objective = request.json.get("objective")
            if agent_name not in agent_instances:
                agent_instances[agent_name] = AgentLLM(agent_name)
            agent_instance = agent_instances[agent_name]
            agent_instance.set_agent_name(agent_name)
            agent_instance.set_objective(objective)
            agent_thread = threading.Thread(target=agent_instance.run_task)
            agent_thread.start()
            return {"message": "Task agent started"}, 200
        else:
            agent_instance = agent_instances[agent_name]
            agent_instance.stop_running()
            return {"message": "Task agent stopped"}, 200

class GetTaskOutput(Resource):
    def get(self, agent_name):
        if agent_name not in agent_instances:
            return {"message": "Task agent not found"}, 404
        agent_instance = agent_instances[agent_name]
        output = CFG.get_task_output(agent_name, agent_instance)
        if agent_instance.get_status():
            return {"output": output, "message": "Task agent is still running"}, 200
        return {"output": output}, 200

class GetTaskStatus(Resource):
    def get(self, agent_name):
        if agent_name not in agent_instances:
            return {"status": False}
        agent_instance = agent_instances[agent_name]
        status = agent_instance.get_status()
        return {"status": status}, 200

class GetChains(Resource):
    def get(self):
        chains = CFG.get_chains()
        return chains, 200
    
class GetChain(Resource):
    def get(self):
        chain_name = request.json.get("chain_name")
        chain_data = CFG.get_chain(chain_name)
        return chain_data, 200

class AddChain(Resource):
    def post(self):
        chain_name = request.json.get("chain_name")
        CFG.add_chain(chain_name)
        return {"message": f"Chain '{chain_name}' created"}, 200
    
class AddChainStep(Resource):
    def post(self):
        chain_name = request.json.get("chain_name")
        step_number = request.json.get("step_number")
        prompt_type = request.json.get("prompt_type")
        prompt = request.json.get("prompt")
        CFG.add_chain_step(chain_name, step_number, prompt_type, prompt)
        return {"message": f"Step '{step_number}' created for chain '{chain_name}'"}, 200
    
class UpdateStep(Resource):
    def post(self):
        chain_name = request.json.get("chain_name")
        old_step_number = request.json.get("old_step_number")
        new_step_number = request.json.get("new_step_number")
        prompt_type = request.json.get("prompt_type")
        CFG.update_step(chain_name, old_step_number, new_step_number, prompt_type)
        return {"message": f"Step '{old_step_number}' changed to '{new_step_number}' for chain '{chain_name}' with prompt type {prompt_type}."}, 200

class DeleteChain(Resource):
    def delete(self):
        chain_name = request.json.get("chain_name")
        CFG.delete_chain(chain_name)
        return {"message": f"Chain '{chain_name}' deleted"}, 200
    
class DeleteChainStep(Resource):
    def delete(self, step_number):
        chain_name = request.json.get("chain_name")
        CFG.delete_chain_step(chain_name, step_number)
        return {"message": f"Step '{step_number}' deleted for chain '{chain_name}'"}, 200

class RunChain(Resource):
    def post(self, agent_name):
        chain_name = request.json.get("chain_name")
        CFG.run_chain(agent_name, chain_name)
        return {"message": "Prompt chain started"}, 200

# Providers
api.add_resource(GetProviders, '/api/provider')

# Agents
api.add_resource(GetAgents, '/api/agent')
# Output: {"agents": ["agent1", "agent2", "agent3"]}
api.add_resource(AddAgent, '/api/agent')
# Output: {"message": "Agent 'agent1' added"}
api.add_resource(GetAgentConfig, '/api/agent/<string:agent_name>')
# Output: {"agent_config": {"agent_name": "agent1", "agent_type": "task", "commands": {"command1": "true", "command2": "false"}}}
api.add_resource(RenameAgent, '/api/agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' renamed to 'agent2'"}
api.add_resource(DeleteAgent, '/api/agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' deleted"}
api.add_resource(GetCommands, '/api/agent/<string:agent_name>/command')
# Output: {"commands": [ {"friendly_name": "Friendly Name", "name": "command1", "enabled": True}, {"friendly_name": "Friendly Name 2", "name": "command2", "enabled": False }]}
api.add_resource(ToggleCommand, '/api/agent/<string:agent_name>/command')
# Output: {"message": "Command 'command1' enabled for agent 'agent1'"}
api.add_resource(Chat, '/api/agent/<string:agent_name>/chat')
# Output: {"message": "Prompt sent to agent 'agent1'"}
api.add_resource(GetChatHistory, '/api/<string:agent_name>/chat')
# Output: {"chat_history": ["chat1", "chat2", "chat3"]}
api.add_resource(Instruct, '/api/agent/<string:agent_name>/instruct')
# Output: {"message": "Prompt sent to agent 'agent1'"}
api.add_resource(WipeAgentMemories, '/api/agent/<string:agent_name>/memory')
# Output: {"message": "Agent 'agent1' memories wiped"}

# Tasks
api.add_resource(ToggleTaskAgent, '/api/agent/<string:agent_name>/task')
# Output: {"message": "Task agent 'agent1' started"}
# Output: {"message": "Task agent 'agent1' stopped"}
api.add_resource(GetTaskOutput, '/api/agent/<string:agent_name>/task')
# Output: {"output": "output"}
api.add_resource(GetTaskStatus, '/api/agent/<string:agent_name>/task/status')
# Output: {"status": "status"}

# Chains
api.add_resource(GetChains, '/api/chain')
# Output: {chain_name: {step_number: {prompt_type: prompt}}}
api.add_resource(GetChain, '/api/chain/<string:chain_name>')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(AddChain, '/api/chain')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(AddChainStep, '/api/chain/<string:chain_name>/step')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(UpdateStep, '/api/chain/<string:chain_name>/step/<string:step_number>')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(DeleteChain, '/api/chain/<string:chain_name>')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(DeleteChainStep, '/api/chain/<string:chain_name>/step/<string:step_number>')
# Output: {step_number: {prompt_type: prompt}}
api.add_resource(RunChain, '/api/chain/<string:chain_name>/run')
# Output: {step_number: {prompt_type: prompt}}

if __name__ == '__main__':
    app.run(debug=True)
