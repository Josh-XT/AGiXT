# Task Chains

Task Chains are a feature of the AGiXT software that allows the AI to perform a series of tasks in a specific order to achieve a user-defined objective. The process begins with the user providing an objective, which the system breaks down into a sequence of tasks. Each task in the chain is executed in order, with the output of one task serving as the input for the next. This allows the AI to handle complex objectives that require multiple steps to complete.

## Important Notice About Small Context Models!
Small context models may struggle with complex Task Chains. A small context model is anything with less than 4000 max tokens, and even at 4000 tokens, depending on the complexity of your task, it may not be enough. See Core Concepts for more information.

## Overview
1. **Objective Acquisition:** The process begins with the user providing the initial objective. This objective serves as the base for the entire process, determining the direction of the subsequent steps.

2. **Task Breakdown:** The Task Agent AI takes the initial objective and breaks it down into a sequence of tasks. These tasks are generated based on the AI's understanding of the objective and its knowledge about the steps needed to accomplish it.

3. **Task Execution:** The Execution Agent then executes each task in the chain in the order they appear. It checks after each execution to ensure the output matches the expected results. The agent repeats this process until the objective is accomplished as intended.

4. **Final Output:** The process culminates with the delivery of the final output. This includes both the detailed explanation from the Task Agent on how the objective was accomplished, as well as the specific task outputs from the Execution Agent. The user is thus provided with a comprehensive view of the objective completion process.

This process ultimately leverages AI's ability to break down, analyze, plan, and execute tasks, creating a robust and intelligent system for objective completion.