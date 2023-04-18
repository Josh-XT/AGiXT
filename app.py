import os
import shutil
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restful import Api, Resource
from flasgger import Swagger
from babyagi import babyagi
from AgentLLM import AgentLLM
from Config import Config
CFG = Config()
app = Flask(__name__)
CORS(app)
api = Api(app)
swagger = Swagger(app)

babyagi_instance = babyagi()

class AddAgent(Resource):
    def post(self, agent_name):
        memories_dir = "memories"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        # Check if the agent name already exists and append an increment if necessary
        i = 0
        agent_file = f"{agent_name}.yaml"
        while os.path.exists(os.path.join(memories_dir, agent_file)):
            i += 1
            agent_file = f"{agent_name}_{i}.yaml"
        # Create the new agent YAML file
        with open(os.path.join(memories_dir, agent_file), "w") as f:
            f.write("")
        return jsonify({"message": "Agent added", "agent_file": agent_file}), 200

class DeleteAgent(Resource):
    def delete(self, agent_name):
        memories_dir = "memories"
        agent_file = f"{agent_name}.yaml"
        agent_folder = os.path.join(memories_dir, agent_file.split('.')[0])

        # Delete the agent YAML file
        try:
            os.remove(os.path.join(memories_dir, agent_file))
        except FileNotFoundError:
            return jsonify({"message": f"Agent file {agent_file} not found."}), 404

        # Delete the agent folder and all its contents
        if os.path.exists(agent_folder):
            shutil.rmtree(agent_folder)

        return jsonify({"message": f"Agent {agent_name} deleted."}), 200

class GetAgents(Resource):
    def get(self):
        agents_list = CFG.AGENTS
        if isinstance(agents_list, str):
            agents_list = [agents_list]
        # Extract agent names from the file paths
        agent_names = [os.path.basename(path).split('.')[0] for path in agents_list]
        return {"agents": agent_names}, 200

class GetChatHistory(Resource):
    def get(self, agent_name):
        agent = AgentLLM()
        agent.CFG.AGENT_NAME = agent_name
        # Get content of {agent_name}.yaml
        with open(os.path.join("memories", f"{agent_name}.yaml"), "r") as f:
            chat_history = f.read()
        return jsonify({"chat_history": chat_history}), 200

class Instruct(Resource):
    def post(self):
        objective = request.json.get("prompt")
        data = request.json.get("data")
        agent = AgentLLM()
        agent.CFG.AGENT_NAME = data["agent_name"]
        agent.CFG.COMMANDS_ENABLED = data["commands_enabled"]
        agent.CFG.AI_PROVIDER = data["ai_provider"]
        agent.CFG.OPENAI_API_KEY = data["openai_api_key"]
        response = agent.run(objective, max_context_tokens=500, long_term_access=False)
        return jsonify({"response": response}), 200

class SetObjective(Resource):
    def post(self):
        objective = request.json.get("objective")
        babyagi_instance.set_objective(objective)
        return jsonify({"message": "Objective updated"}), 200

class AddInitialTask(Resource):
    def post(self):
        babyagi_instance.add_initial_task()
        return jsonify({"message": "Initial task added"}), 200

class ExecuteNextTask(Resource):
    def get(self):
        task = babyagi_instance.execute_next_task()
        task_list = list(babyagi_instance.task_list)
        if task:
            return jsonify({"task": task, "result": babyagi_instance.response, "task_list": task_list}), 200
        else:
            return jsonify({"message": "All tasks complete"}), 200

class CreateTask(Resource):
    def post(self):
        objective = request.json.get("objective")
        result = request.json.get("result")
        task_description = request.json.get("task_description")
        task_list = request.json.get("task_list")
        new_tasks = babyagi_instance.task_creation_agent(objective, result, task_description, task_list)
        return jsonify({"new_tasks": new_tasks}), 200

class PrioritizeTasks(Resource):
    def post(self):
        task_id = request.json.get("task_id")
        babyagi_instance.prioritization_agent(task_id)
        return jsonify({"task_list": babyagi_instance.task_list}), 200

class ExecuteTask(Resource):
    def post(self):
        objective = request.json.get("objective")
        task = request.json.get("task")
        result = babyagi_instance.execution_agent(objective, task)
        return jsonify({"result": result}), 200

api.add_resource(AddAgent, '/api/add_agent/<string:agent_name>')
api.add_resource(DeleteAgent, '/api/delete_agent/<string:agent_name>')
api.add_resource(GetChatHistory, '/api/get_chat_history/<string:agent_name>')
api.add_resource(GetAgents, '/api/get_agents')
api.add_resource(Instruct, '/api/instruct')
api.add_resource(SetObjective, '/api/set_objective')
api.add_resource(AddInitialTask, '/api/add_initial_task')
api.add_resource(ExecuteNextTask, '/api/execute_next_task')
api.add_resource(CreateTask, '/api/create_task')
api.add_resource(PrioritizeTasks, '/api/prioritize_tasks')
api.add_resource(ExecuteTask, '/api/execute_task')

if __name__ == '__main__':
    app.run(debug=True)