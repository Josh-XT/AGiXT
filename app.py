from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restplus import Api, Resource
from babyagi import babyagi
from AgentLLM import AgentLLM

app = Flask(__name__)
CORS(app)
api = Api(app, version='1.0', title='Task Management API', description='A simple API for managing tasks')

babyagi_instance = babyagi()

tasks_ns = api.namespace('api', description='Task-related operations')

@tasks_ns.route('/instruct')
class Instruct(Resource):
    @api.doc(params={'prompt': 'Your prompt', 'data': 'Your data'})
    @api.response(200, 'Success')
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

@tasks_ns.route('/set_objective')
class SetObjective(Resource):
    @api.doc(params={'objective': 'Your objective'})
    @api.response(200, 'Objective updated')
    def post(self):
        objective = request.json.get("objective")
        babyagi_instance.set_objective(objective)
        return jsonify({"message": "Objective updated"}), 200

@tasks_ns.route('/add_initial_task')
class AddInitialTask(Resource):
    @api.response(200, 'Initial task added')
    def post(self):
        babyagi_instance.add_initial_task()
        return jsonify({"message": "Initial task added"}), 200

@tasks_ns.route('/execute_next_task')
class ExecuteNextTask(Resource):
    @api.response(200, 'Success')
    def get(self):
        task = babyagi_instance.execute_next_task()
        task_list = list(babyagi_instance.task_list)
        if task:
            return jsonify({"task": task, "result": babyagi_instance.response, "task_list": task_list}), 200
        else:
            return jsonify({"message": "All tasks complete"}), 200

@tasks_ns.route('/create_task')
class CreateTask(Resource):
    @api.doc(params={'objective': 'Your objective', 'result': 'Task result', 'task_description': 'Task description', 'task_list': 'Task list'})
    @api.response(200, 'Success')
    def post(self):
        objective = request.json.get("objective")
        result = request.json.get("result")
        task_description = request.json.get("task_description")
        task_list = request.json.get("task_list")
        new_tasks = babyagi_instance.task_creation_agent(objective, result, task_description, task_list)
        return jsonify({"new_tasks": new_tasks}), 200

@tasks_ns.route('/prioritize_tasks')
class PrioritizeTasks(Resource):
    @api.doc(params={'task_id': 'Task ID'})
    @api.response(200, 'Success')
    def post(self):
        task_id = request.json.get("task_id")
        babyagi_instance.prioritization_agent(task_id)
        return jsonify({"task_list": babyagi_instance.task_list}), 200

@tasks_ns.route('/execute_task')
class ExecuteTask(Resource):
    @api.doc(params={'objective': 'Your objective', 'task': 'Task to execute'})
    @api.response(200, 'Success')
    def post(self):
        objective = request.json.get("objective")
        task = request.json.get("task")
        result = babyagi_instance.execution_agent(objective, task)
        return jsonify({"result": result}), 200

if __name__ == '__main__':
    app.run(debug=True)
