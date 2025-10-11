import asyncio
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import aiosqlite
import subprocess
from src.shared.path_handler import PathHandler
from src.plugins.core._base import BasePlugin


def get_plugin_metadata(_):
    about = """
            This plugin implements an asynchronous clipboard history server
            that monitors the system clipboard, stores its contents in a
            persistent database, and provides methods to manage that history.
            """
    return {
        "id": "org.waypanel.plugin.clipboard_server",
        "name": "Clipboard Server",
        "version": "1.0.0",
        "enabled": True,
        "description": about,
    }


def initialize_plugin(panel_instance):
    verify_db(panel_instance)
    return run_server_in_background(panel_instance)


def run_server_in_background(panel_instance):
    """Start the clipboard server without blocking main thread"""

    async def _run_server():
        plugin = get_plugin_class()
        server = plugin(panel_instance)
        await server.start()
        while True:
            await asyncio.sleep(1)

    def _start_loop():
        asyncio.run(_run_server())

    import threading

    thread = threading.Thread(target=_start_loop, daemon=True)
    thread.start()
    return thread


def initialize_db(panel_instance):
    """
    Synchronously creates database and table if they don't exist.
    UPDATED: Includes the 'label' and 'is_pinned' columns.
    Returns: Database connection
    """
    path_handler = PathHandler(panel_instance)
    db_path = path_handler.get_data_path("db/clipboard/clipboard_server.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clipboard_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                label TEXT DEFAULT NULL,
                is_pinned INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        return conn
    except Exception as e:
        conn.close()
        raise RuntimeError(f"Database initialization failed: {e}")


def verify_db(panel_instance):
    logger = panel_instance.logger
    path_handler = PathHandler(panel_instance)
    db_path = path_handler.get_data_path("db/clipboard/clipboard_server.db")
    if not os.path.exists(db_path):
        logger.info("Database doesn't exist. Creating...")
        initialize_db(panel_instance)
        return
    logger.info(f"Database exists at {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='clipboard_items'"
    )
    if not cursor.fetchone():
        logger.warning("Table missing. Recreating...")
        conn.close()
        initialize_db(panel_instance)
        return
    try:
        cursor.execute("SELECT label FROM clipboard_items LIMIT 1")
    except sqlite3.OperationalError as e:
        if "no such column: label" in str(e):
            logger.info("Migrating database: Adding 'label' column to clipboard_items.")
            conn.execute(
                "ALTER TABLE clipboard_items ADD COLUMN label TEXT DEFAULT NULL"
            )
            conn.commit()
            logger.info("Database migration complete (label).")
    try:
        cursor.execute("SELECT is_pinned FROM clipboard_items LIMIT 1")
    except sqlite3.OperationalError as e:
        if "no such column: is_pinned" in str(e):
            logger.info(
                "Migrating database: Adding 'is_pinned' column to clipboard_items."
            )
            conn.execute(
                "ALTER TABLE clipboard_items ADD COLUMN is_pinned INTEGER DEFAULT 0"
            )
            conn.commit()
            logger.info("Database migration complete (is_pinned).")
    finally:
        conn.close()


def get_plugin_class():
    class AsyncClipboardServer(BasePlugin):
        def __init__(self, panel_instance, db_path=None):
            super().__init__(panel_instance)
            self.last_clipboard_content = ""
            self.executor = ThreadPoolExecutor(max_workers=1)
            self.running = False
            self.db_path = self.path_handler.get_data_path(
                "db/clipboard/clipboard_server.db"
            )
            self.log_enabled = self.get_plugin_setting("server_log_enabled", False)
            self.max_items = self.get_plugin_setting("server_max_items", 100)
            self.monitor_interval = self.get_plugin_setting(
                "server_monitor_interval", 0.5
            )

        async def _init_db(self, panel_instance, db_path):
            """
            Initialize the SQLite database.
            UPDATED: Includes the 'label' and 'is_pinned' columns.
            """
            path_handler = PathHandler(panel_instance)
            db_path = path_handler.get_data_path("db/clipboard/clipboard_server.db")
            async with aiosqlite.connect(db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS clipboard_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        label TEXT DEFAULT NULL,
                        is_pinned INTEGER DEFAULT 0 -- RENAMED: from is_stuck to is_pinned
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
            if not content.strip() or content == self.last_clipboard_content:
                return
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM clipboard_items WHERE content = ?", (content,)
                )
                count = (await cursor.fetchone())[0]  # pyright: ignore
                if count > 0:
                    if self.log_enabled:
                        self.logger.info(
                            f"Duplicate item found: {content[:50]}... Skipping."
                        )
                    return
                cursor = await db.execute("SELECT COUNT(*) FROM clipboard_items")
                total_items = (await cursor.fetchone())[0]  # pyright: ignore
                if total_items >= self.max_items:
                    await db.execute("""
                        DELETE FROM clipboard_items
                        WHERE id = (
                            SELECT id FROM clipboard_items
                            WHERE is_pinned = 0  -- RENAMED: from is_stuck to is_pinned
                            ORDER BY timestamp ASC LIMIT 1
                        )
                    """)
                    await db.commit()
                await db.execute(
                    "INSERT INTO clipboard_items (content) VALUES (?)", (content,)
                )
                await db.commit()
                self.last_clipboard_content = content
                if self.log_enabled:
                    self.logger.info(f"Added new item: {content[:50]}...")

        async def get_items(self, limit=100):
            """
            Fetch recent items (pinned items first, then newest first).
            UPDATED: Now selects id, content, label, and is_pinned.
            """
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, content, label, is_pinned FROM clipboard_items ORDER BY is_pinned DESC, timestamp DESC LIMIT ?",
                    (limit,),
                )
                return await cursor.fetchall()

        async def update_label(self, item_id: int, new_label: str | None):
            """
            Update the custom label for a specific item ID.
            """
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET label = ? WHERE id = ?",
                    (new_label, item_id),
                )
                await db.commit()
                if self.log_enabled:
                    self.logger.info(
                        f"Updated label for item {item_id} to '{new_label}'."
                    )

        async def update_pin_status(self, item_id: int, pin_value: int):
            """
            NEW: Update the 'is_pinned' status (pin/unpin) for a specific item ID.
            NOTE: Expects 0 (unpinned) or 1 (pinned).
            """
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET is_pinned = ? WHERE id = ?",
                    (pin_value, item_id),
                )
                await db.commit()
                if self.log_enabled:
                    self.logger.info(
                        f"Updated pin status for item {item_id} to {pin_value}."
                    )

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
                content = await asyncio.to_thread(
                    lambda: subprocess.run(
                        ["wl-paste", "--no-newline"], capture_output=True, text=True
                    ).stdout.strip()
                )
                if not content:
                    image_data = await asyncio.to_thread(
                        lambda: subprocess.run(
                            ["wl-paste", "--type", "image/png"], capture_output=True
                        ).stdout
                    )
                    if image_data:
                        content = "<image>"
                await self.add_item(content)
                await asyncio.sleep(self.monitor_interval)

        async def start(self):
            """Start the clipboard monitor."""
            await self._init_db(self.obj, self.db_path)
            asyncio.create_task(self.monitor())
            if self.log_enabled:
                self.logger.info("Clipboard monitor started.")

        async def stop(self):
            """Stop the monitor."""
            self.running = False
            self.executor.shutdown()
            if self.log_enabled:
                self.logger.info("Clipboard monitor stopped.")

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
                are correctly set up on startup, including migration for the new
                `label` and **`is_pinned`** columns. The `add_item` method enforces data integrity
                by preventing the storage of empty or duplicate entries and
                automatically pruning old, *non-pinned* items to stay within a configurable
                size limit.
            4.  **Pinned Item Prioritization**: The new **`is_pinned`** column and
                **`update_pin_status`** method allow clients to "pin" important
                clipboard entries. The `get_items` query ensures that all
                pinned items are always returned first, making them easy to
                access regardless of their age.
            """
            return self.code_explanation.__doc__

    return AsyncClipboardServer
