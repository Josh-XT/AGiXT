# Extension Commands
Commands are functions that can be executed by the agent. They are defined in the `commands` section of the agent configuration file. The agent will execute the commands in the order they are defined in the configuration file. The agent will wait for the command to complete before executing the next command. If a command fails, the agent will take the failure message and then ask the Agent what to do about the message to fix it, then attempts to execute again until the Agent works out the issues they're having with executing commands.

## Recommendations
### Enable commands per agent sparingly!
Agent should only be given commands to access what they **need** to access to complete their task.  If you give them more than they need, you are likely to cause `hallucinations`, which is when the agent starts to generate responses that are not relevant to the task at hand.  This is because the agent has too much information to work with and is unable to focus on the task at hand.  Think about it like this: if you were given a task to complete, but you were given a bunch of other tasks to complete at the same time, you would likely get confused and not be able to complete any of the tasks.  This is what happens to the agent when you give it too many commands to execute.

If you enable **all** commands on any agent, you're likely to get very poor results.

### Run this in Docker or a Virtual Machine!
You're welcome to disregard this message, but if you do and the AI decides that the best course of action for its task is to build a command to format your entire computer, that is on you. The only restrictions the agents have are the ones you give them. If you give them access to your entire computer, they will use it.

### Want to make your own commands?
You don't even need to be a developer! There is a command for that! Just give your agent the `Create a new command` command and tell it what new command you want it to make, it will create a new command file in the `commands` folder and any commands inside of the file will be available in Agent Settings to enable if you choose to do so.

## Some Commands
This is not a full list of commands! These are just some examples. You can find all of the commands in the repository.  Each Extension file may have as many commands associated as needed.

- Ask AI Agent `AGENT_NAME`
- Instruct AI Agent `AGENT_NAME`
- Create a new command
- Scrape Text with Playwright
- Scrape Links with Playwright
- Generate Image
- Searx Search
- Read Audio from File
- Read Audio
- Speak with TTS
- Google Search
- Evaluate Code
- Analyze Pull Request
- Perform Automated Testing
- Run CI-CD Pipeline
- Improve Code
- Write Tests
- Clone Github Repository
- Create Github Repository
- Execute Python File
- Execute Shell
- Get Datetime
- Browse Website
- Is Valid URL
- Sanitize URL
- Check Local File Access
- Get Response
- Send Email with Sendgrid
- Send Tweet
- Check Duplicate Operation
- Read File
- Ingest File
- Write to File
- Append to File
- Delete File
- Search Files