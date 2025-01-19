# Extension Commands

Commands are functions that can be executed by the agent. They are defined in the `commands` section of the agent configuration file. The agent will execute the commands in the order they are defined in the configuration file. The agent will wait for the command to complete before executing the next command. If a command fails, the agent will take the failure message and then ask the Agent what to do about the message to fix it, then attempts to execute again until the Agent works out the issues they're having with executing commands.

## Core Automation & Integration

1. **Web Browsing & Automation**
   - *Real-world scenario:* Imagine you need to monitor product prices across multiple e-commerce sites. Instead of manually checking each site, AGiXT can automate this process, navigate through the sites, extract pricing data, and notify you of changes.
   - *Use case:* "The agent can log into your supplier portals, check inventory levels, and automatically create purchase orders when stock runs low."

2. **Database Integrations**
   - *Real-world scenario:* You need to analyze customer purchase patterns but don't know SQL. Simply ask "Show me which products are most popular on weekends" and AGiXT translates this to proper SQL queries.
   - *Use case:* "Instead of writing complex JOIN statements, just tell the agent 'Find all customers who bought product X but haven't made a purchase in 6 months' and it handles the query construction."

3. **AI-Enhanced GitHub Integration**
   - *Real-world scenario:* Your team uses GitHub for project management. Rather than switching between platforms, you can say "Create an issue for updating the login page validation and assign it to Sarah" - AGiXT handles the creation and assignment.
   - *Use case:* "When a bug is reported, the agent can analyze the code, create a new branch, implement a fix, and create a pull request with detailed documentation of the changes."

4. **Cloud Platform Integration**
   - *Real-world scenario:* Managing calendar invites across teams can be tedious. Tell AGiXT "Schedule a project review meeting with the development team next week when everyone is available" and it checks calendars and sends invites.
   - *Use case:* "The agent can monitor your inbox for specific types of requests, automatically create tasks in your project management system, and schedule follow-up meetings."

### Data Management & Analysis

1. **Long-Term Memory System**
   - *Real-world scenario:* During project discussions, important decisions are made. AGiXT can store these decisions with context, so months later when you ask "Why did we choose MongoDB over PostgreSQL?" it can provide the complete reasoning.
   - *Use case:* "The agent maintains a knowledge base of all project decisions, technical documentation, and meeting outcomes, making it searchable and contextually relevant."

2. **File System Management**
   - *Real-world scenario:* Your development team has a specific way of organizing project files. AGiXT can automatically organize new files, enforce naming conventions, and maintain project structure.
   - *Use case:* "When you save new source code files, the agent can automatically format them according to team standards, update documentation, and organize related test files."

### Development & Creation Tools

1. **3D Modeling Integration**
   - *Real-world scenario:* You need to create a custom enclosure for a circuit board. Instead of learning OpenSCAD, describe what you need: "Create a box with ventilation holes that fits a 100x50mm board with mounting points" - AGiXT generates the model.
   - *Use case:* "The agent can take natural language descriptions of physical objects and convert them into precise 3D models ready for printing."

2. **GraphQL Integration**
   - *Real-world scenario:* Instead of writing complex GraphQL queries, tell AGiXT "Get me all users who posted comments last week with their profile pictures" and it constructs the appropriate query.
   - *Use case:* "The agent can handle complex data requirements by constructing optimized queries, managing pagination, and handling error cases."

### Communication & External Services

1. **Email Integration**
   - *Real-world scenario:* You need to send weekly progress updates to stakeholders. AGiXT can automatically compile project updates from various sources, create a well-formatted email, and send it to the right people.
   - *Use case:* "The agent can monitor project milestones, generate status reports, and send customized updates to different stakeholder groups automatically."

2. **Search & Research**
   - *Real-world scenario:* When researching a new technology stack, instead of manually searching and comparing, ask AGiXT "Find recent papers and discussions about microservices vs monolithic architectures in high-traffic applications."
   - *Use case:* "The agent can conduct comprehensive research across multiple sources, synthesize the information, and present a detailed analysis with citations."

These practical examples demonstrate how AGiXT's extensions work together to automate complex workflows that would typically require multiple tools and manual intervention. The system's strength lies in its ability to understand natural language instructions and translate them into specific actions across various platforms and services.

For example, a single request like "Set up a new feature development cycle for the user authentication system" could trigger AGiXT to:

1. Create a new GitHub project board
2. Generate relevant issues and assign team members
3. Schedule a kickoff meeting based on team availability
4. Create documentation templates
5. Set up necessary development branches
6. Send notification emails to stakeholders

This integrated approach significantly reduces the time spent on administrative tasks and allows teams to focus on their core work while maintaining consistent processes and documentation.

## Recommendations

### Enable commands per agent sparingly!

Agent should only be given commands to access what they **need** to access to complete their task.  If you give them more than they need, you are likely to cause `hallucinations`, which is when the agent starts to generate responses that are not relevant to the task at hand.  This is because the agent has too much information to work with and is unable to focus on the task at hand.  Think about it like this: if you were given a task to complete, but you were given a bunch of other tasks to complete at the same time, you would likely get confused and not be able to complete any of the tasks.  This is what happens to the agent when you give it too many commands to execute.

If you enable **all** commands on any agent, you're likely to get very poor results.

### Want to make your own commands and extensions?

You don't even need to be a developer! There is a command for that! Just give your agent the `Create a new command` command and tell it what new command you want it to make, it will create a new command file in the `commands` folder and any commands inside of the file will be available in Agent Settings to enable if you choose to do so.
