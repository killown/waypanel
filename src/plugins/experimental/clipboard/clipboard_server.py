import os
import sqlite3
from gi.repository import Gdk, GdkPixbuf
from urllib.parse import unquote, urlparse
from pathlib import Path

from src.plugins.core._base import BasePlugin
from src.shared.path_handler import PathHandler


def get_plugin_metadata(_):
    return {
        "id": "org.waypanel.plugin.clipboard_server",
        "name": "Clipboard Server",
        "version": "1.1.0",
        "enabled": True,
        "description": "Native GDK clipboard server with automatic asset management.",
    }


def verify_db(panel_instance):
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
            self.db_path = self.path_handler.get_data_path(
                "db/clipboard/clipboard_server.db"
            )
            self.assets_path = os.path.join(os.path.dirname(self.db_path), "assets")
            os.makedirs(self.assets_path, exist_ok=True)

        def on_start(self):
            self.max_items = self.get_plugin_setting_add_hint(
                "server/max_items", 100, "Max history size"
            )
            verify_db(self._panel_instance)

        async def start(self):
            self.on_start()
            display = Gdk.Display.get_default()
            if display:
                self.clipboard = display.get_clipboard()
                self.clipboard.connect("changed", self._on_clipboard_changed)

        def _on_clipboard_changed(self, clipboard):
            formats = clipboard.get_formats()
            if formats.contain_gtype(Gdk.Texture.__gtype__):
                clipboard.read_texture_async(None, self._on_image_read_ready)
            elif formats.contain_gtype(str):
                clipboard.read_text_async(None, self._on_text_read_ready)

        def _on_text_read_ready(self, clipboard, result):
            text = clipboard.read_text_finish(result)
            if text and text.strip():
                self.run_in_async_task(self.add_item(text.strip()))

        def _on_image_read_ready(self, clipboard, result):
            texture = clipboard.read_texture_finish(result)
            if texture:
                import time

                file_path = os.path.join(
                    self.assets_path, f"clip_{int(time.time())}.png"
                )
                texture.save_to_png(file_path)
                self.run_in_async_task(self.add_item(f"file://{file_path}"))

        def _cleanup_file(self, content_path):
            """Removes the raw image and its thumbnail from disk."""
            if not content_path.startswith("file://"):
                return

            try:
                raw_path = Path(unquote(urlparse(content_path).path))
                thumb_path = Path(f"{raw_path}.thumb")

                if raw_path.exists():
                    raw_path.unlink()
                if thumb_path.exists():
                    thumb_path.unlink()
            except Exception as e:
                self.logger.error(f"Asset cleanup failed: {e}")

        async def update_label(self, item_id, label):
            """Updates the text alias for a specific history item."""
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET label = ? WHERE id = ?",
                    (label, item_id),
                )
                await db.commit()

        async def update_pin_status(self, item_id, status):
            """Sets the is_pinned bit for an item (1 or 0)."""
            async with self.aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE clipboard_items SET is_pinned = ? WHERE id = ?",
                    (status, item_id),
                )
                await db.commit()

        async def add_item(self, content):
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
                    cursor = await db.execute("SELECT COUNT(*) FROM clipboard_items")
                    if (res := await cursor.fetchone()) and res[0] >= self.max_items:
                        # Fetch the oldest item to clean up its file before deleting record
                        oldest = await db.execute(
                            "SELECT content FROM clipboard_items WHERE is_pinned = 0 ORDER BY timestamp ASC LIMIT 1"
                        )
                        if item := await oldest.fetchone():
                            self._cleanup_file(item[0])

                        await db.execute(
                            "DELETE FROM clipboard_items WHERE id = (SELECT id FROM clipboard_items WHERE is_pinned = 0 ORDER BY timestamp ASC LIMIT 1)"
                        )

                    await db.execute(
                        "INSERT INTO clipboard_items (content, thumbnail) VALUES (?, ?)",
                        (content, thumb_path),
                    )

                await db.commit()
                self.last_clipboard_content = content

        def _process_image_content(self, content: str) -> str | None:
            if not content.startswith("file://"):
                return None
            real_path = unquote(urlparse(content).path)
            thumb_path = f"{real_path}.thumb"
            if not os.path.exists(thumb_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        real_path, 250, 250, True
                    )
                    pixbuf.savev(thumb_path, "png", [], [])
                except:
                    return None
            return thumb_path

        async def delete_item(self, item_id):
            async with self.aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT content FROM clipboard_items WHERE id = ?", (item_id,)
                )
                if item := await cursor.fetchone():
                    self._cleanup_file(item[0])
                await db.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
                await db.commit()

        async def clear_all(self):
            async with self.aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT content FROM clipboard_items")
                items = await cursor.fetchall()
                for item in items:
                    self._cleanup_file(item[0])
                await db.execute("DELETE FROM clipboard_items")
                await db.commit()

        async def get_items(self, limit=100):
            async with self.aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, content, label, is_pinned, thumbnail FROM clipboard_items ORDER BY is_pinned DESC, timestamp DESC LIMIT ?",
                    (limit,),
                )
                return await cursor.fetchall()

        async def stop(self):
            pass

    return AsyncClipboardServer
