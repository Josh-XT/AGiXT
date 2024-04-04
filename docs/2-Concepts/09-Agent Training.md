# Agent Training
AGiXT provides a flexible memory for agents allowing you to train them on any data you would like to be injected in context when interacting with the agent.

Training enables you to interact with just about any data with natural language.  You can train the agent on websites, files, and more.

## Website Training

Enter a website URL then click `Train from Website` to train the agent on the website.  The agent will scape the websites information into its long term memory.  This will allow the agent to answer questions about the website.

## File Training

The agent will accept zip files, any kind of plain text file, PDF files, CSV, XLSX, and more. The agent will read the files into its long term memory. This will allow the agent to answer questions about the files.

## Text Training

You can enter any text you would like to train the agent on.  There are two inputs for this mode.

The first input is `Enter some short text, description, or question to associate the learned text with.` which is the input that you will be associating your main text with.  For example, I would say `What is Josh's favorite color?` in this box, then `Yellow` in the `Enter some text for the agent to learn from` box.  The agent will then associate the text `Yellow` with the question `What is Josh's favorite color?`.  This will allow the agent to answer questions about Josh's favorite color.

## GitHub Repository Training

The agent will download all files from the GitHub repository you provide into its long term memory. This will allow the agent to answer questions about the repository and any code in the repository.

GitHub repository training allows you to enter the repository name, for example `Josh-XT/AGiXT`, then click `Train from GitHub Repository` to train the agent on the repository. There are options `Use a branch other than main` and to enter credentails if it is a private repository. You can also choose to use the agent's settings for the GitHub credentials if you have those stored in your agent settings.

## Memory Management

On the Memory Management page, you can query the memory with any search term you would like as if you were saying the same thing to an agent.  This will show each memory relevant to your search and its relevance score.  You can choose to delete any memory you would like from the memory management page.