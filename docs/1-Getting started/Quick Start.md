## Quickstart with Docker

#### Prereqs
`docker --version` should say something like

`Docker version 24.0.2, build cb74dfc`

Version `23.x` should work also, but we recommend using the version mentioned above.

#### Run AGiXT

Clone the repository and run the AGiXT Streamlit Web App.
```
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT && docker compose up
```
- Web Interface http://localhost:8501

#### Run the REST interface
Remove the line 

` entrypoint: ...`

from `docker-compose.yaml` and `docker compose up`

Make sure you get your ports right!

### Use a specific version of AGiXT
```
AGiXT_VERSION="1.1.83-beta" docker compose up
```

### Update local docker containers

```
docker compose pull
```
