import logging
import mysql.connector
from mysql.connector import Error
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
        self.MYSQL_DATABASE_NAME = MYSQL_DATABASE_NAME
        self.MYSQL_DATABASE_HOST = MYSQL_DATABASE_HOST
        self.MYSQL_DATABASE_PORT = MYSQL_DATABASE_PORT
        self.MYSQL_DATABASE_USERNAME = MYSQL_DATABASE_USERNAME
        self.MYSQL_DATABASE_PASSWORD = MYSQL_DATABASE_PASSWORD

        self.commands = {
            "Create Table in MySQL Database": self.create_table,
            "Insert Row in MySQL Database": self.insert_row,
            "Select Rows in MySQL Database": self.select_rows,
            "Update Rows in MySQL Database": self.update_rows,
            "Delete Rows in MySQL Database": self.delete_rows,
            "Custom SQL Query in MySQL Database": self.execute_sql,
            "Get Database Schema from MySQL Database": self.get_schema,
            "Get Table Schema from MySQL Database": self.get_table_schema,
        }

    async def create_table(self, table_name: str, columns: str):
        logging.info(f"Creating table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor()
            cursor.execute(f"CREATE TABLE {table_name} ({columns});")
            connection.commit()
            cursor.close()
            connection.close()
            return f"Table '{table_name}' created"
        except Error as e:
            logging.error(f"Error creating table: {e}")
            return "Error creating table"

    async def insert_row(self, table_name: str, values: str):
        logging.info(f"Inserting row into table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor()
            cursor.execute(f"INSERT INTO {table_name} VALUES ({values});")
            connection.commit()
            cursor.close()
            connection.close()
            return f"Row inserted into table '{table_name}'"
        except Error as e:
            logging.error(f"Error inserting row: {e}")
            return "Error inserting row"

    async def select_rows(self, table_name: str, columns: str, where: str):
        logging.info(f"Selecting rows from table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute(f"SELECT {columns} FROM {table_name} WHERE {where};")
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            return rows
        except Error as e:
            logging.error(f"Error selecting rows: {e}")
            return []

    async def update_rows(self, table_name: str, set_clause: str, where: str):
        logging.info(f"Updating rows in table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor()
            cursor.execute(f"UPDATE {table_name} SET {set_clause} WHERE {where};")
            connection.commit()
            cursor.close()
            connection.close()
            return f"Rows updated in table '{table_name}'"
        except Error as e:
            logging.error(f"Error updating rows: {e}")
            return "Error updating rows"

    async def delete_rows(self, table_name: str, where: str):
        logging.info(f"Deleting rows from table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {table_name} WHERE {where};")
            connection.commit()
            cursor.close()
            connection.close()
            return f"Rows deleted from table '{table_name}'"
        except Error as e:
            logging.error(f"Error deleting rows: {e}")
            return "Error deleting rows"

    async def execute_sql(self, query: str):
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        logging.info(f"Executing SQL Query: {query}")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            return rows
        except Error as e:
            logging.error(f"Error executing SQL query: {e}")
            return []

    async def get_table_schema(self, table_name: str):
        logging.info(f"Getting schema for table '{table_name}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute(f"DESCRIBE {table_name};")
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            return rows
        except Error as e:
            logging.error(f"Error getting table schema: {e}")
            return []

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.MYSQL_DATABASE_NAME}'")
        try:
            connection = mysql.connector.connect(
                host=self.MYSQL_DATABASE_HOST,
                port=self.MYSQL_DATABASE_PORT,
                database=self.MYSQL_DATABASE_NAME,
                user=self.MYSQL_DATABASE_USERNAME,
                password=self.MYSQL_DATABASE_PASSWORD,
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public';"
            )
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            return rows
        except Error as e:
            logging.error(f"Error getting database schema: {e}")
            return []
