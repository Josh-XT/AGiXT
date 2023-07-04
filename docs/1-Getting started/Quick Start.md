## Quick Start Guide

To get started quickly, you can use the Docker deployment. You will need [docker and docker-compose](https://docs.docker.com/compose/install/) installed on your system. 

Note: If you run locally without docker, it is unsupported.  Any issues you encounter will be closed without comment. Docker is the only way we can say "it works on my machine" and have it mean anything.

### Downloading the docker-compose file
Open a terminal and run the following commands to download the docker-compose file and the example environment file:

```
mkdir AGiXT
cd AGiXT
wget https://raw.githubusercontent.com/Josh-XT/AGiXT/main/docker-compose.yml
wget https://raw.githubusercontent.com/Josh-XT/AGiXT/main/.env.example
```

### Editing the environment file
Open the `.env.example` file in a text editor, you will want to at least change the `POSTGRES_PASSWORD` if nothing else.

- `POSTGRES_SERVER` is the name of the database server, this should be `db` if you are using the docker-compose file as-is.
- `POSTGRES_DB` is the name of the database, this should be `postgres` if you are using the docker-compose file as-is.
- `POSTGRES_PORT` is the port that the database is listening on, this should be `5432` if you are using the docker-compose file as-is.
- `POSTGRES_USER` is the username to connect to the database with, this should be `postgres` if you are using the docker-compose file as-is.
- `POSTGRES_PASSWORD` **is the password to connect to the database with, this should be changed from the example file.**
- `UVICORN_WORKERS` is the number of workers to run the web server with, this is `6` by default, adjust this to your system's capabilities.
- `AGIXT_HUB` is the name of the AGiXT hub, this should be `AGiXT/hub` if you want to use the [Open Source AGiXT hub.](https://github.com/AGiXT/hub) If you want to use your own fork of AGiXT hub, change this to your username and the name of your fork.
- `AGIXT_URI` is the URI of the AGiXT hub, this should be `http://agixt:7437` if you are using the docker-compose file as-is. If hosting the AGiXT server separately, change this to the URI of your AGiXT server, otherwise leave it as-is.
- `GITHUB_USER` is your GitHub username, this is only required if using your own AGiXT hub to pull your repository data.
- `GITHUB_TOKEN` is your GitHub personal access token, this is only required if using your own AGiXT hub to pull your repository data.

### Running AGiXT
Once you have edited the `.env.example` file, save it as `.env` and run the following command to start AGiXT:
```
docker-compose up -d
```

Follow the prompts to install the required dependencies.  Any time you want to run AGiXT in the future, just run `docker-compose up -d` again from the `AGiXT` directory.

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437