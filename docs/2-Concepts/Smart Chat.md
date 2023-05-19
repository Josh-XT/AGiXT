# Smart Chat
"Smart Chat" is an advanced feature of the AGiXT software that integrates artificial intelligence with web research to deliver highly accurate and contextually relevant responses to user prompts. It initiates with user interaction, followed by strategic web searches conducted by an AI agent. The agent then scrapes and analyses data from the web, recursively learning and exploring until it gathers enough information. This knowledge is then used to generate potential task solutions, which are evaluated and refined through multiple AI modules. The result is a carefully crafted solution that not only addresses the user's original prompt but also incorporates the most recent and pertinent data from the web, ensuring a comprehensive and informed response.

## Important Notice About Small Context Models!
Small context models are not good at doing things like this.  A small context model is anything with less than 4000 max tokens, and even at 4000 tokens, depending on the complexity of your task, it may not be enough. See [Core Concepts](https://josh-xt.github.io/AGiXT/2-Concepts/0-Core%20Concepts.html) for more information.

## Overview
1. **User Interaction**: A user begins the process by providing a chat prompt - a question, instruction, or request. They also have the option to upload a file, such as a PDF or Excel document, which the software can use as additional data for its operations.

2. **Search Strategy Development**: The Web Search Agent AI, a specialized component of the software, analyzes the user's input and determines five key topics or areas to search the web for. These topics are identified based on their potential relevance in addressing the user's prompt effectively.

3. **Web Exploration**: The Web Search Agent AI conducts searches on DuckDuckGo, a privacy-centric search engine, using the identified topics. It aims to retrieve pertinent information from five distinct websites suggested by the AI.

4. **Data Scraping and Recursive Learning**: The Web Search Agent AI scrapes text and extracts hyperlinks from each webpage. This data is then fed back into the AI, which assesses the relevance of the links. If any of the links are determined to be potentially valuable, the AI clicks on them and continues the scraping process on the new page. This recursive browsing continues until the AI has gathered sufficient information.

5. **Contextualization and Task Generation**: The Chat Agent, another module of the software, incorporates the learned information from the web research into its understanding of the user's initial prompt. It then generates three potential ways to complete the task the user has requested.

6. **Quality Assessment**: The Research Agent, a component designed to evaluate the outputs of the Chat Agent, analyzes the three proposed solutions. It identifies any potential flaws, drawbacks, or issues in each solution, providing a deeper layer of context for the next step in the process.

7. **Solution Refinement**: The Solution Agent uses the outputs of the Research Agent to refine the solutions. It crafts an optimized solution that addresses the user's prompt, taking into account the feedback and additional context provided by the Research Agent.

8. **Final Output Delivery**: The final step of the process involves delivering the Solution Agent's response to the user. This output represents the software's best answer or solution to the original task, informed by thorough web research, iterative task generation, and diligent solution refinement. 
