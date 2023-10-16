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
        connection = mysql.connector.connect(
            host=self.MYSQL_DATABASE_HOST,
            port=self.MYSQL_DATABASE_PORT,
            database=self.MYSQL_DATABASE_NAME,
            user=self.MYSQL_DATABASE_USERNAME,
            password=self.MYSQL_DATABASE_PASSWORD,
        )
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'mysql%' AND schema_name NOT LIKE 'information_schema' AND schema_name NOT LIKE 'performance_schema'"
        )
        schemas = cursor.fetchall()
        sql_export = []
        key_relations = []

        for schema in schemas:
            schema = schema["schema_name"]
            cursor.execute(
                f"""
                SELECT 
                    ke.table_name as foreign_table, kcu.table_name as primary_table, ke.column_name as foreign_column, 
                    kcu.column_name as primary_column
                FROM
                    information_schema.table_constraints AS tc 
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.key_column_usage AS ke 
                        ON ke.ordinal_position = kcu.ordinal_position
                        AND ke.constraint_name = kcu.referenced_constraint_name
                        AND ke.table_schema = kcu.referenced_table_schema
                WHERE 
                    tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema='{schema}';
                """
            )
            relations = cursor.fetchall()

            for relation in relations:
                key_relations.append(
                    f"-- {relation['foreign_table']}.{relation['foreign_column']} can be joined with {relation['primary_table']}.{relation['primary_column']}"
                )

            cursor.execute(
                f"""
                SELECT table_name, column_name, data_type, column_default, is_nullable, ordinal_position 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}';
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
                create_table_sql = f"CREATE TABLE {schema}.{table_name} ("
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
