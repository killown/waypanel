import sqlite3
from typing import List, Any

class RecentAppsDatabase:
    """
    Manages the SQLite persistence layer for the application launcher.

    Attributes:
        db_path (str): The filesystem path to the SQLite database.
        max_recent (int): The maximum number of recent applications to retain.
        time_handler (Any): An object or module providing a time() method.
    """

    def __init__(self, db_path: str, max_recent: int, time_handler: Any):
        """
        Initializes the database connection and ensures the schema exists.

        Args:
            db_path (str): Path to the database file.
            max_recent (int): Capacity limit for the recent apps list.
            time_handler (Any): Reference to the time provider (e.g., time module).
        """
        self.db_path = db_path
        self.max_recent = max_recent
        self.time = time_handler
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.initialize_schema()

    def initialize_schema(self) -> None:
        """
        Creates the SQLite table for recent apps if it does not exist.
        """
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_apps (
                app_name TEXT PRIMARY KEY,
                last_opened_at REAL
            )
        """)
        self.conn.commit()

    def add_app(self, app_id: str) -> None:
        """
        Inserts or updates an application's last opened timestamp and prunes old entries.

        Args:
            app_id (str): The unique identifier for the application.
        """
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO recent_apps (app_name, last_opened_at)
            VALUES (?, ?)
        """,
            (app_id, self.time.time()),
        )
        self.conn.commit()
        
        self.cursor.execute("SELECT COUNT(*) FROM recent_apps")
        count = self.cursor.fetchone()[0]
        
        if count > self.max_recent:
            self.cursor.execute(
                """
                DELETE FROM recent_apps
                WHERE app_name IN (
                    SELECT app_name FROM recent_apps ORDER BY last_opened_at ASC LIMIT ?
                )
            """,
                (count - self.max_recent,),
            )
            self.conn.commit()

    def fetch_recent(self) -> List[str]:
        """
        Retrieves the list of recent app IDs sorted by the most recently opened.

        Returns:
            List[str]: A list of application identifiers.
        """
        self.cursor.execute(
            f"SELECT app_name FROM recent_apps ORDER BY last_opened_at DESC LIMIT {self.max_recent}"
        )
        return [row[0] for row in self.cursor.fetchall()]

    def disconnect(self) -> None:
        """
        Closes the active SQLite database connection.
        """
        self.conn.close()