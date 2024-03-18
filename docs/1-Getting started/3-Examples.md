# Examples
We plan to build more examples but would love to see what you build with AGiXT.  If you have an example you would like to share, please submit a pull request to add it to this page.

## Chatbot Example
Example of a basic AGiXT chatbot:  Set your agent, make it learn whichever urls or files you want, then just keep using that conversation ID to keep a conversation going with the AI where it is aware of the history of your conversation (last 5 interactions).  If you want to keep talking to it about the same docs without the history, start a new conversation and keep going with the same agent without any retraining of the documentation. Any conversations you have with the AI will be saved in the `agixt/conversations` directory and will also be viewable from inside of the AGiXT Streamlit Web UI.

You can open this file in a Jupyter Notebook and run the code cells to see the example in action. https://github.com/Josh-XT/AGiXT/blob/main/examples/Chatbot.ipynb

## Voice Chat Example
Example of a basic AGiXT voice chat: Make the agent listen to you saying a specific word that makes it take what you say, send it to the agent, and then execute an AGiXT function. In this example, you can use two different wake functions, `chat` and `instruct`. When this example is running, and you say each of the wake words, it will take the words you say after that, send them to the agent, and respond back to you with an audio response.

You can open this file in a Jupyter Notebook and run the code cells to see the example in action. https://github.com/Josh-XT/AGiXT/blob/main/examples/Voice.ipynb

## Some Examples of Useful Chains

- [Smart Chat](https://josh-xt.github.io/AGiXT/2-Concepts/Smart%20Chat.html)
- [Smart Instruct](https://josh-xt.github.io/AGiXT/2-Concepts/Smart%20Instruct.html)
- [Smart Task Chain](https://josh-xt.github.io/AGiXT/2-Concepts/Smart%20Task%20Chains.html)
- [Task Chain](https://josh-xt.github.io/AGiXT/2-Concepts/Task%20Chains.html)
