import asyncio
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import aiosqlite
import subprocess

from src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True


def get_plugin_placement(panel_instance):
    return


def initialize_plugin(panel_instance):
    verify_db(panel_instance)
    return run_server_in_background(panel_instance)


def run_server_in_background(panel_instance):
    """Start the clipboard server without blocking main thread"""

    async def _run_server():
        server = AsyncClipboardServer(panel_instance)
        await server.start()
        while True:  # Keep alive
            await asyncio.sleep(1)

    # Run in dedicated thread
    def _start_loop():
        asyncio.run(_run_server())

    import threading

    thread = threading.Thread(target=_start_loop, daemon=True)
    thread.start()
    return thread


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


def verify_db(panel_instance):
    logger = panel_instance.logger
    db_path = str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

    if not os.path.exists(db_path):
        logger.info("Database doesn't exist. Creating...")
        initialize_db()
    else:
        logger.info(f"Database exists at {db_path}")
        # Verify table structure
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clipboard_items'"
        )
        if not cursor.fetchone():
            logger.warning("Table missing. Recreating...")
            initialize_db(db_path)
        conn.close()


class AsyncClipboardServer(BasePlugin):
    def __init__(self, panel_instance, db_path=None):
        super().__init__(panel_instance)
        self.db_path = db_path or self._default_db_path()
        self.last_clipboard_content = ""
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.running = False

        self.config_data_server = self.config_data.get("clipboard").get("server")
        self.log_enabled = self.config_data_server.get("log_enabled", False)
        self.max_items = self.config_data_server.get("max_items", 100)
        self.monitor_interval = self.config_data_server.get("monitor_interval", 0.5)

    def _default_db_path(self):
        return str(Path.home() / ".config" / "waypanel" / "clipboard_server.db")

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
            if self.log_enabled:
                self.logger.info(f"Database initialized at {self.db_path}")

    async def add_item(self, content):
        """
        Add an item if it's new and non-empty, maintaining max items limit.
        Avoids adding duplicate items by checking if the content already exists in the database.
        """
        # Skip empty or duplicate content
        if not content.strip() or content == self.last_clipboard_content:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Check if the content already exists in the database
            cursor = await db.execute(
                "SELECT COUNT(*) FROM clipboard_items WHERE content = ?", (content,)
            )
            count = (await cursor.fetchone())[0]
            if count > 0:
                if self.log_enabled:
                    self.logger.info(
                        f"Duplicate item found: {content[:50]}... Skipping."
                    )
                return

            # Enforce the maximum number of items
            cursor = await db.execute("SELECT COUNT(*) FROM clipboard_items")
            total_items = (await cursor.fetchone())[0]
            if total_items >= self.max_items:
                # Remove the oldest item
                await db.execute("""
                    DELETE FROM clipboard_items
                    WHERE id = (SELECT id FROM clipboard_items ORDER BY timestamp ASC LIMIT 1)
                """)
                await db.commit()

            # Insert the new item
            await db.execute(
                "INSERT INTO clipboard_items (content) VALUES (?)", (content,)
            )
            await db.commit()

            # Update the last clipboard content
            self.last_clipboard_content = content

            if self.log_enabled:
                self.logger.info(f"Added new item: {content[:50]}...")

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
            if self.log_enabled:
                self.logger.info("Cleared all items.")

    async def delete_item(self, item_id):
        """Delete a specific item by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
            await db.commit()
            if self.log_enabled:
                self.logger.info(f"Deleted item {item_id}")

    async def monitor(self):
        """Background task: Watch clipboard for changes using wl-paste."""
        self.running = True
        while self.running:
            # Run wl-paste in a separate thread to avoid blocking
            content = await asyncio.to_thread(
                lambda: subprocess.run(
                    ["wl-paste", "--no-newline"], capture_output=True, text=True
                ).stdout.strip()
            )

            if not content:
                # Try getting an image if no text is found
                image_data = await asyncio.to_thread(
                    lambda: subprocess.run(
                        ["wl-paste", "--type", "image/png"], capture_output=True
                    ).stdout
                )

                if image_data:
                    content = "<image>"  # Placeholder for image handling logic

            await self.add_item(content)
            await asyncio.sleep(self.monitor_interval)

    async def start(self):
        """Start the clipboard monitor."""
        await self._init_db()
        asyncio.create_task(self.monitor())
        if self.log_enabled:
            self.logger.info("Clipboard monitor started.")

    async def stop(self):
        """Stop the monitor."""
        self.running = False
        self.executor.shutdown()
        if self.log_enabled:
            self.logger.info("Clipboard monitor stopped.")

    def about(self):
        """
        This plugin implements an asynchronous clipboard history server
        that monitors the system clipboard, stores its contents in a
        persistent database, and provides methods to manage that history.
        """
        return self.about.__doc__

    def code_explanation(self):
        """
        The core logic of this clipboard server is based on an
        asynchronous, concurrent design for reliable clipboard history
        management. Its key principles are:

        1.  **Asynchronous Database Operations**: The `AsyncClipboardServer`
            uses `asyncio` and `aiosqlite` to perform all database
            interactions. This ensures that reading from and writing to
            the persistent SQLite database happens without blocking the
            main application thread, preserving responsiveness.

        2.  **Background Monitoring with Concurrency**: The `monitor`
            function continuously checks the system clipboard using an
            external command (`wl-paste`). It offloads this blocking
            I/O operation to a separate thread using `asyncio.to_thread`
            to prevent the main event loop from freezing, a vital step
            for a responsive application.

        3.  **Data Persistence and Integrity**: The server stores a history
            of copied items in an SQLite database. The `initialize_db`
            and `verify_db` functions ensure the database and its schema
            are correctly set up on startup. The `add_item` method
            enforces data integrity by preventing the storage of empty or
            duplicate entries and automatically pruning old items to stay
            within a configurable size limit.
        """
        return self.code_explanation.__doc__
