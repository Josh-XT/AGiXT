# Smart Task Chains

Smart Task Chains are an advanced feature of the AGiXT software that enhances the functionality of Task Chains. In a Smart Task Chain, each task in the chain is treated as a Smart Instruct. This means that before the AI attempts each task, it first conducts a thorough research using web search, formulates strategies, evaluates them, and fine-tunes the best possible solution. This ensures that each step in the chain is not just completed, but completed in the best possible way.

## Important Notice About Small Context Models!

Small context models may struggle with complex Smart Task Chains. A small context model is anything with less than 4000 max tokens, and even at 4000 tokens, depending on the complexity of your task, it may not be enough. See Core Concepts for more information.

## Overview

1. **Objective Acquisition:** The process begins with the user providing the initial objective. This objective serves as the base for the entire process, determining the direction of the subsequent steps.

2. **Task Breakdown:** The Task Agent AI takes the initial objective and breaks it down into a sequence of tasks. These tasks are generated based on the AI's understanding of the objective and its knowledge about the steps needed to accomplish it.

3. **Smart Instruct Integration:** Each task in the chain is treated as a Smart Instruct. This means that before the AI attempts each task, it first conducts a thorough research using web search, formulates strategies, evaluates them, and fine-tunes the best possible solution.

4. **Task Execution:** The Execution Agent then executes each task in the chain in the order they appear. It checks after each execution to ensure the output matches the expected results. The agent repeats this process until the objective is accomplished as intended.

5. **Final Output:** The process culminates with the delivery of the final output. This includesboth the detailed explanation from the Task Agent on how the objective was accomplished, as well as the specific task outputs from the Execution Agent. The user is thus provided with a comprehensive view of the objective completion process.

This process ultimately leverages AI's ability to research, analyze, plan, and execute tasks, creating a robust and intelligent system for task completion. Smart Task Chains represent a combination of strategic planning and efficient execution, providing a comprehensive, intelligent, and reliable approach to achieving complex objectives.