from flask import Flask, request, jsonify
from flask_cors import CORS
from babyagi import babyagi
from AgentLLM import AgentLLM
app = Flask(__name__)
CORS(app)  # Add this line to enable CORS for your Flask application
babyagi_instance = babyagi()

# Instruct Agent-LLM
@app.route('/api/instruct', methods=['POST'])
def instruct():
    objective = request.json.get("prompt")
    data = request.json.get("data")
    agent = AgentLLM()
    agent.CFG.AGENT_NAME = data["agent_name"]
    agent.CFG.COMMANDS_ENABLED = data["commands_enabled"]
    agent.CFG.AI_PROVIDER = data["ai_provider"]
    agent.CFG.OPENAI_API_KEY = data["openai_api_key"]
    response = agent.run(objective, max_context_tokens=500, long_term_access=False)
    return jsonify({"response": response}), 200

@app.route('/api/set_objective', methods=['POST'])
def set_objective():
    objective = request.json.get("objective")
    babyagi_instance.set_objective(objective)
    return jsonify({"message": "Objective updated"}), 200

@app.route('/api/add_initial_task', methods=['POST'])
def add_initial_task():
    babyagi_instance.add_initial_task()
    return jsonify({"message": "Initial task added"}), 200

@app.route('/api/execute_next_task', methods=['GET'])
def execute_next_task():
    task = babyagi_instance.execute_next_task()
    task_list = list(babyagi_instance.task_list)  # Convert deque to a list
    if task:
        return jsonify({"task": task, "result": babyagi_instance.response, "task_list": task_list}), 200
    else:
        return jsonify({"message": "All tasks complete"}), 200

@app.route('/api/create_task', methods=['POST'])
def create_task():
    objective = request.json.get("objective")
    result = request.json.get("result")
    task_description = request.json.get("task_description")
    task_list = request.json.get("task_list")
    new_tasks = babyagi_instance.task_creation_agent(objective, result, task_description, task_list)
    return jsonify({"new_tasks": new_tasks}), 200

@app.route('/api/prioritize_tasks', methods=['POST'])
def prioritize_tasks():
    task_id = request.json.get("task_id")
    babyagi_instance.prioritization_agent(task_id)
    return jsonify({"task_list": babyagi_instance.task_list}), 200

@app.route('/api/execute_task', methods=['POST'])
def execute_task():
    objective = request.json.get("objective")
    task = request.json.get("task")
    result = babyagi_instance.execution_agent(objective, task)
    return jsonify({"result": result}), 200

if __name__ == '__main__':
    app.run(debug=True)
