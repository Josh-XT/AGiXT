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
        self.POSTGRES_DATABASE_NAME = POSTGRES_DATABASE_NAME
        self.POSTGRES_DATABASE_HOST = POSTGRES_DATABASE_HOST
        self.POSTGRES_DATABASE_PORT = POSTGRES_DATABASE_PORT
        self.POSTGRES_DATABASE_USERNAME = POSTGRES_DATABASE_USERNAME
        self.POSTGRES_DATABASE_PASSWORD = POSTGRES_DATABASE_PASSWORD

        self.commands = {
            "Create Table in Postgres Database": self.create_table,
            "Insert Row in Postgres Database": self.insert_row,
            "Select Rows in Postgres Database": self.select_rows,
            "Update Rows in Postgres Database": self.update_rows,
            "Delete Rows in Postgres Database": self.delete_rows,
            "Custom SQL Query in Postgres Database": self.execute_sql,
            "Get Database Schema from Postgres Database": self.get_schema,
        }

    async def create_table(self, table_name: str, columns: str):
        logging.info(f"Creating table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor()
        cursor.execute(f"CREATE TABLE {table_name} ({columns});")
        connection.commit()
        cursor.close()
        connection.close()
        return f"Table '{table_name}' created"

    async def insert_row(self, table_name: str, values: str):
        logging.info(f"Inserting row into table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor()
        cursor.execute(f"INSERT INTO {table_name} VALUES ({values});")
        connection.commit()
        cursor.close()
        connection.close()
        return f"Row inserted into table '{table_name}'"

    async def select_rows(self, table_name: str, columns: str, where: str):
        logging.info(f"Selecting rows from table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(f"SELECT {columns} FROM {table_name} WHERE {where};")
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return rows

    async def update_rows(self, table_name: str, set: str, where: str):
        logging.info(f"Updating rows in table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor()
        cursor.execute(f"UPDATE {table_name} SET {set} WHERE {where};")
        connection.commit()
        cursor.close()
        connection.close()
        return f"Rows updated in table '{table_name}'"

    async def delete_rows(self, table_name: str, where: str):
        logging.info(f"Deleting rows from table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor()
        cursor.execute(f"DELETE FROM {table_name} WHERE {where};")
        connection.commit()
        cursor.close()
        connection.close()
        return f"Rows deleted from table '{table_name}'"

    async def execute_sql(self, query: str):
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        query = query.replace("\n", " ")
        query = query.replace(".", '"."')
        query = query.replace("FROM ", 'FROM "')
        query = query.replace(" WHERE ", '" WHERE ')
        query = query.replace(' " WHERE', '" WHERE')
        if "WHERE" not in query:
            query = query.replace(";", '";')
        query = query.strip()
        logging.info(f"Executing SQL Query: {query}")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        rows_string = ""
        for row in rows:
            rows_string += str(row) + "\n"
        rows_string = rows_string[:-1]
        rows_string = rows_string.strip()
        rows_string = rows_string[1:-1]
        return rows_string

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.POSTGRES_DATABASE_NAME}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
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
