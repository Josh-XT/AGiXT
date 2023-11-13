import logging

try:
    import psycopg2
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2"])
    import psycopg2

import psycopg2.extras
import logging
from Extensions import Extensions


class postgres_database(Extensions):
    def __init__(
        self,
        POSTGRES_DATABASE_NAME: str = "",
        POSTGRES_DATABASE_HOST: str = "",
        POSTGRES_DATABASE_PORT: int = 5432,
        POSTGRES_DATABASE_USERNAME: str = "",
        POSTGRES_DATABASE_PASSWORD: str = "",
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.POSTGRES_DATABASE_NAME = POSTGRES_DATABASE_NAME
        self.POSTGRES_DATABASE_HOST = POSTGRES_DATABASE_HOST
        self.POSTGRES_DATABASE_PORT = POSTGRES_DATABASE_PORT
        self.POSTGRES_DATABASE_USERNAME = POSTGRES_DATABASE_USERNAME
        self.POSTGRES_DATABASE_PASSWORD = POSTGRES_DATABASE_PASSWORD
        self.commands = {
            "Custom SQL Query in Postgres Database": self.execute_sql,
            "Get Database Schema from Postgres Database": self.get_schema,
        }

    def get_connection(self):
        try:
            connection = psycopg2.connect(
                database=self.POSTGRES_DATABASE_NAME,
                host=self.POSTGRES_DATABASE_HOST,
                port=self.POSTGRES_DATABASE_PORT,
                user=self.POSTGRES_DATABASE_USERNAME,
                password=self.POSTGRES_DATABASE_PASSWORD,
            )
            return connection
        except Exception as e:
            logging.error(f"Error connecting to Postgres Database. Error: {str(e)}")
            return None

    async def execute_sql(self, query: str):
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        query = query.replace("\n", " ")
        query = query.strip()
        logging.info(f"Executing SQL Query: {query}")
        connection = self.get_connection()
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
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
                prompt_name="Validate PostgreSQL",
                prompt_args={
                    "database_type": "PostgreSQL",
                    "schema": await self.get_schema(),
                    "query": query,
                },
            )
            return await self.execute_sql(query=new_query)

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.POSTGRES_DATABASE_NAME}'")
        connection = self.get_connection()
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(
            f"SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema');"
        )
        schemas = cursor.fetchall()
        sql_export = []
        key_relations = []
        for schema in schemas:
            schema_name = schema["schema_name"]
            cursor.execute(
                f"""
                SELECT kcu.table_name as foreign_table, rel_tco.table_name as primary_table,
                kcu.column_name as foreign_column, rel_kcu.column_name as primary_column
                FROM information_schema.table_constraints tco
                JOIN information_schema.key_column_usage kcu 
                                            ON kcu.constraint_name = tco.constraint_name
                                            AND kcu.constraint_schema = tco.constraint_schema
                JOIN information_schema.referential_constraints rco ON tco.constraint_name = rco.constraint_name
                                            AND tco.constraint_schema = rco.constraint_schema
                JOIN information_schema.key_column_usage rel_kcu ON rco.unique_constraint_name = rel_kcu.constraint_name
                                            AND rco.unique_constraint_schema = rel_kcu.constraint_schema
                JOIN information_schema.table_constraints rel_tco ON rel_kcu.constraint_name = rel_tco.constraint_name
                                            AND rel_kcu.constraint_schema = rel_tco.constraint_schema
                WHERE tco.constraint_type = 'FOREIGN KEY' AND tco.table_schema = '{schema_name}' 
                """
            )
            relations = cursor.fetchall()
            if relations:
                for relation in relations:
                    key_relations.append(
                        f"-- {relation['foreign_table']}.{relation['foreign_column']} can be joined with "
                        f"{relation['primary_table']}.{relation['primary_column']}"
                    )

            cursor.execute(
                f"""
                SELECT table_name, column_name, data_type, column_default, is_nullable, ordinal_position 
                FROM information_schema.columns 
                WHERE table_schema = '{schema_name}';
                """
            )
            rows = cursor.fetchall()

            table_columns = {}
            for row in rows:
                table_name = row["table_name"]
                if table_name not in table_columns:
                    table_columns[table_name] = []
                column_details = {
                    "column_name": row["column_name"],
                    "data_type": row["data_type"],
                    "column_default": row["column_default"],
                    "is_nullable": row["is_nullable"],
                }
                table_columns[table_name].append(column_details)

            for table_name, columns in table_columns.items():
                create_table_sql = f"CREATE TABLE {schema_name}.{table_name} ("
                for column in columns:
                    column_sql = f"{column['column_name']} {column['data_type']}"
                    if column["column_default"]:
                        column_sql += f" DEFAULT {column['column_default']}"
                    if column["is_nullable"] == "NO":
                        column_sql += " NOT NULL"
                    create_table_sql += f"{column_sql}, "
                create_table_sql = create_table_sql.rstrip(", ") + ");"
                sql_export.append(create_table_sql)
        connection.close()
        return "\n\n".join(sql_export + key_relations)
