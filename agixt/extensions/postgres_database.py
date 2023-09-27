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
            "Get Table Schema from Postgres Database": self.get_table_schema,
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
        return rows

    async def get_table_schema(self, table_name: str):
        logging.info(f"Getting schema for table '{table_name}'")
        connection = psycopg2.connect(
            database=self.POSTGRES_DATABASE_NAME,
            host=self.POSTGRES_DATABASE_HOST,
            port=self.POSTGRES_DATABASE_PORT,
            user=self.POSTGRES_DATABASE_USERNAME,
            password=self.POSTGRES_DATABASE_PASSWORD,
        )
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(
            f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}';"
        )
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return rows

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
            f"SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public';"
        )
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return rows
