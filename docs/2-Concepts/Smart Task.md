# Smart Tasks
The Smart Task process is an intelligent system that dynamically manages tasks through a series of AI-driven agents. It starts with a user-defined objective, which is then broken down into subtasks by the Task Agent. These subtasks are methodically executed using a loop structure that employs a Smart Instruct process. This process involves a suite of agents including a Web Search Agent for information gathering, an Instruction Agent for generating potential solutions, a Research Agent for analyzing these solutions, a Solution Agent for determining the best course of action, and finally an Execution Agent for carrying out the necessary commands. The task list is continually reprioritized to optimize efficiency and prevent redundancy. The final output of the Smart Task process is a comprehensive solution to the user's initial objective, encompassing an explanation from the Solution Agent and the results of the executed commands from the Execution Agent. The Smart Task process exemplifies an innovative application of AI in task management, demonstrating a high level of responsiveness to user input and adaptability to evolving task requirements.

## Important Notice About Small Context Models!
Small context models are not good at doing things like this.  A small context model is anything with less than 4000 max tokens, and even at 4000 tokens, depending on the complexity of your task, it may not be enough. See [Core Concepts](https://josh-xt.github.io/AGiXT/2-Concepts/0-Core%20Concepts.html) for more information.

## Overview
1. **Task Definition:** The user provides the LLM with a specific task to accomplish. This task serves as the objective that the LLM will work towards.

2. **Task Breakdown:** The Task Agent, an AI component, analyzes the main task and generates a list of subtasks necessary for its completion. 

3. **Task Execution Loop:** The Task Agent enters a loop where it utilizes a Smart Instruct process for each subtask. 

4. **Task Prioritization:** After the completion of each subtask, the AI reevaluates and reprioritizes the remaining tasks. This helps in minimizing redundancy and overlapping work.

5. **Loop Continuation:** The process continues, looping back to the Smart Instruct step until all the tasks in the list are completed.

Within this process, the Smart Instruct system is responsible for completing individual tasks. See the [Smart Instruct Documentation](https://josh-xt.github.io/AGiXT/2-Concepts/Smart%20Instruct.html) for more information.