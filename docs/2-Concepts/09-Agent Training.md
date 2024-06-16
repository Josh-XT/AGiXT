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

# Synthetic Dataset Creation and Training
AGiXT can take all memories created and turn them into a synthetic dataset in the format of `question/good answer/bad answer` for [DPO](https://huggingface.co/docs/trl/main/en/dpo_trainer), [CPO](https://huggingface.co/docs/trl/main/en/cpo_trainer), and [ORPO](https://huggingface.co/docs/trl/main/en/orpo_trainer) trainers to be used in Transformers (or pick your solution) to fine-tune models. The API Endpoint for this training feature is `/api/agent/{agent_name}/memory/dataset`.

Once the dataset is done being created, it can be found at `AGiXT/agixt/WORKSPACE/{dataset_name}.json`.

### Example with Python SDK
The example below will consume the AGiXT GitHub repository to the agent's memory, then create a synthetic dataset with the learned information.

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="Your AGiXT API Key")

# Define the agent we're working with
agent_name="gpt4free"

# Consume the whole AGiXT GitHub Repository to the agent's memory.
agixt.learn_github_repo(
    agent_name=agent_name,
    github_repo="Josh-XT/AGiXT",
    collection_number="0",
)

# Create a synthetic dataset in DPO/CPO/ORPO format.
agixt.create_dataset(
    agent_name=agent_name, dataset_name="Your_dataset_name", batch_size=5
)
```

### Model Training Based on Agent Memory

Finally, we want to make "training" a full process instead of stopping at the memories. After your agent learns from GitHub repo, files, arXive articles, websites, or YouTube captions based on its memories, you can use the training endpoint to:

- Turn all of the agent's memories into synthetic DPO/CPO/ORPO format dataset
- Turn the dataset into DPO QLoRA with `unsloth`
- Merge into the model of your choosing to make your own model from the data you trained your AGiXT agent on
- Uploads your new model to HuggingFace with your choice of `provate_repo` on a `bool` once complete if your agent has a `HUGGINGFACE_API_KEY` in its config.

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="Your AGiXT API Key")

# Define the agent we're working with
agent_name="gpt4free"

# Consume the whole AGiXT GitHub Repository to the agent's memory.
agixt.learn_github_repo(
    agent_name=agent_name,
    github_repo="Josh-XT/AGiXT",
    collection_number="0",
)

# Train the desired model on a synthetic DPO dataset created based on the agents memories.
agixt.train(
      agent_name="AGiXT",
      dataset_name="dataset",
      model="unsloth/mistral-7b-v0.2",
      max_seq_length=16384,
      huggingface_output_path="JoshXT/finetuned-mistral-7b-v0.2",
      private_repo=True,
)
```



