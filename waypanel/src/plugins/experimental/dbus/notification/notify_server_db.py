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
