# ==== FILE: clipboard_server.py ====
import asyncio
import os
import sqlite3

from src.plugins.core._base import BasePlugin
from src.shared.path_handler import PathHandler


def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.clipboard_server",
        "name": "Clipboard Server",
        "version": "1.0.0",
        "enabled": True,
        "description": "Asynchronous clipboard history server with database persistence.",
    }


def verify_db(panel_instance):
    """Synchronously ensures the DB directory, file, and schema exist."""
    path_handler = PathHandler(panel_instance)
    db_path = path_handler.get_data_path("db/clipboard/clipboard_server.db")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if not os.path.exists(db_path) or os.stat(db_path).st_size == 0:
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clipboard_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    label TEXT DEFAULT NULL,
                    is_pinned INTEGER DEFAULT 0,
                    thumbnail TEXT DEFAULT NULL
                )
            """)
            conn.commit()
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for col, col_type in [
            ("label", "TEXT DEFAULT NULL"),
            ("is_pinned", "INTEGER DEFAULT 0"),
            ("thumbnail", "TEXT DEFAULT NULL"),
        ]:
            try:
                cursor.execute(f"SELECT {col} FROM clipboard_items LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE clipboard_items ADD COLUMN {col} {col_type}")
        conn.commit()


def get_plugin_class():
    class AsyncClipboardServer(BasePlugin):
        def __init__(self, panel_instance):
            super().__init__(panel_instance)
            self.last_clipboard_content = ""
            self.running = False
            self._lock = asyncio.Lock()
            self.db_path = self.path_handler.get_data_path(
                "db/clipboard/clipboard_server.db"
            )

        def on_start(self):
            """Initializes settings and triggers database verification."""
            self.max_items = self.get_plugin_setting_add_hint(
                "server/max_items", 100, "Max history size"
            )
            self.monitor_interval = self.get_plugin_setting_add_hint(
                "server/monitor_interval", 0.5, "Poll rate"
            )
            verify_db(self._panel_instance)

        def _process_image_content(self, content: str) -> str | None:
            """Generates thumbnail path and triggers background conversion if content is an image path."""
            if not content.startswith("file://"):
                return None

            from urllib.parse import unquote, urlparse
            from pathlib import Path

            raw_path = urlparse(content).path
            real_path = unquote(raw_path)
            path_obj = Path(real_path)

            if path_obj.suffix.lower() not in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
            ]:
                return None

            thumb_path = f"{real_path}.thumb"
            if not os.path.exists(thumb_path):
                cmd = f"convert '{real_path}' -resize 250x250 '{thumb_path}'"
                self.run_cmd(cmd)

            return thumb_path

        async def add_item(self, content):
            """Async database insertion with duplicate promotion and immediate thumbnailing."""
            content = content.strip()
            if not content:
                return

            async with self._lock:
                if content == self.last_clipboard_content:
                    return

                thumb_path = self._process_image_content(content)

                async with self.aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT id FROM clipboard_items WHERE content = ? LIMIT 1",
                        (content,),
                    )
                    exists = await cursor.fetchone()

                    if exists:
                        await db.execute(
                            "UPDATE clipboard_items SET timestamp = CURRENT_TIMESTAMP WHERE id = ?",
                            (exists[0],),
                        )
                    else:
                        cursor = await db.execute(
                            "SELECT COUNT(*) FROM clipboard_items"
                        )
                        count_res = await cursor.fetchone()
                        if count_res and count_res[0] >= self.max_items:
                            await db.execute("""
                                DELETE FROM clipboard_items WHERE id = (
                                    SELECT id FROM clipboard_items WHERE is_pinned = 0 
                                    ORDER BY timestamp ASC LIMIT 1
                                )
                            """)
                        await db.execute(
                            "INSERT INTO clipboard_items (content, thumbnail) VALUES (?, ?)",
                            (content, thumb_path),
                        )

                    await db.commit()
                    self.last_clipboard_content = content

        async def monitor(self):
            """Background task: Watch clipboard for changes using wl-paste."""
            self.running = True
            while self.running:
                try:
                    proc_types = await self.asyncio.create_subprocess_exec(
                        "wl-paste", "--list-types", stdout=self.asyncio.subprocess.PIPE
                    )
                    types_out, _ = await self.asyncio.wait_for(
                        proc_types.communicate(), timeout=0.5
                    )

                    content = None
                    if b"image/png" in types_out:
                        content = "<image>"
                    else:
                        proc = await self.asyncio.create_subprocess_exec(
                            "wl-paste",
                            "--no-newline",
                            stdout=self.asyncio.subprocess.PIPE,
                            stderr=self.asyncio.subprocess.PIPE,
                        )
                        stdout, _ = await self.asyncio.wait_for(
                            proc.communicate(), timeout=1.0
                        )
                        content = stdout.decode("utf-8", errors="ignore").strip()

                    if content:
                        await self.add_item(content)
                except Exception as e:
                    self.logger.error(f"Monitor error: {e}")

                await self.asyncio.sleep(self.monitor_interval)

        async def start(self):
            """Register the monitor task in the global loop if not already running."""
            if self.running:
                return
            self.on_start()
            self.run_in_async_task(self.monitor())

        async def stop(self):
            """Signal the monitor loop to break."""
            self.running = False

        async def get_items(self, limit=100):
            """Retrieve history sorted by pinned status and timestamp, including thumbnails."""
            async with self.aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, content, label, is_pinned, thumbnail FROM clipboard_items ORDER BY is_pinned DESC, timestamp DESC LIMIT ?",
                    (limit,),
                )
                return await cursor.fetchall()

        async def update_label(self, item_id, label):
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET label = ? WHERE id = ?",
                    (label, item_id),
                )
                await db.commit()

        async def update_pin_status(self, item_id, status):
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET is_pinned = ? WHERE id = ?",
                    (status, item_id),
                )
                await db.commit()

        async def clear_all(self):
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM clipboard_items")
                await db.commit()

        async def delete_item(self, item_id):
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
                await db.commit()

    return AsyncClipboardServer
