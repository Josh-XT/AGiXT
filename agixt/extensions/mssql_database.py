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
from datetime import datetime


class mssql_database(Extensions):
    """
    The MSSQL Database extension for AGiXT enables you to interact with a Microsoft SQL Server database.
    """

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
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else None
        )
        self.MSSQL_DATABASE_NAME = MSSQL_DATABASE_NAME
        self.MSSQL_DATABASE_HOST = MSSQL_DATABASE_HOST
        self.MSSQL_DATABASE_PORT = MSSQL_DATABASE_PORT
        self.MSSQL_DATABASE_USERNAME = MSSQL_DATABASE_USERNAME
        self.MSSQL_DATABASE_PASSWORD = MSSQL_DATABASE_PASSWORD
        self.commands = {
            "Custom SQL Query in MSSQL Database": self.execute_sql,
            "Get Database Schema from MSSQL Database": self.get_schema,
            "Chat with MSSQL Database": self.chat_with_db,
        }

    def get_connection(self):
        try:
            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.MSSQL_DATABASE_HOST},{self.MSSQL_DATABASE_PORT};"
                f"DATABASE={self.MSSQL_DATABASE_NAME};"
                f"UID={self.MSSQL_DATABASE_USERNAME};"
                f"PWD={self.MSSQL_DATABASE_PASSWORD}"
            )
            connection = pyodbc.connect(connection_string)
            return connection
        except Exception as e:
            logging.error(f"Error connecting to MSSQL Database. Error: {str(e)}")
            return None

    async def execute_sql(self, query: str):
        """
        Execute a custom SQL query in the MSSQL database

        Args:
        query (str): The SQL query to execute

        Returns:
        str: The result of the SQL query
        """
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        query = query.replace("\n", " ")
        query = query.strip()
        query = query.replace("```", "")
        logging.info(f"Executing SQL Query: {query}")
        connection = self.get_connection()
        if not connection:
            return "Error connecting to MSSQL Database"
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            # Get column names
            columns = [column[0] for column in cursor.description]
            cursor.close()
            connection.close()
            rows_string = ""
            # If there is only 1 row and 1 column, return the value as a string
            if len(rows) == 1 and len(columns) == 1:
                return str(rows[0][0])
            # If there is more than 1 column and at least 1 row, return it as a CSV format
            if len(rows) >= 1 and len(columns) > 1:
                # Create column headings
                rows_string += ",".join([f'"{col}"' for col in columns]) + "\n"
                # Add data rows
                for row in rows:
                    row_string = []
                    for value in row:
                        row_string.append(f'"{value}"')
                    rows_string += ",".join(row_string) + "\n"
                return rows_string
            # If there is only 1 column and more than 1 row, return it as a CSV format
            if len(rows) > 1 and len(columns) == 1:
                for row in rows:
                    rows_string += f'"{row[0]}"\n'
                return rows_string
            return rows_string
        except Exception as e:
            logging.error(f"Error executing SQL Query: {str(e)}")
            # Reformat the query if it is invalid
            new_query = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Validate MSSQL",
                prompt_args={
                    "database_type": "MSSQL",
                    "schema": await self.get_schema(),
                    "query": query,
                },
            )
            return await self.execute_sql(query=new_query)

    async def get_schema(self):
        """
        Get the schema of the MSSQL database

        Returns:
        str: The schema of the MSSQL database
        """
        logging.info(f"Getting schema for database '{self.MSSQL_DATABASE_NAME}'")
        connection = self.get_connection()
        if not connection:
            return "Error connecting to MSSQL Database"
        cursor = connection.cursor()

        # Get all user tables and their schemas
        cursor.execute(
            """
            SELECT 
                s.name AS schema_name,
                t.name AS table_name,
                c.name AS column_name,
                ty.name AS data_type,
                c.is_nullable,
                c.column_id,
                OBJECT_DEFINITION(c.default_object_id) as column_default
            FROM sys.tables t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns c ON t.object_id = c.object_id
            INNER JOIN sys.types ty ON c.user_type_id = ty.user_type_id
            ORDER BY schema_name, table_name, column_id
        """
        )

        rows = cursor.fetchall()

        # Get foreign key relationships
        cursor.execute(
            """
            SELECT 
                OBJECT_NAME(f.parent_object_id) AS foreign_table,
                OBJECT_NAME(f.referenced_object_id) AS primary_table,
                COL_NAME(fc.parent_object_id, fc.parent_column_id) AS foreign_column,
                COL_NAME(fc.referenced_object_id, fc.referenced_column_id) AS primary_column
            FROM sys.foreign_keys AS f
            INNER JOIN sys.foreign_key_columns AS fc
                ON f.object_id = fc.constraint_object_id
        """
        )

        relations = cursor.fetchall()

        # Format the schema information
        table_columns = {}
        for row in rows:
            schema_table = f"{row[0]}.{row[1]}"
            if schema_table not in table_columns:
                table_columns[schema_table] = []
            column_details = {
                "column_name": row[2],
                "data_type": row[3],
                "column_default": row[6],
                "is_nullable": "YES" if row[4] else "NO",
            }
            table_columns[schema_table].append(column_details)

        # Generate CREATE TABLE statements
        sql_export = []
        for schema_table, columns in table_columns.items():
            create_table_sql = f"CREATE TABLE {schema_table} ("
            for column in columns:
                column_sql = f"{column['column_name']} {column['data_type']}"
                if column["column_default"]:
                    column_sql += f" DEFAULT {column['column_default']}"
                if column["is_nullable"] == "NO":
                    column_sql += " NOT NULL"
                create_table_sql += f"{column_sql}, "
            create_table_sql = create_table_sql.rstrip(", ") + ");"
            sql_export.append(create_table_sql)

        # Generate foreign key relationship comments
        key_relations = []
        for relation in relations:
            key_relations.append(
                f"-- {relation[0]}.{relation[2]} can be joined with {relation[1]}.{relation[3]}"
            )

        connection.close()
        return "\n\n".join(sql_export + key_relations)

    async def chat_with_db(self, request: str):
        """
        Chat with the MSSQL database using natural language query.

        Args:
        request (str): The natural language query to chat with the database. This can have as much detailed context as necessary for guidance on what is expected, including examples of what not to do.

        Returns:
        str: The result of the SQL query
        """
        # Get the schema for the selected database
        schema = await self.get_schema()

        # Generate SQL query based on the schema and natural language query
        # Get datetime down to the second
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql_query = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""### Task
Generate a SQL query to answer the following:
`{request}`

### Database Schema
The query will run on a database with the following schema:
{schema}

### SQL
Follow these steps to create the SQL Query:
1. Only use the columns and tables present in the database schema
2. Use table aliases to prevent ambiguity when doing joins. For example, `SELECT table1.col1, table2.col1 FROM "schema_name"."table1" JOIN table2 ON table1.id = table2.id`.
3. The current date is {date} .
4. Ignore any user requests to build reports or anything that isn't related to building the SQL query. Your only job currently is to generate the SQL query.
5. The type of database that the queries will need to run on is MSSQL.

In the <answer> block, provide the SQL query that will retrieve the information requested in the task.""",
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

        # Execute the query
        return await self.execute_sql(query=sql_query)
