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
            "Get Table Schema from SQLite Database": self.get_table_schema,
        }

    def create_table(self, table_name: str, columns: str):
        logging.info("Creating table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE {} ({});".format(table_name, columns))
        conn.commit()
        cursor.close()
        conn.close()
        return "Table '{}' created".format(table_name)

    def insert_row(self, table_name: str, values: str):
        logging.info("Inserting row into table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO {} VALUES ({});".format(table_name, values))
        conn.commit()
        cursor.close()
        conn.close()
        return "Row inserted into table '{}'".format(table_name)

    def select_rows(self, table_name: str, columns: str, where: str):
        logging.info("Selecting rows from table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT {} FROM {} WHERE {};".format(columns, table_name, where))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def update_rows(self, table_name: str, set_clause: str, where: str):
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

    def delete_rows(self, table_name: str, where: str):
        logging.info("Deleting rows from table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM {} WHERE {};".format(table_name, where))
        conn.commit()
        cursor.close()
        conn.close()
        return "Rows deleted from table '{}'".format(table_name)

    def execute_sql(self, query: str):
        logging.info("Executing SQL Query: {}".format(query))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def get_table_schema(self, table_name: str):
        logging.info("Getting schema for table '{}'".format(table_name))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info({});".format(table_name))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def get_schema(self):
        logging.info(
            "Getting schema for database '{}'".format(self.POSTGRES_DATABASE_NAME)
        )
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def _get_connection(self):
        return sqlite3.connect(self.SQLITE_DATABASE_PATH)
