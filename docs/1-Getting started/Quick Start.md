## Quickstart with Docker
Clone the repository and run the AGiXT Streamlit Web App.
```
git clone https://github.com/Josh-XT/AGiXT
docker compose up
```
- Web Interface http://localhost:8501

#### Run the REST interface
Remove the line 

` entrypoint: ...`

from `docker-compose.yaml` and `docker compose up`

Make sure you get your ports right!

### Use a specific version of AGiXT
```
AGiXT_VERSION="1.1.76-beta" docker compose up
```

### Update local docker containers

```
docker compose pull
```
