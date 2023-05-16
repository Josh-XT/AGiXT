## Building Prompts for Plugin System

This README file provides the necessary information for building prompts for the Plugin System. See also [Prompts](../Concepts/PROMPT.md)
### Plugin Overview

The Plugin System uses prompts to provide instructions to different AI agents. Each prompt is a text file that contains a specific format for providing instructions. There are four types of prompts that the Plugin System uses. They are as follows:
1. model-prompts/{model}/execute.txt
2. model-prompts/{model}/priority.txt
3. model-prompts/{model}/system.txt
4. model-prompts/{model}/task.txt
5. model-prompts/{model}/script.txt
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
#### system.txt

The `system.txt` prompt is used to instruct an AI agent have commands to use. The format for the `system.txt` prompt is as follows:

```css

You are an AI language model. Your name is {AGENT_NAME}. Your role is to do anything asked of you with precision. You have the following constraints:
1. ~4000 word limit for short term memory. Your short term memory is short, so immediately save important information to files.
2. If you are unsure how you previously did something or want to recall past events, thinking about similar events will help you remember.
3. No user assistance.
4. Exclusively use the commands listed in double quotes e.g. "command name".

You have the following resources:
1. Internet access for searches and information gathering.
2. Long Term memory management.
3. GPT-3.5 powered Agents for delegation of simple tasks.
4. File output.

You have the following commands available:
{COMMANDS}
```


The `{AGENT_NAME}` field is the Agent name so that it knows who it is. The `{COMMANDS}` field dumps the listing of commands that the AI will have to choose from for use.
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

#### script.txt

```sql
You write new commands for this framework. Ensure commands summaries are short and concise in self.commands. Do not explain, only provide code.
from typing import List
from Commands import Commands
from AgentLLM import AgentLLM

class code_evaluation(Commands):
    def __init__(self):
        self.commands = {
            "Evaluate Code": self.evaluate_code
        }

    def evaluate_code(self, code: str) -> List[str]:
        args = [code]
        function_string = "def analyze_code(code: str) -> List[str]:"
        description_string = "Analyzes the given code and returns a list of suggestions for improvements."
        prompt = f"You are now the following python function: ```# {description_string}\n{function_string}```\n\nOnly respond with your `return` value. Args: {args}"
        return AgentLLM().run(prompt, commands_enabled=False)
```

### Conclusion

This README file provided an overview of the Plugin System and the four types of prompts used to instruct AI agents. It also provided the format for each prompt type.

When building prompts for the Plugin System, make sure to follow the specific format for each prompt type. This will ensure that the AI agents can interpret the instructions correctly.

In addition to the prompt format, it is also important to provide clear and concise instructions for the AI agents. Make sure to use simple language and avoid ambiguity.

By following these guidelines, you can build effective prompts for the Plugin System that will help the AI agents accomplish their tasks successfully.
