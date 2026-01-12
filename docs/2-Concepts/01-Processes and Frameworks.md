Since AGiXT is designed to build customizable and extensible AI agents, there are different services to satisfy the goal. In the web UI of AGiXT, you will see the services that include Agent Management, Agent Training, Agent Interactions, Memory Management, Prompt Management, and Chains Management.

## Agent Management

This service is dedicated to managing the agent such as agent settings that you can find more details in [Agents](03-Agents.md) section. The agent settings part modifies the settings in text generation models based on the available [Providers](02-Providers.md). Moreover, you can configure which extension commands are enabled for the agent, allowing it to perform actions like searching the web, executing code, or interacting with external services. Applying these settings to the agent makes the agent more aligned with the user's expectations.

## Agent Training

The agent can train based on the additional resources provided to it. These resources include websites, different file formats, text (i.e., a pair of question and answer that the user provides), and GitHub repositories. You can find more details about these training modes in [Agent Training](09-Agent%20Training.md) section.

Training creates vector embeddings of the content, which are stored in memory collections. During conversations, the agent automatically retrieves relevant memories based on the user's input to provide informed, contextual responses.

In addition to the fundamental settings for agent training, the user can provide more advanced options such as predefined memory collections that can be used by developers. These options include storing the web search results, positive/negative feedback, etc.

## Agent Interactions

All agent interactions go through the unified `/v1/chat/completions` endpoint, which provides a single intelligent pipeline for all conversations. The system automatically:

1. **Assembles context** from memories, conversation history, and uploads
2. **Analyzes complexity** to determine appropriate reasoning depth
3. **Executes the thinking/acting loop** where the agent reasons and uses commands as needed
4. **Streams responses** in real-time with activities and the final answer

You can find more details about interaction options and advanced configuration in [Agent Interactions](10-Agent%20Interactions.md) section.

## Memory Management

The agent automatically searches relevant memories during every conversation. When you send a message, the system:

1. Queries vector memories based on your input
2. Retrieves recent conversation context
3. Includes uploaded files and activities
4. Assembles everything into a coherent context

You can manage memory collections, view stored memories, and control how many results are injected into conversations. See [Agent Training](09-Agent%20Training.md) for more details.

Advanced options for memory management include predefined memory collections, number of the output memories, and the minimum relevance score for a memory to be returned.

## Prompt Management

This feature helps in managing the prompts when working with the agents. Prompt management assists in creating, editing, and deleting prompts, or even changing them to conversations. You can learn more about it in [Prompts](06-Prompts.md) section. There are also more details about the conversations in [Conversations](07-Conversations.md).

Prompts support injection variables that are automatically filled with context like `{user_input}`, `{context}`, `{conversation_history}`, and `{COMMANDS}` for available agent commands.

## Chains Management

Chains are predefined multi-step workflows that orchestrate agent actions. Each step can run a prompt, execute a command, or call another chain. The output of each step flows to the next via `{step1}`, `{step2}`, etc. variables.

You can learn more about chains and predefined variables in [Chains](08-Chains.md).

In addition to the details listed, there are some advanced options including running single steps, starting from a specific step, and showing all intermediate responses.
