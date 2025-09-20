import os
import sqlite3
import orjson as json
import base64


class Database:
    def __init__(self) -> None:
        pass

    def _initialize_db(self):
        """Initialize the SQLite database to store notifications."""
        db_path = os.path.expanduser("~/.config/waypanel/notifications.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    body TEXT,
                    app_icon TEXT,
                    actions TEXT,
                    hints JSON,
                    expire_timeout INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
            print(f"Database initialized at {db_path}")
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise
        return db_path

    def _save_notification_to_db(self, notification, db_path):
        """Save a notification to the database.
        Args:
            notification: Dictionary containing notification details.
        """
        try:
            # Ensure hints are JSON serializable
            hints = notification.get("hints", {})
            hints = self._make_serializable(hints)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO notifications (
                    app_name, summary, body, app_icon, actions, hints, expire_timeout
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    notification["app_name"],
                    notification["summary"],
                    notification["body"],
                    notification["app_icon"],
                    ",".join(notification["actions"]),
                    json.dumps(hints),
                    notification["expire_timeout"],
                ),
            )
            conn.commit()
            conn.close()
            print("Notification saved to database.")
        except Exception as e:
            print(f"Error saving notification to database: {e}")

    def _make_serializable(self, data):
        """Recursively convert non-serializable types (e.g., bytes) to serializable formats."""
        if isinstance(data, dict):
            return {k: self._make_serializable(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._make_serializable(item) for item in data]
        elif isinstance(data, bytes):
            # Convert bytes to Base64-encoded string
            return {"__bytes__": base64.b64encode(data).decode("utf-8")}
        else:
            return data

    def about(self):
        """
        This module provides the data persistence layer for the
        notification system, using an SQLite database to store
        and manage a history of all received notifications.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this database module is to reliably store
        notification data for later retrieval. Its design is based on
        these key concepts:

        1.  **Dedicated Data Layer**: The module is a self-contained
            data access object. It is responsible solely for managing
            the SQLite database file and the `notifications` table,
            decoupling the storage logic from the D-Bus communication
            and UI components.

        2.  **Schema Definition**: The `_initialize_db` method defines
            a robust table schema for notifications, including a primary
            key, content fields (summary, body), and a JSON field for
            metadata (hints). This structure ensures consistency for
            all stored notifications.

        3.  **Cross-Platform Serialization**: The `_save_notification_to_db`
            method handles the complex task of serializing data. It
            uses a helper function to recursively convert potentially
            non-serializable data types (like bytes) into a standard
            JSON format using Base64 encoding. This guarantees that all
            notification data, regardless of its original format, can
            be safely and consistently stored.
        """
        return self.code_explanation.__doc__
