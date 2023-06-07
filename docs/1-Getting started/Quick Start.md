## Quick Start Guide
You have two options for running AGiXT currently, you can either run it with Python locally or you can run it with Docker.

### Local Quick Start Guide
To get started quickly locally, you will need at least Python 3.10.6 installed.  If using Windows, we recommend installing [Windows Subsystem For Linux](https://learn.microsoft.com/en-us/windows/wsl/install) first.

Open a terminal and run the following commands:

```
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
./AGiXT.sh
```

Any time you want to run AGiXT after that, you can just run `./AGiXT.sh` from the AGiXT directory.  This will pull the latest changes from the main branch then launch AGiXT.

You may have to press `Ctrl+C` multiple times to stop AGiXT running in the terminal due to it running multiple processes.

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437

### Docker Quick Start Guide
To get started quickly with Docker, you will need at least Docker 24.0.2 installed. You can check your version by running `docker --version` in a terminal. You can install Docker by following the instructions [here](https://docs.docker.com/get-docker/).

Open a terminal and run the following commands:
```
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
docker-compose up
```

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437
#### Update Docker Containers

```
docker compose pull
```