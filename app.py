import os
import shutil
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from babyagi import babyagi
from AgentLLM import AgentLLM
from Config import Config
from flask_restful import Api, Resource
from flask_swagger_ui import get_swaggerui_blueprint
from Commands import Commands

CFG = Config()
app = Flask(__name__)
CORS(app)
api = Api(app)

babyagi_instance = babyagi()

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
            commands_list = commands.get_commands_list()
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
            return jsonify({"message": f"Agent file {agent_file} not found."}), 404

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
        return {"agents": agents}, 200

class GetChatHistory(Resource):
    def get(self, agent_name):
        agent = AgentLLM()
        agent.CFG.AGENT_NAME = agent_name
        with open(os.path.join("agents", f"{agent_name}.yaml"), "r") as f:
            chat_history = f.read()
        return {"chat_history": chat_history}, 200

class Instruct(Resource):
    def post(self):
        agent_name = request.json.get("agent_name")
        objective = request.json.get("prompt")
        agent = AgentLLM()
        agent.CFG.AGENT_NAME = agent_name
        response = agent.run(objective, max_context_tokens=500, long_term_access=False)
        return {"response": str(response)}, 200

class SetObjective(Resource):
    def post(self):
        objective = request.json.get("objective")
        babyagi_instance.set_objective(objective)
        return {"message": "Objective updated"}, 200

class AddInitialTask(Resource):
    def post(self):
        babyagi_instance.add_initial_task()
        return {"message": "Initial task added"}, 200

class ExecuteNextTask(Resource):
    def get(self):
        task = babyagi_instance.execute_next_task()
        task_list = list(babyagi_instance.task_list)
        if task:
            return {"task": task, "result": babyagi_instance.response, "task_list": task_list}, 200
        else:
            return {"message": "All tasks complete"}, 200

class CreateTask(Resource):
    def post(self):
        objective = request.json.get("objective")
        result = request.json.get("result")
        task_description = request.json.get("task_description")
        task_list = request.json.get("task_list")
        new_tasks = babyagi_instance.task_creation_agent(objective, result, task_description, task_list)
        return {"new_tasks": new_tasks}, 200

class PrioritizeTasks(Resource):
    def post(self):
        task_id = request.json.get("task_id")
        babyagi_instance.prioritization_agent(task_id)
        return {"task_list": babyagi_instance.task_list}, 200

class ExecuteTask(Resource):
    def post(self):
        objective = request.json.get("objective")
        task = request.json.get("task")
        result = babyagi_instance.execution_agent(objective, task)
        return {"result": result}, 200

class GetCommands(Resource):
    def get(self):
        commands = Commands()
        commands_list = commands.get_commands_list()
        return jsonify({"commands": commands_list}, 200)
    
class GetAvailableCommands(Resource):
    def get(self, agent_name):
        available_commands = Commands(agent_name).get_available_commands()
        return jsonify({"available_commands": available_commands}, 200)

class EnableCommand(Resource):
    def post(self, agent_name, command_name):
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "true"
        with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
            json.dump(commands.agent_config, agent_config)
        return jsonify({"message": f"Command '{command_name}' enabled for agent '{agent_name}'."}, 200)

class DisableCommand(Resource):
    def post(self, agent_name, command_name):
        commands = Commands(agent_name)
        commands.agent_config["commands"][command_name] = "false"
        with open(os.path.join("agents", agent_name, "config.json"), "w") as agent_config:
            json.dump(commands.agent_config, agent_config)
        return jsonify({"message": f"Command '{command_name}' disabled for agent '{agent_name}'."}, 200)

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

api.add_resource(AddAgent, '/api/add_agent/<string:agent_name>')
api.add_resource(DeleteAgent, '/api/delete_agent/<string:agent_name>')
api.add_resource(GetAgents, '/api/get_agents')
api.add_resource(GetChatHistory, '/api/get_chat_history/<string:agent_name>')
api.add_resource(Instruct, '/api/instruct')
api.add_resource(SetObjective, '/api/set_objective')
api.add_resource(AddInitialTask, '/api/add_initial_task')
api.add_resource(ExecuteNextTask, '/api/execute_next_task')
api.add_resource(CreateTask, '/api/create_task')
api.add_resource(PrioritizeTasks, '/api/prioritize_tasks')
api.add_resource(ExecuteTask, '/api/execute_task')
api.add_resource(GetCommands, '/api/get_commands')
api.add_resource(GetAvailableCommands, '/api/get_available_commands/<string:agent_name>')
api.add_resource(EnableCommand, '/api/enable_command/<string:agent_name>/<string:command_name>')
api.add_resource(DisableCommand, '/api/disable_command/<string:agent_name>/<string:command_name>')
api.add_resource(DisableAllCommands, '/api/disable_all_commands/<string:agent_name>')
api.add_resource(EnableAllCommands, '/api/enable_all_commands/<string:agent_name>')

if __name__ == '__main__':
    app.run(debug=True)
