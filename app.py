from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restful import Api, Resource
from flasgger import Swagger
from babyagi import babyagi
from AgentLLM import AgentLLM

app = Flask(__name__)
CORS(app)
api = Api(app)
swagger = Swagger(app)

babyagi_instance = babyagi()

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

api.add_resource(Instruct, '/instruct')
api.add_resource(SetObjective, '/set_objective')
api.add_resource(AddInitialTask, '/add_initial_task')
api.add_resource(ExecuteNextTask, '/execute_next_task')
api.add_resource(CreateTask, '/create_task')
api.add_resource(PrioritizeTasks, '/prioritize_tasks')
api.add_resource(ExecuteTask, '/execute_task')

if __name__ == '__main__':
    app.run(debug=True)