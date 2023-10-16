import logging
import mysql.connector
from mysql.connector import Error
from Extensions import Extensions
import re


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

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.MYSQL_DATABASE_NAME}'")
        connection = mysql.connector.connect(
            host=self.MYSQL_DATABASE_HOST,
            port=self.MYSQL_DATABASE_PORT,
            database=self.MYSQL_DATABASE_NAME,
            user=self.MYSQL_DATABASE_USERNAME,
            password=self.MYSQL_DATABASE_PASSWORD,
        )
        cursor = connection.cursor(dictionary=True)

        # List of MySQL default tables to exclude
        sys_tables = [
            "information_schema",
            "performance_schema",
            "mysql",
            "sys",
        ]

        # Getting relationships
        cursor.execute(
            f"""
            SELECT constraint_name, update_rule, delete_rule, table_name, referenced_table_name 
            FROM information_schema.referential_constraints 
            WHERE constraint_schema = '{self.MYSQL_DATABASE_NAME}' AND
            referenced_table_name NOT IN ({','.join(["%s"]*len(sys_tables))})
        """,
            tuple(sys_tables),
        )
        relations = cursor.fetchall()

        # Doing the same for tables...
        cursor.execute(
            f"""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = '{self.MYSQL_DATABASE_NAME}' AND
            table_name NOT IN ({','.join(["%s"]*len(sys_tables))})
        """,
            tuple(sys_tables),
        )
        tables = cursor.fetchall()
        schema_sql = []
        relations_sql = []

        for table in tables:
            table_name = table["TABLE_NAME"]
            cursor.execute(f"SHOW CREATE TABLE {table_name}")
            create_table_sql = cursor.fetchone()["Create Table"]
            schema_sql.append(create_table_sql)

            # Adding comments about relationships if any
            for key in relations:
                if key.startswith(table_name + "_"):
                    relations_sql.append(
                        f"-- {table_name}.{key.split('_')[1]} can be joined with {relations[key]}"
                    )

        connection.close()
        joined_schema_sql = "\n\n".join(schema_sql + relations_sql)
        joined_schema_sql = re.sub(r"\/\*!\d{5}.*COMMENT=", "-- ", joined_schema_sql)
        joined_schema_sql = re.sub(r"\/\*.*", "", joined_schema_sql)
        joined_schema_sql = re.sub(r"\).*COMMENT=", ") -- ", joined_schema_sql)
        joined_schema_sql = (
            joined_schema_sql.replace(" COLLATE utf8mb3_bin", "")
            .replace(" CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci", "")
            .replace(" CHARACTER SET ascii COLLATE ascii_general_ci", "")
            .replace(" CHARACTER SET utf8mb3 ", "")
            .replace(" int unsigned ", " int ")
            .replace(" NOT NULL", "")
        )
        return joined_schema_sql
