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

class AddAgent(Resource):
    def post(self, agent_name):
        agent_info = CFG.add_agent(agent_name)
        return {"message": "Agent added", "agent_file": agent_info['agent_file']}, 200

class RenameAgent(Resource):
    def put(self, agent_name, new_name):
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
    
class GetCommands(Resource):
    def get(self, agent_name):
        commands = Commands(agent_name)
        available_commands = commands.get_available_commands()
        return {"commands": available_commands}, 200

class EnableCommand(Resource):
    def post(self, agent_name):
        command_name = request.json.get("command_name")
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "true"
        CFG.update_agent_config(agent_name, commands.agent_config)
        return {"message": f"Command '{command_name}' enabled for agent '{agent_name}'."}, 200

class DisableCommand(Resource):
    def post(self, agent_name):
        command_name = request.json.get("command_name")
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "false"
        CFG.update_agent_config(agent_name, commands.agent_config)
        return {"message": f"Command '{command_name}' disabled for agent '{agent_name}'."}, 200

class EnableAllCommands(Resource):
    def post(self, agent_name):
        try:
            commands = Commands(agent_name)
            for command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][command_name] = "true"
            CFG.update_agent_config(agent_name, commands.agent_config)
            return {"message": f"All commands enabled for agent '{agent_name}'."}, 200
        except Exception as e:
            return {"message": f"Error enabled all commands for agent '{agent_name}': {str(e)}"}, 500

class DisableAllCommands(Resource):
    def post(self, agent_name):
        try:
            commands = Commands(agent_name)
            for command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][command_name] = "false"
            CFG.update_agent_config(agent_name, commands.agent_config)
            return {"message": f"All commands disabled for agent '{agent_name}'."}, 200
        except Exception as e:
            return {"message": f"Error disabled all commands for agent '{agent_name}': {str(e)}"}, 500

class StartTaskAgent(Resource):
    def post(self, agent_name):
        objective = request.json.get("objective")
        if agent_name not in agent_instances:
            agent_instances[agent_name] = AgentLLM(agent_name)
        agent_instance = agent_instances[agent_name]
        agent_instance.set_agent_name(agent_name)
        agent_instance.set_objective(objective)
        agent_thread = threading.Thread(target=agent_instance.run_task)
        agent_thread.start()
        return {"message": "Task agent started"}, 200

class StopTaskAgent(Resource):
    def post(self, agent_name):
        if agent_name not in agent_instances:
            return {"message": "Task agent not found"}, 404
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

# Agents
api.add_resource(GetAgents, '/api/get_agents')
# Output: {"agents": ["agent1", "agent2", "agent3"]}
api.add_resource(AddAgent, '/api/add_agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' added"}
api.add_resource(RenameAgent, '/api/rename_agent/<string:old_agent_name>/<string:new_agent_name>')
# Output: {"message": "Agent 'agent1' renamed to 'agent2'"}
api.add_resource(DeleteAgent, '/api/delete_agent/<string:agent_name>')
# Output: {"message": "Agent 'agent1' deleted"}
api.add_resource(GetCommands, '/api/get_commands/<string:agent_name>')
# Output: {"commands": [ {"friendly_name": "Friendly Name", "name": "command1", "enabled": True}, {"friendly_name": "Friendly Name 2", "name": "command2", "enabled": False }]}
api.add_resource(EnableCommand, '/api/enable_command/<string:agent_name>')
# Output: {"message": "Command 'command1' enabled for agent 'agent1'"}
api.add_resource(DisableCommand, '/api/disable_command/<string:agent_name>')
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