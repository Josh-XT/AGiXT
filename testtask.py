from AgentLLM import AgentLLM
from collections import deque
def main():
    # Create an instance of the AgentLLM class
    agent = AgentLLM(primary_objective="Organize a birthday party")

    # Add initial tasks to the task list
    agent.task_list = deque([
        {"task_id": 1, "task_name": "Choose a venue for the party"},
        {"task_id": 2, "task_name": "Prepare a guest list"},
        {"task_id": 3, "task_name": "Decide on a theme for the party"},
    ])

    # Run the main loop to process tasks
    while agent.task_list:
        task = agent.task_list.popleft()
        print(f"Executing task {task['task_id']}: {task['task_name']}")
        result = agent.execution_agent(task["task_name"], task["task_id"])
        print(f"Task Result: {result}\n")

        new_tasks = agent.task_creation_agent({"data": result}, task["task_name"], [t["task_name"] for t in agent.task_list])
        for new_task in new_tasks:
            new_task.update({"task_id": len(agent.task_list) + 1})
            agent.task_list.append(new_task)

        agent.prioritization_agent()

    print("All tasks completed.")

if __name__ == "__main__":
    main()