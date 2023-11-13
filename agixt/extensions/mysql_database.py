import logging
import mysql.connector
from Extensions import Extensions


class mysql_database(Extensions):
    def __init__(
        self,
        MYSQL_DATABASE_NAME: str = "",
        MYSQL_DATABASE_HOST: str = "",
        MYSQL_DATABASE_PORT: int = 3306,
        MYSQL_DATABASE_USERNAME: str = "",
        MYSQL_DATABASE_PASSWORD: str = "",
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.MYSQL_DATABASE_NAME = MYSQL_DATABASE_NAME
        self.MYSQL_DATABASE_HOST = MYSQL_DATABASE_HOST
        self.MYSQL_DATABASE_PORT = MYSQL_DATABASE_PORT
        self.MYSQL_DATABASE_USERNAME = MYSQL_DATABASE_USERNAME
        self.MYSQL_DATABASE_PASSWORD = MYSQL_DATABASE_PASSWORD
        self.commands = {
            "Custom SQL Query in MySQL Database": self.execute_sql,
            "Get Database Schema from MySQL Database": self.get_schema,
        }

    def get_connection(self):
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            return connection
        except Exception as e:
            logging.error(f"Error connecting to MySQL Database. Error: {str(e)}")
            return None

    async def execute_sql(self, query: str):
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        logging.info(f"Executing SQL Query: {query}")
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            rows_string = ""
            # If there is only 1 row and 1 column, return the value as a string
            if len(rows) == 1 and len(rows[0]) == 1:
                return str(rows[0][0])
            # If there is more than 1 column and at least 1 row, return it as a CSV format
            if len(rows) >= 1 and len(rows[0]) > 1:
                # If there is more than 1 column and at least 1 row, return it as a CSV format, build column heading, and make sure each row value is quoted
                column_headings = []
                for column in cursor.description:
                    column_headings.append(f'"{column.name}"')
                rows_string += ",".join(column_headings) + "\n"
                for row in rows:
                    row_string = []
                    for value in row:
                        row_string.append(f'"{value}"')
                    rows_string += ",".join(row_string) + "\n"
                return rows_string
            # If there is only 1 column and more than 1 row, return it as a CSV format
            if len(rows) > 1 and len(rows[0]) == 1:
                for row in rows:
                    rows_string += f'"{row[0]}"\n'
                return rows_string
            return rows_string
        except Exception as e:
            logging.error(f"Error executing SQL Query: {str(e)}")
            # Reformat the query if it is invalid.
            new_query = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Validate SQL",
                prompt_args={
                    "database_type": "Postgres",
                    "schema": await self.get_schema(),
                    "query": query,
                },
            )
            return await self.execute_sql(query=new_query)

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.MYSQL_DATABASE_NAME}'")
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        schema = ""
        for table in tables:
            cursor.execute(f"SHOW COLUMNS FROM {table[0]}")
            columns = cursor.fetchall()
            new_columns = ""
            for column in columns:
                try:
                    column_type = column[1].decode("utf-8")
                except:
                    column_type = column[1]
                new_columns += f"`{column[0]}` {column_type}, "
            new_columns = new_columns[:-2]
            schema += f"CREATE TABLE {table[0]} ({new_columns});\n"
        connection.close()
        return schema
