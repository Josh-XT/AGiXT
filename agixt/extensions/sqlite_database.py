import logging
import sqlite3
from Extensions import Extensions


class sqlite_database(Extensions):
    def __init__(self, SQLITE_DATABASE_PATH: str = "", **kwargs):
        self.SQLITE_DATABASE_PATH = SQLITE_DATABASE_PATH

        self.commands = {
            "Create Table in SQLite Database": self.create_table,
            "Insert Row in SQLite Database": self.insert_row,
            "Select Rows in SQLite Database": self.select_rows,
            "Update Rows in SQLite Database": self.update_rows,
            "Delete Rows in SQLite Database": self.delete_rows,
            "Custom SQL Query in SQLite Database": self.execute_sql,
            "Get Database Schema from SQLite Database": self.get_schema,
        }

    async def create_table(self, table_name: str, columns: str):
        logging.info("Creating table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE {} ({});".format(table_name, columns))
        conn.commit()
        cursor.close()
        conn.close()
        return "Table '{}' created".format(table_name)

    async def insert_row(self, table_name: str, values: str):
        logging.info("Inserting row into table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO {} VALUES ({});".format(table_name, values))
        conn.commit()
        cursor.close()
        conn.close()
        return "Row inserted into table '{}'".format(table_name)

    async def select_rows(self, table_name: str, columns: str, where: str):
        logging.info("Selecting rows from table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT {} FROM {} WHERE {};".format(columns, table_name, where))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    async def update_rows(self, table_name: str, set_clause: str, where: str):
        logging.info("Updating rows in table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE {} SET {} WHERE {};".format(table_name, set_clause, where)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return "Rows updated in table '{}'".format(table_name)

    async def delete_rows(self, table_name: str, where: str):
        logging.info("Deleting rows from table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM {} WHERE {};".format(table_name, where))
        conn.commit()
        cursor.close()
        conn.close()
        return "Rows deleted from table '{}'".format(table_name)

    async def execute_sql(self, query: str):
        logging.info("Executing SQL Query: {}".format(query))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    async def get_schema(self):
        logging.info(f"Getting schema for database '{self.SQLITE_DATABASE_NAME}'")
        connection = sqlite3.connect(self.SQLITE_DATABASE_PATH)
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        sql_export = []
        key_relations = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA foreign_key_list({table_name});")
            relations = cursor.fetchall()
            if relations:
                for relation in relations:
                    key_relations.append(
                        f"-- {table_name}.{relation[3]} can be joined with "
                        f"{relation[2]}.{relation[4]}"
                    )

            cursor.execute(f"PRAGMA table_info({table_name});")
            rows = cursor.fetchall()

            table_columns = []
            for row in rows:
                column_details = {
                    "column_name": row[1],
                    "data_type": row[2],
                    "column_default": row[4],
                    "is_nullable": "YES" if row[3] == 0 else "NO",
                }
                table_columns.append(column_details)

            create_table_sql = f"CREATE TABLE {table_name} ("
            for column in table_columns:
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

    def _get_connection(self):
        return sqlite3.connect(self.SQLITE_DATABASE_PATH)
