try:
    import sqlite3
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "sqlite3"])
    import sqlite3

import logging
from Extensions import Extensions


class sqlite_database(Extensions):
    def __init__(
        self,
        SQLITE_DATABASE_PATH: str = "",
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.SQLITE_DATABASE_PATH = SQLITE_DATABASE_PATH
        self.commands = {
            "Custom SQL Query in SQLite Database": self.execute_sql,
            "Get Database Schema from SQLite Database": self.get_schema,
        }

    def get_connection(self):
        try:
            connection = sqlite3.connect(self.SQLITE_DATABASE_PATH)
            return connection
        except Exception as e:
            logging.error(f"Error connecting to SQLite Database. Error: {str(e)}")
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
                column_headings = []
                for column in cursor.description:
                    column_headings.append(f'"{column[0]}"')
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
            new_query = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Validate SQL",
                prompt_args={
                    "database_type": "SQLite",
                    "schema": await self.get_schema(),
                    "query": query,
                },
            )
            return await self.execute_sql(query=new_query)

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.SQLITE_DATABASE_PATH}'")
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        sql_export = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name});")
            rows = cursor.fetchall()

            create_table_sql = f"CREATE TABLE {table_name} ("
            for row in rows:
                column_sql = f"{row[1]} {row[2]}"
                if row[4]:
                    column_sql += f" DEFAULT {row[4]}"
                if row[3] == 1:
                    column_sql += " NOT NULL"
                create_table_sql += f"{column_sql}, "
            create_table_sql = create_table_sql.rstrip(", ") + ");"
            sql_export.append(create_table_sql)
        connection.close()
        return "\n\n".join(sql_export)
