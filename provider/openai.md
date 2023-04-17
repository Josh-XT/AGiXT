# Cloud Setup
## OpenAI with Pinecone

1. Clone the repository via `git clone https://github.com/yoheinakajima/babyagi.git` and `cd` into the cloned repository.
2. Install the required packages: `pip install -r requirements.txt`
3. Copy the .env.example file to .env: `cp .env.example .env`. This is where you will set the following variables.
4. Set your OpenAI and Pinecone API keys in the OPENAI_API_KEY, OPENAPI_API_MODEL, and PINECONE_API_KEY variables.
5. Set the Pinecone environment in the PINECONE_ENVIRONMENT variable.
6. Set the name of the table where the task results will be stored in the TABLE_NAME variable.
7. (Optional) Set the objective of the task management system in the OBJECTIVE variable.
8. (Optional) Set the first task of the system in the INITIAL_TASK variable.
9.  Run the script.
