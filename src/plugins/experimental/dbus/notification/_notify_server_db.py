import sqlite3
import orjson as json
import base64
from src.shared.path_handler import PathHandler


class Database:
    def __init__(self, panel_instance) -> None:
        self.path_handler = PathHandler(panel_instance)
        self.db_path = self.path_handler.get_data_path("db/notify/notifications.db")
        self._initialize_db()

    def _initialize_db(self):
        """Initialize the SQLite database to store notifications."""
        try:
            conn = sqlite3.connect(self.db_path)
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
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise

    def _save_notification_to_db(self, notification, db_path_ignored=None):
        """Save a notification to the database.
        Args:
            notification: Dictionary containing notification details.
            db_path_ignored: Redundant argument passed by calling code, now accepted and ignored.
        """
        try:
            hints = notification.get("hints", {})
            hints = self._make_serializable(hints)
            conn = sqlite3.connect(self.db_path)
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
            return {"__bytes__": base64.b64encode(data).decode("utf-8")}
        else:
            return data
