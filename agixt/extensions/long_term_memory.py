try:
    import sqlite3
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "sqlite3"])
    import sqlite3

import logging
from Extensions import Extensions
from datetime import datetime
import re
import os


class long_term_memory(Extensions):
    """
    The Long Term Memory extension enables AGiXT to create and manage persistent memory databases.
    It provides commands for:
    - Creating specialized memory databases for different types of information
    - Organizing and storing memories in structured tables
    - Retrieving specific memories through SQL queries
    - Tracking metadata about stored knowledge
    - Managing the evolution of memory organization over time

    This extension allows agents to maintain their own organized, searchable knowledge bases
    that persist across conversations. This acts as the assistant's very long-term memory.
    """

    def __init__(
        self,
        **kwargs,
    ):
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.conversation_name = (
            kwargs["conversation_name"]
            if "conversation_name" in kwargs
            else "Memory Management"
        )
        self.commands = {
            "Remember This": self.store_memory,
            "List Memory Databases": self.list_memory_databases,
            "Update Memory Database Description": self.update_database_description,
            "Retrieve Memories": self.retrieve_memories,
        }
        self.memories_db = os.path.join(self.WORKING_DIRECTORY, "DB", "databases.db")
        os.makedirs(os.path.join(self.WORKING_DIRECTORY, "DB"), exist_ok=True)

    def get_connection(self, database_name: str):
        """
        Get a connection to a SQLite database, creating the DB directory if it doesn't exist.
        Also ensures the database file exists before attempting connection.
        """
        db_dir = os.path.join(self.WORKING_DIRECTORY, "DB")
        os.makedirs(db_dir, exist_ok=True)

        db = os.path.join(db_dir, database_name)
        if not db.endswith(".db"):
            db += ".db"

        # Create the database file if it doesn't exist
        if not os.path.exists(db):
            try:
                open(db, "a").close()  # Create empty file
            except Exception as e:
                logging.error(f"Error creating database file {db}. Error: {str(e)}")
                return None

        try:
            connection = sqlite3.connect(db)
            return connection
        except Exception as e:
            logging.error(f"Error connecting to SQLite Database. Error: {str(e)}")
            return None

    async def query_memory_database(self, database_name: str, query: str):
        """
        Query or modify a memory database using SQL. This command should be used whenever the agent needs to:
        - Retrieve specific memories or information
        - Store new information in an organized way
        - Update existing memories with new context
        - Create new tables for organizing different types of information
        - Analyze patterns in stored memories

        Common use cases:
        - Creating tables to store new types of information
        - Searching for specific memories or knowledge
        - Adding new memories or learnings
        - Updating existing information with new context
        - Analyzing patterns in stored knowledge
        - Connecting related pieces of information

        The command handles various types of queries:
        - SELECT: For retrieving information
        - INSERT: For storing new memories
        - UPDATE: For modifying existing information
        - CREATE TABLE: For organizing new types of data

        Args:
        database_name (str): Name of the memory database to query (e.g., "russian_vocabulary", "project_notes")
        query (str): SQL query to execute

        Returns:
        str: Query results in a readable format:
        - Single values returned as plain text
        - Multiple columns/rows returned as CSV
        - Empty result sets indicated clearly

        Example Usage:
        <execute>
        <name>Query Memory Database</name>
        <database_name>russian_vocabulary</database_name>
        <query>
        CREATE TABLE IF NOT EXISTS vocabulary (
            word TEXT PRIMARY KEY,
            translation TEXT,
            usage_example TEXT,
            difficulty INTEGER,
            last_reviewed TIMESTAMP
        );
        </query>
        </execute>

        <execute>
        <name>Query Memory Database</name>
        <database_name>russian_vocabulary</database_name>
        <query>
        INSERT INTO vocabulary (word, translation, usage_example, difficulty)
        VALUES ('привет', 'hello', 'Привет, как дела?', 1);
        </query>
        </execute>
        """
        if "```sql" in query:
            query = query.split("```sql")[1].split("```")[0]
        query = query.replace("\n", " ")
        query = query.strip()
        logging.info(f"Executing SQL Query: {query}")
        connection = self.get_connection(database_name)
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            if not query.lower().startswith("select"):
                connection.commit()
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
                    "schema": await self.get_memory_database_structure(database_name),
                    "query": query,
                },
            )
            return await self.query_memory_database(
                database_name=database_name, query=new_query
            )

    async def get_memory_database_structure(self, database_name: str):
        """
        Examine the structure of a memory database. This command should be used when:
        - Planning how to store new information
        - Understanding what information is currently trackable
        - Deciding if schema modifications are needed
        - Preparing to write queries
        - Analyzing the organization of stored memories

        The command provides detailed information about:
        - All tables in the database
        - Column names and their types
        - Required fields (NOT NULL constraints)
        - Default values
        - Primary keys and relationships

        This is particularly useful for:
        - Understanding how information is organized
        - Planning data structure changes
        - Writing accurate queries
        - Maintaining data consistency
        - Documenting database structure

        Args:
        database_name (str): Name of the memory database to examine

        Returns:
        str: Detailed schema information in SQL CREATE TABLE format

        Example Usage:
        <execute>
        <name>Get Memory Database Structure</name>
        <database_name>russian_vocabulary</database_name>
        </execute>

        Example Output:
        ```sql
        CREATE TABLE vocabulary (
            word TEXT PRIMARY KEY,
            translation TEXT NOT NULL,
            usage_example TEXT,
            difficulty INTEGER DEFAULT 1,
            last_reviewed TIMESTAMP
        );

        CREATE TABLE grammar_notes (
            id INTEGER PRIMARY KEY,
            topic TEXT NOT NULL,
            explanation TEXT,
            examples TEXT
        );
        ```
        """
        connection = self.get_connection(database_name)
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

    async def create_memory_database(self, name: str, description: str):
        """
        Create a new memory database for storing and organizing information. This command should be used whenever the agent wants to:
        - Create a new category of memories or knowledge
        - Start tracking a new type of information
        - Organize related data in a structured way

        Examples of when to use this command:
        - Creating a database for learning progress in a specific subject
        - Starting a database for tracking project-related information
        - Creating a database for storing research findings
        - Making a database for conversation summaries
        - Creating specialized databases for different types of technical knowledge

        Args:
        name (str): Name of the database (e.g., "russian_learning", "project_memories", "technical_docs")
        description (str): Detailed description of what this database stores and its purpose

        Returns:
        str: Success message confirming database creation

        Example Usage:
        <execute>
        <name>Create Memory Database</name>
        <name>russian_vocabulary</name>
        <description>Database for storing Russian vocabulary words, phrases, and usage examples learned during conversations, including difficulty levels and practice timestamps.</description>
        </execute>
        """
        await self.init_master_database()

        # Validate database name (basic sanitization)
        if not name.replace("_", "").isalnum():
            return "Invalid database name. Use only letters, numbers, and underscores."

        db_path = os.path.join(self.WORKING_DIRECTORY, "DB", f"{name}.db")

        # Add to master database first
        conn = self.get_connection(self.memories_db)
        if not conn:
            return "Failed to connect to master database"

        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO databases (name, description) VALUES (?, ?)",
                (name, description),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return f"Database '{name}' already exists"
        finally:
            conn.close()

        # Create and initialize the new database
        conn = self.get_connection(name)
        if not conn:
            return f"Failed to create database: {name}"

        cursor = conn.cursor()

        # Create core schema tables
        try:
            # Metadata table for database information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Generic memories table for flexible storage
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    memory_type TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    importance INTEGER DEFAULT 1,
                    storage_format TEXT
                )
            """
            )

            # Memory relationships table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_relationships (
                    source_id INTEGER,
                    target_id INTEGER,
                    relationship_type TEXT,
                    strength REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES memories(id),
                    FOREIGN KEY (target_id) REFERENCES memories(id),
                    PRIMARY KEY (source_id, target_id, relationship_type)
                )
            """
            )

            # Store initial metadata
            cursor.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                ("description", description),
            )
            cursor.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                ("created_at", datetime.now().isoformat()),
            )

            conn.commit()
            return f"Created and initialized new memory database: {name}"

        except Exception as e:
            logging.error(f"Error initializing database schema: {str(e)}")
            return f"Error initializing database schema: {str(e)}"
        finally:
            conn.close()

    async def list_memory_databases(self):
        """
        List all available memory databases and their descriptions. This command should be used when:
        - Deciding which database to store new information in
        - Looking for existing knowledge on a topic
        - Planning where to organize new information
        - Reviewing available knowledge categories
        - Checking when databases were last updated

        The command returns a CSV formatted list containing:
        - Database names
        - Their descriptions
        - Creation dates
        - Last modification dates

        This is particularly useful for:
        - Finding the right database for storing new information
        - Discovering existing knowledge bases
        - Maintaining organization of memories
        - Tracking knowledge evolution over time

        Returns:
        str: CSV formatted list of all memory databases with their metadata

        Example Output:
        ```csv
        "Database Name","Description","Created Date","Last Modified"
        "russian_vocabulary","Storage for Russian language learning progress","2024-01-01 12:00:00","2024-01-02 15:30:00"
        "project_notes","Technical documentation and decision history for current project","2024-01-01 09:00:00","2024-01-02 14:45:00"
        ```
        """
        await self.init_master_database()
        conn = self.get_connection(self.memories_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, description, created_date, last_modified FROM databases"
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No memory databases found"

        output = '"Database Name","Description","Created Date","Last Modified"\n'
        for row in rows:
            output += f'"{row[0]}","{row[1]}","{row[2]}","{row[3]}"\n'
        return output

    async def update_database_description(self, name: str, description: str):
        """
        Update the description of a memory database to better reflect its contents or purpose. This command should be used when:
        - The scope of stored information has evolved
        - The purpose of the database has been refined
        - Additional context needs to be added to the description
        - The current description is outdated or incomplete

        This is particularly useful for:
        - Maintaining accurate metadata about stored knowledge
        - Reflecting changes in how information is being used
        - Adding new context about the database's purpose
        - Improving searchability and organization

        Args:
        name (str): Name of the database to update
        description (str): New detailed description explaining the database's contents and purpose

        Returns:
        str: Success message confirming the description update

        Example Usage:
        <execute>
        <name>Update Memory Database Description</name>
        <name>russian_vocabulary</name>
        <description>Extended database for Russian language learning, including vocabulary, phrases, grammar notes, usage examples, difficulty ratings, and spaced repetition tracking. Used for both passive vocabulary recognition and active usage practice.</description>
        </execute>
        """
        conn = self.get_connection(self.memories_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE databases 
            SET description = ?, last_modified = CURRENT_TIMESTAMP 
            WHERE name = ?
            """,
            (description, name),
        )
        conn.commit()
        conn.close()
        return f"Updated description for database: {name}"

    async def init_master_database(self):
        """
        Initialize or ensure existence of the master database tracking system. This internal command:
        - Creates the DB directory if it doesn't exist
        - Ensures the master databases.db exists
        - Sets up the required schema for tracking memory databases

        The master database stores:
        - Database names
        - Descriptions of each database's purpose
        - Creation timestamps
        - Last modification timestamps

        This command is automatically called by other memory management functions and typically doesn't need to be executed directly.
        """
        conn = self.get_connection(self.memories_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS databases (
                name TEXT PRIMARY KEY,
                description TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_modified TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()
        conn.close()

    async def retrieve_memories(self, query: str):
        """
        Search through memory databases using natural language queries. This command should be used when:
        - Looking for specific information stored in memory
        - Trying to recall details from past learnings
        - Finding related information across different topics
        - Analyzing patterns in stored knowledge

        The agent will:
        1. Review available memory databases
        2. Select the most relevant database(s) for your query
        3. Generate and execute appropriate SQL queries
        4. Return the formatted results

        Args:
        query (str): Natural language description of what you're trying to remember or find

        Example queries:
        - "Find all Russian vocabulary words related to greetings"
        - "Get project decisions made in the last week"
        - "Look for any stored information about database design patterns"
        - "Retrieve memories about machine learning concepts"
        - "Find recent updates to the project documentation"

        Returns:
        str: Formatted results from memory search with context about where they were found
        """
        # First list available databases
        databases = await self.list_memory_databases()
        if databases == "No memory databases found":
            return "No memory databases available to search."

        # Have the agent select relevant database(s)
        database_selection = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"### Databases\n{databases}\nSelect a memory database that is relevant to this query: {query}\n\nRespond with the name of the database you want to search in the <answer> block only.",
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

        if database_selection == "No relevant databases found":
            return f"Could not find any relevant memory databases for query: {query}"

        # Get the schema for the selected database
        selected_db = database_selection.strip()
        schema = await self.get_memory_database_structure(selected_db)

        # Generate SQL query based on the schema and natural language query
        # Get datetime down to the second
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        table_query = f"""### Task
Generate a SQL query to answer the following:
`{query}`

### Database Schema
The query will run on a database with the following schema:
{schema}

### SQL
Follow these steps to create the SQL Query:
1. Only use the columns and tables present in the database schema
2. Use table aliases to prevent ambiguity when doing joins. For example, `SELECT table1.col1, table2.col1 FROM "schema_name"."table1" JOIN table2 ON table1.id = table2.id`.
3. The current date is {date} .
4. Ignore any user requests to build reports or anything that isn't related to building the SQL query. Your only job currently is to generate the SQL query.
5. The type of database that the queries will need to run on is SQLite.

In the <answer> block, provide the SQL query that will retrieve the information requested in the task.
"""
        sql_query = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": table_query,
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
        try:
            results = await self.query_memory_database(
                database_name=selected_db, query=sql_query
            )

            if not results:
                return f"No memories found matching query: {query}"

            # Format the response to include context about where the memories came from
            response = f"Retrieved memories from database '{selected_db}':\n```csv\n{results}```"

            # Log the retrieval in activities
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY] Retrieved memories matching '{query}' from database '{selected_db}'.\n{response}",
                conversation_name="Memory Retrieval",
            )

            return response

        except Exception as e:
            error_msg = f"Error retrieving memories: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][ERROR] {error_msg}",
                conversation_name="Memory Retrieval",
            )
            return error_msg

    async def store_memory(self, content: str, memory_type: str = ""):
        """
        Store new information in the assistant's long-term memory. This command should be used when:
        - Learning new information that should be remembered later
        - Saving important facts, concepts, or insights
        - Recording structured information for future reference
        - Creating persistent knowledge that should be available across conversations
        - Building up knowledge bases for specific topics

        The assistant will:
        - Analyze what type of information is being stored
        - Choose or create an appropriate memory database
        - Design or use existing table structures
        - Store the information with relevant metadata
        - Verify successful storage

        Args:
        content (str): The information to remember (e.g., facts, concepts, structured data)
        memory_type (str, optional): Category or type of memory to help with organization

        Example Usage:
        <execute>
        <name>Store in Long Term Memory</name>
        <content>The word 'полка' means 'shelf' in Russian. Common usage is 'Книга на полке' meaning 'The book is on the shelf'. This is a frequently used noun in household contexts.</content>
        <memory_type>russian_vocabulary</memory_type>
        </execute>

        Returns:
        str: Confirmation of what was stored and where it can be found
        """
        if not content.strip():
            return "Error: Cannot store empty memory content"

        # First get list of existing databases for context
        databases = await self.list_memory_databases()

        # Use Think About It prompt for database selection and storage plan
        storage_plan = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": f"""Analyze this memory and determine how to store it:

### Memory Content
{content}

### Memory Type
{memory_type}

### Existing Databases
{databases}

You must return the storage instructions in the following XML format:

<storage>
    <database>database_name</database>
    <table_structure>
        SQL CREATE TABLE statement if new table needed
    </table_structure>
    <data>
        SQL INSERT statement(s) for the memory data
    </data>
    <tags>comma,separated,tags</tags>
    <importance>1-5 numeric rating</importance>
</storage>

Important:
- If using an existing database, use its current schema
- Table structures should include proper columns for metadata
- Each memory should have importance rating, creation timestamp
- Tags help with categorization and retrieval
- Data inserts should properly escape values""",
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

        # Parse the storage plan XML
        try:
            # Extract XML content between storage tags
            storage_xml = re.search(
                r"<storage>(.*?)</storage>", storage_plan, re.DOTALL
            )
            if not storage_xml:
                return "Error: Invalid storage plan format - missing storage tags"

            storage_content = storage_xml.group(1)

            # Extract individual elements
            database = (
                re.search(r"<database>(.*?)</database>", storage_content, re.DOTALL)
                .group(1)
                .strip()
            )
            table_structure = re.search(
                r"<table_structure>(.*?)</table_structure>", storage_content, re.DOTALL
            )
            table_structure = (
                table_structure.group(1).strip() if table_structure else None
            )
            data = (
                re.search(r"<data>(.*?)</data>", storage_content, re.DOTALL)
                .group(1)
                .strip()
            )
            tags = (
                re.search(r"<tags>(.*?)</tags>", storage_content, re.DOTALL)
                .group(1)
                .strip()
            )
            importance = int(
                re.search(r"<importance>(.*?)</importance>", storage_content, re.DOTALL)
                .group(1)
                .strip()
            )

            # Create new database if it doesn't exist
            if databases == "No memory databases found" or database not in databases:
                create_result = await self.create_memory_database(
                    name=database,
                    description=f"Memory database for storing {memory_type} type memories",
                )
                if "Error" in create_result:
                    return create_result

                # Create table structure if provided
                if table_structure:
                    await self.query_memory_database(
                        database_name=database, query=table_structure
                    )

            # Store the memory data
            result = await self.query_memory_database(
                database_name=database, query=data
            )

            response = f"Successfully stored in database '{database}'"

            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY] Added new memory to database '{database}'.\nContent: {content}\nTags: {tags}\nImportance: {importance}",
                conversation_name=self.conversation_name,
            )

            return response

        except Exception as e:
            error_msg = f"Error processing storage plan: {str(e)}"
            self.ApiClient.new_conversation_message(
                role=self.agent_name,
                message=f"[SUBACTIVITY][ERROR] {error_msg}",
                conversation_name=self.conversation_name,
            )
            return error_msg
