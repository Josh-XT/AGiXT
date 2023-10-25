import logging

try:
    import pyodbc
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyodbc"])
    import pyodbc

import logging
from Extensions import Extensions


class mssql_database(Extensions):
    def __init__(
        self,
        MSSQL_DATABASE_NAME: str = "",
        MSSQL_DATABASE_HOST: str = "",
        MSSQL_DATABASE_PORT: int = 1433,
        MSSQL_DATABASE_USERNAME: str = "",
        MSSQL_DATABASE_PASSWORD: str = "",
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.MSSQL_DATABASE_NAME = MSSQL_DATABASE_NAME
        self.MSSQL_DATABASE_HOST = MSSQL_DATABASE_HOST
        self.MSSQL_DATABASE_PORT = MSSQL_DATABASE_PORT
        self.MSSQL_DATABASE_USERNAME = MSSQL_DATABASE_USERNAME
        self.MSSQL_DATABASE_PASSWORD = MSSQL_DATABASE_PASSWORD
        self.commands = {
            "Custom SQL Query in MSSQL Database": self.execute_sql,
            "Get Database Schema from MSSQL Database": self.get_schema,
        }

    def get_connection(self):
        try:
            connection_str = (
                f"Driver={{ODBC Driver 17 for SQL Server}};"
                f"Server={self.MSSQL_DATABASE_HOST},{self.MSSQL_DATABASE_PORT};"
                f"Database={self.MSSQL_DATABASE_NAME};"
                f"Uid={self.MSSQL_DATABASE_USERNAME};"
                f"Pwd={self.MSSQL_DATABASE_PASSWORD};"
                "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            )
            connection = pyodbc.connect(connection_str)
            return connection
        except Exception as e:
            logging.error(f"Error connecting to MSSQL Database. Error: {str(e)}")
            return None

    async def execute_sql(self, query: str):
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        query = query.replace("\n", " ")
        query = query.strip()
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
                column_headings = [column[0] for column in cursor.description]
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
                    "database_type": "MSSQL",
                    "schema": await self.get_schema(),
                    "query": query,
                },
            )
            return await self.execute_sql(query=new_query)

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.MSSQL_DATABASE_NAME}'")
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT table_name, column_name, data_type 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE table_catalog=DATABASE()
            """
        )
        rows = cursor.fetchall()
        connection.close()

        table_columns = {}
        for row in rows:
            table_name = row.table_name
            if table_name not in table_columns:
                table_columns[table_name] = []
            column_details = {
                "column_name": row.column_name,
                "data_type": row.data_type,
            }
            table_columns[table_name].append(column_details)

        schema = []
        for table_name, columns in table_columns.items():
            create_table_sql = f"CREATE TABLE {table_name} ("
            for column in columns:
                column_sql = f"{column['column_name']} {column['data_type']}"
                create_table_sql += f"{column_sql}, "
            create_table_sql = create_table_sql.rstrip(", ") + ");"
            schema.append(create_table_sql)

        return "\n\n".join(schema)
