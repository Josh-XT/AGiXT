## Building Prompts for Plugin System

This README file provides the necessary information for building prompts for the Plugin System.
### Plugin Overview

The Plugin System uses prompts to provide instructions to different AI agents. Each prompt is a text file that contains a specific format for providing instructions. There are four types of prompts that the Plugin System uses. They are as follows:
1. execute.txt
2. priority.txt
3. script.txt
4. task.txt
### Prompt Formats

Each prompt has a specific format for providing instructions to the AI agents. The following section explains the format for each prompt type.
#### execute.txt

The `execute.txt` prompt is used to instruct an AI agent to perform a specific task. The format for the `execute.txt` prompt is as follows:

```vbnet

You are an AI who performs one task based on the following objective: {objective}.
Take into account these previously completed tasks: {context}.
Your task: {task}
Response:
```

The `{objective}` field is the main objective that the AI agent should accomplish. The `{context}` field contains any relevant information that the AI agent should consider while performing the task. The `{task}` field is the specific task that the AI agent should perform.
#### priority.txt

The `priority.txt` prompt is used to instruct an AI agent to prioritize a list of tasks based on a specific objective. The format for the `priority.txt` prompt is as follows:

```sql

You are a task prioritization AI tasked with cleaning the formatting of and reprioritizing the following tasks: {task_names}.
Consider the ultimate objective of your team:{objective}.
Do not remove any tasks. Return the result as a numbered list, like:
#. First task
#. Second task
Start the task list with number {next_task_id}.
```



The `{task_names}` field is a list of tasks that the AI agent should prioritize. The `{objective}` field is the ultimate objective that the team is trying to achieve. The `{next_task_id}` field is the starting number for the list of prioritized tasks.
#### script.txt

The `script.txt` prompt is used to instruct an AI agent to write a Python script that accomplishes a specific task. The format for the `script.txt` prompt is as follows:

```css

With the primary objective being: {objective}.
Use selenium, webdriver_manager with chromedriver if browsing the web is required.
1. Write a Python script to help accomplish this task: {task}.
2. Short summary of the intention of the script.
3. Suggested unique file name for the script.
```



The `{objective}` field is the primary objective that the Python script should accomplish. The `{task}` field is the specific task that the Python script should help accomplish.
#### task.txt

The `task.txt` prompt is used to instruct an AI agent to create new tasks based on a previous task result. The format for the `task.txt` prompt is as follows:

```sql

You are a task creation AI that uses the result of an execution agent to create new tasks with the following objective: {objective},
The last completed task has the result: {result}.
This result was based on this task description: {task_description}. These are incomplete tasks: {tasks}.
Based on the result, create new tasks to be completed by the AI system that do not overlap with incomplete tasks.
Return the tasks as an array.
```



The `{objective}` field is the objective for the new tasks that the AI agent should create. The `{result}` field is the result of the previous task. The `{task_description}` field is the description of the previous task. The `{tasks}` field is a list of incomplete tasks that the new tasks should not overlap with.
### Conclusion

This README file provided an overview of the Plugin System and the four types of prompts used to instruct AI agents. It also provided the format for each prompt type.

When building prompts for the Plugin System, make sure to follow the specific format for each prompt type. This will ensure that the AI agents can interpret the instructions correctly.

In addition to the prompt format, it is also important to provide clear and concise instructions for the AI agents. Make sure to use simple language and avoid ambiguity.

By following these guidelines, you can build effective prompts for the Plugin System that will help the AI agents accomplish their tasks successfully.
