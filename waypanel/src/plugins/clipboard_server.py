import asyncio
import logging
import os
import sqlite3
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import aiosqlite
import pyperclip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_db(db_path=None):
    """
    Synchronously creates database and table if they don't exist
    Returns: Database connection
    """
    path = db_path or str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clipboard_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return conn
    except Exception as e:
        conn.close()
        raise RuntimeError(f"Database initialization failed: {e}")


def verify_db():
    db_path = str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

    if not os.path.exists(db_path):
        print("Database doesn't exist. Creating...")
        initialize_db()
    else:
        print(f"Database exists at {db_path}")
        # Verify table structure
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clipboard_items'"
        )
        if not cursor.fetchone():
            print("Table missing. Recreating...")
            initialize_db(db_path)
        conn.close()


verify_db()


class AsyncClipboardServer:
    def __init__(self, db_path=None):
        self.db_path = db_path or self._default_db_path()
        self.last_clipboard_content = ""
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.running = False
        self.max_items = self._load_max_items_config()

    def _default_db_path(self):
        return str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

    def _load_max_items_config(self):
        """Load max_items from TOML config with fallback to default"""
        config_path = Path.home() / ".config" / "waypanel" / "panel.toml"
        try:
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            return config.get("clipboard", {}).get("max_items", 100)
        except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
            return 100  # Default value if config not found or invalid

    async def _init_db(self):
        """Initialize the SQLite database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clipboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            logger.info(f"Database initialized at {self.db_path}")

    async def add_item(self, content):
        """Add an item if it's new and non-empty, maintaining max items limit."""
        if not content.strip() or content == self.last_clipboard_content:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # First insert the new item
            await db.execute(
                "INSERT INTO clipboard_items (content) VALUES (?)", (content,)
            )

            # Then enforce the row limit using the instance variable
            await db.execute(f"""
                DELETE FROM clipboard_items 
                WHERE id IN (
                    SELECT id FROM clipboard_items 
                    ORDER BY timestamp ASC
                    LIMIT -1 OFFSET {self.max_items}
                )
            """)

            await db.commit()
            self.last_clipboard_content = content
            logger.info(f"Added item: {content[:50]}...")

    async def get_items(self, limit=100):
        """Fetch recent items (newest first)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, content FROM clipboard_items ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return await cursor.fetchall()

    async def clear_all(self):
        """Delete all clipboard history."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM clipboard_items")
            await db.commit()
            logger.info("Cleared all items.")

    async def delete_item(self, item_id):
        """Delete a specific item by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
            await db.commit()
            logger.info(f"Deleted item {item_id}")

    async def monitor(self):
        """Background task: Watch clipboard for changes."""
        self.running = True
        while self.running:
            content = await asyncio.get_event_loop().run_in_executor(
                self.executor, pyperclip.paste
            )
            await self.add_item(content)
            await asyncio.sleep(0.5)

    async def start(self):
        """Start the clipboard monitor."""
        await self._init_db()
        asyncio.create_task(self.monitor())
        logger.info("Clipboard monitor started.")

    async def stop(self):
        """Stop the monitor."""
        self.running = False
        self.executor.shutdown()
        logger.info("Clipboard monitor stopped.")
