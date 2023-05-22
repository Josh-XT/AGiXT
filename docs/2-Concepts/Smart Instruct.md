# Smart Instruct
"Smart Instruct" is an advanced feature of the AGiXT software that integrates artificial intelligence designed to comprehend, plan, and execute tasks efficiently. It starts with an instruction from the user, which the system breaks down and analyzes. Leveraging the power of web search, the system seeks out relevant information to understand the task at hand thoroughly. It then formulates multiple strategies, evaluates them for any potential issues, and fine-tunes the best possible solution. This solution is then executed via a series of commands, with each output monitored for accuracy. The process concludes with a detailed report on the task's execution, providing a comprehensive overview of the journey from instruction to completion. "Smart Instruct" truly embodies the synergy of artificial intelligence and the internet, offering an intelligent, adaptive, and reliable approach to task completion.

## Important Notice About Small Context Models!
Small context models are not good at doing things like this.  A small context model is anything with less than 4000 max tokens, and even at 4000 tokens, depending on the complexity of your task, it may not be enough. See [Core Concepts](https://josh-xt.github.io/AGiXT/2-Concepts/0-Core%20Concepts.html) for more information.

## Overview
1. **Instruction Acquisition:** The process begins with the user providing the initial instruction or task. This instruction serves as the base for the entire process, determining the direction of the subsequent steps.

2. **Search Strategy Determination:** The Web Search Agent AI takes the initial instruction and determines five key search topics that will assist in task completion. These topics are generated based on the AI's understanding of the instruction and its knowledge about the information needed to accomplish it.

3. **Web Search:** The Web Search Agent then conducts searches on DuckDuckGo for the five identified topics. It identifies relevant websites, pulling in a wealth of information from the web related to the task at hand.

4. **Website Scrutiny:** The Web Search Agent meticulously navigates each page, scraping text and links for information. The AI evaluates the scraped content to identify any relevant links, clicking on these links and further exploring their content. This recursive process continues until the AI has sufficiently canvassed the web and gathered all necessary information.

5. **Instruction Generation:** The Instruction Agent integrates the information learned from the web research into the context of the task. It then formulates three potential approaches to complete the task based on the initial instruction and the newly acquired knowledge. During this stage, the AI does not execute any commands, but rather formulates potential plans of action.

6. **Research Review:** The Research Agent reviews the three proposed solutions from the Instruction Agent. It critically evaluates each solution for potential flaws or issues. This assessment provides an additional layer of context, ensuring the final solution is as robust and foolproof as possible.

7. **Solution Formulation:** Based on the feedback from the Research Agent, the Solution Agent devises the optimal solution. This solution incorporates all the insights from the previous stages, resulting in an approach that is most likely to successfully complete the task.

8. **Command Execution:** The Execution Agent identifies the specific commands included in the Solution Agent's proposed solution. It then executes these commands one by one, checking after each execution to ensure the output matches the expected results. The agent repeats this process until the task is accomplished as intended.

9. **Final Output:** The process culminates with the delivery of the final output. This includes both the detailed explanation from the Solution Agent on how the task was accomplished, as well as the specific command outputs from the Execution Agent. The user is thus provided with a comprehensive view of the task completion process.

This process ultimately leverages AI's ability to research, analyze, plan, and execute tasks, creating a robust and intelligent system for task completion.