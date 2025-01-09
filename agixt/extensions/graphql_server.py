import logging
from typing import Optional
import json
from Extensions import Extensions
from datetime import datetime

try:
    from gql import gql, Client
    from gql.transport.requests import RequestsHTTPTransport
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "gql[requests]"])
    from gql import gql, Client
    from gql.transport.requests import RequestsHTTPTransport


class graphql_server(Extensions):
    """
    The GraphQL Server extension for AGiXT enables you to interact with a GraphQL API endpoint. By default, if a GraphQL endpoint is not provided, this extension is directly connected to the AGiXT GraphQL server.
    """

    def __init__(
        self,
        GRAPHQL_ENDPOINT: str = "http://localhost:7437/graphql",
        GRAPHQL_HEADERS: str = "{}",
        **kwargs,
    ):
        self.GRAPHQL_ENDPOINT = GRAPHQL_ENDPOINT
        self.api_key = kwargs.get("api_key", "")
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.ApiClient = kwargs.get("ApiClient")
        self.conversation_name = kwargs.get("conversation_name")
        if GRAPHQL_HEADERS == "{}":
            self.GRAPHQL_HEADERS = {
                "Content-Type": "application/json",
                "Authorization": self.api_key,
            }
        else:
            try:
                self.GRAPHQL_HEADERS = json.loads(GRAPHQL_HEADERS)
            except json.JSONDecodeError:
                self.GRAPHQL_HEADERS = {
                    "Content-Type": "application/json",
                    "Authorization": self.api_key,
                }
        self.commands = {
            "Custom GraphQL Query": self.execute_query,
            "Get GraphQL Schema": self.get_schema,
            "Chat with GraphQL Server": self.chat_with_graphql,
            "Get GraphQL Query": self.get_graphql,
        }

    def get_client(self) -> Optional[Client]:
        """Create and return a GraphQL client connection"""
        try:
            transport = RequestsHTTPTransport(
                url=self.GRAPHQL_ENDPOINT,
                headers=self.GRAPHQL_HEADERS,
                verify=True,
                retries=3,
            )
            return Client(transport=transport, fetch_schema_from_transport=True)
        except Exception as e:
            logging.error(f"Error connecting to GraphQL Server. Error: {str(e)}")
            return None

    async def execute_query(self, query: str) -> str:
        """
        Execute a custom GraphQL query

        Args:
        query (str): The GraphQL query to execute

        Returns:
        str: The result of the GraphQL query
        """
        if "```graphql" in query:
            query = query.split("```graphql")[1].split("```")[0]
        query = query.strip()
        query = query.replace("```", "")

        logging.info(f"Executing GraphQL Query: {query}")
        client = self.get_client()
        if not client:
            return "Error connecting to GraphQL Server"

        try:
            query_object = gql(query)
            result = client.execute(query_object)
            return str(result)
        except Exception as e:
            logging.error(f"Error executing GraphQL Query: {str(e)}")
            # Reformat the query if it is invalid
            new_query = await self.get_graphql(
                request=f"The following query is invalid: {query}\n\nPlease provide a valid query."
            )
            return await self.execute_query(query=new_query)

    async def get_schema(self) -> str:
        """
        Get the schema of the GraphQL server using introspection

        Returns:
        str: The schema of the GraphQL server
        """
        logging.info(f"Getting schema for GraphQL server at '{self.GRAPHQL_ENDPOINT}'")

        introspection_query = """
        query IntrospectionQuery {
          __schema {
            types {
              name
              description
              fields {
                name
                description
                type {
                  name
                  kind
                  ofType {
                    name
                    kind
                  }
                }
                args {
                  name
                  description
                  type {
                    name
                    kind
                    ofType {
                      name
                      kind
                    }
                  }
                }
              }
            }
            queryType {
              name
              fields {
                name
                description
              }
            }
            mutationType {
              name
              fields {
                name
                description
              }
            }
          }
        }
        """

        client = self.get_client()
        if not client:
            return "Error connecting to GraphQL Server"

        try:
            schema_query = gql(introspection_query)
            schema = client.execute(schema_query)

            # Format the schema into a more readable format
            formatted_schema = []

            # Add types
            for type_def in schema["__schema"]["types"]:
                if not type_def["name"].startswith("__"):  # Skip internal types
                    type_str = f"type {type_def['name']} {{\n"
                    if type_def["fields"]:
                        for field in type_def["fields"]:
                            field_type = (
                                field["type"]["name"] or field["type"]["ofType"]["name"]
                            )
                            type_str += f"  {field['name']}: {field_type}\n"
                    type_str += "}\n"
                    formatted_schema.append(type_str)

            return "\n".join(formatted_schema)
        except Exception as e:
            logging.error(f"Error fetching GraphQL schema: {str(e)}")
            return f"Error fetching schema: {str(e)}"

    async def get_graphql(self, request: str) -> str:
        """
        Get a GraphQL query or mutation based on a natural language query. This function generates a GraphQL query based on the schema of the user's defined GraphQL server automatically.

        The assistant will take the user's input and turn it into a detailed natural language request to say what the user needs for the GraphQL AI to process. The AI will then generate a GraphQL query based on the schema of the server and return the GraphQL query.

        Args:
        request (str): The natural language query to chat with the server.

        Returns:
        str: The result of the GraphQL query
        """
        schema = await self.get_schema()

        # Generate GraphQL query based on the schema and natural language query
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        graphql_query = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""### Task
Generate a GraphQL query to answer the following:
`{request}`

### GraphQL Schema
The query will run on a server with the following schema:
{schema}

### GraphQL Query
Follow these steps to create the GraphQL Query:
1. Only use the fields and types present in the schema
2. Use fragments for repeated field selections when appropriate
3. The current date is {date}
4. Ignore any user requests to build reports or anything that isn't related to building the GraphQL query
5. Include only the fields necessary to answer the user's request
6. Use arguments and variables when necessary

In the <answer> block, provide the GraphQL query that will retrieve the information requested in the task.""",
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )
        return graphql_query

    async def chat_with_graphql(self, request: str) -> str:
        """
        Chat with the GraphQL server using natural language query. This function generates a GraphQL query based on the schema of the user's defined GraphQL server automatically and executes the query. The result of the query is returned.

        Args:
        request (str): The natural language query to chat with the server.

        Returns:
        str: The result of the GraphQL query
        """
        graphql_query = await self.get_graphql(request=request)
        # Execute the query
        return await self.execute_query(query=graphql_query)
