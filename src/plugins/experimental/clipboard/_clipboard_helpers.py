import mimetypes
from pathlib import Path
import re
import aiosqlite
import string
import math
from collections import Counter
from src.shared.path_handler import PathHandler
from src.shared.data_helpers import DataHelpers


class ClipboardManager:
    def __init__(self, panel_instance, get_plugin_class):
        plugin = get_plugin_class()
        self.server = plugin(panel_instance)
        self.path_handler = PathHandler(panel_instance)
        self.data_helpers = DataHelpers()
        self.db_path = self.path_handler.get_data_path(
            "db/clipboard/clipboard_server.db"
        )

    async def initialize(self):
        """Triggers the server to verify/create the database and start monitoring."""
        await self.server.start()

    async def get_history(self) -> list[tuple[int, str, str | None, int]]:
        """Returns all items as (id, content, label, is_pinned) tuples (new feature)"""
        return await self.server.get_items()  # pyright: ignore

    async def get_item_by_id(
        self, target_id: int
    ) -> tuple[int, str, str | None, int] | None:
        """Get specific item by its database ID (first tuple element)"""
        items = await self.get_history()
        for item_id, content, label, is_pinned in items:
            if item_id == target_id:
                return (item_id, content, label, is_pinned)
        return None

    async def update_item_pin_status(self, item_id: int, status: bool):
        """Updates the pin status using the native server method name."""
        await self.server.update_pin_status(item_id, 1 if status else 0)

    async def update_item_label(self, item_id: int, label: str | None):
        """Updates the item label using the native server method name."""
        await self.server.update_label(item_id, label)

    async def clear_history(self):
        await self.server.clear_all()

    async def reset_ids(self):
        """Properly rebuild the table with sequential IDs (UPDATED for 'label' and 'is_pinned' column)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                    CREATE TABLE new_clipboard_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        label TEXT DEFAULT NULL,
                        is_pinned INTEGER DEFAULT 0 -- NEW: Field for Pinning
                    )
                """)
            await db.execute("""
                    INSERT INTO new_clipboard_items (content, timestamp, label, is_pinned)
                    SELECT content, timestamp, label, 0 FROM clipboard_items
                    ORDER BY timestamp DESC
                """)
            await db.execute("DROP TABLE clipboard_items")
            await db.execute(
                "ALTER TABLE new_clipboard_items RENAME TO clipboard_items"
            )
            await db.commit()

    async def delete_item(self, item_id: int):
        await self.server.delete_item(item_id)

    def get_item_by_id_sync(
        self, target_id: int
    ) -> tuple[int, str, str | None, int] | None:
        """Blocking version for non-async contexts"""
        import asyncio

        return asyncio.run(self.get_item_by_id(target_id))


class ClipboardHelpers:
    def __init__(self, parent) -> None:
        self.parent = parent
        pass

    def is_image_content(self, content):
        """Detects if content is an image path, raw data, or an HTML image tag."""
        if not content:
            return False

        # Check for HTML img tags or direct image URLs
        if isinstance(content, str):
            # Regex to catch the <img src="..."> pattern you provided
            if re.search(
                r'<img [^>]*src=["\']([^"\']+\.(?:png|jpg|jpeg|gif|webp|svg))["\']',
                content,
                re.I,
            ):
                return True
            # Direct URL check
            if content.lower().startswith(
                ("http://", "https://")
            ) and content.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                return True
            # Existing file path check
            if len(content) < 512 and Path(content).exists():
                mime = mimetypes.guess_type(content)[0]
                return mime and mime.startswith("image/")

        # Existing bytes check
        elif isinstance(content, bytes):
            magic_numbers = {b"\x89PNG": "PNG", b"\xff\xd8": "JPEG", b"BM": "BMP"}
            return any(content.startswith(magic) for magic in magic_numbers.keys())

        return content == "<image>"

    def clear_and_calculate_height(self):
        try:
            # Precise UI Cleanup
            if self.parent.listbox is not None:
                row = self.parent.listbox.get_first_child()
                while row:
                    next_row = row.get_next_sibling()
                    # Deep cleanup of popovers to prevent memory leaks
                    row_hbox = row.get_child()
                    if row_hbox:
                        child = row_hbox.get_first_child()
                        while child:
                            if hasattr(child, "popover") and child.popover is not None:
                                try:
                                    child.popover.unparent()
                                    del child.popover
                                except Exception:
                                    pass
                            child = child.get_next_sibling()

                    self.parent.listbox.remove(row)
                    row = next_row

            # Sync State with Server
            self.parent.asyncio.run(self.parent.manager.initialize())
            items = self.parent.asyncio.run(self.parent.manager.get_history())

            # Calculate Height using explicit properties
            IMAGE_EXTENSIONS = (
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".bmp",
                ".webp",
                ".svg",
            )
            total_height = 0

            for _, content, _, _ in items:
                is_img = any(
                    isinstance(content, str) and content.lower().endswith(ext)
                    for ext in IMAGE_EXTENSIONS
                ) or self.parent.clipboard_helper.is_image_content(content)

                if is_img:
                    total_height += self.parent.image_row_height
                else:
                    # Logic: Text height + markup/label overhead
                    total_height += self.parent.text_row_height

                total_height += self.parent.item_spacing

            # Final Constraint Check
            final_height = min(max(total_height, 100), self.parent.popover_max_height)

            # Update ScrolledWindow to reflect new content size immediately
            if hasattr(self.parent, "scrolled_window"):
                self.parent.scrolled_window.set_min_content_height(final_height)

            return final_height

        except Exception as e:
            self.parent.logger.error(
                message=f"Error in clear_and_calculate_height: {e}"
            )
            return 100

    def is_color_code(self, text):
        """
        Returns True ONLY if the input is EXACTLY:
        - A 3/6-digit hex color (with or without
        - An RGB color, e.g., "rgb(255,0,0)"
        - An RGBA color, e.g., "rgba(255,0,0,0.5)"
        Returns False for partial matches (e.g., "x#FF0000", "123abc").
        """
        if self.parent.data_helper.validate_string(
            text, "text from is_color_code"
        ) and re.fullmatch(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", text):
            return True
        if self.parent.data_helper.validate_string(text, "text from is_color_code"):
            if re.fullmatch(
                r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", text
            ):
                r, g, b = map(int, re.findall(r"\d+", text))
                return all(0 <= c <= 255 for c in (r, g, b))
            if re.fullmatch(
                r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([01]?\.\d+)\s*\)$",
                text,
            ):
                r, g, b, a = map(float, re.findall(r"[\d.]+", text))
                return all(0 <= c <= 255 for c in (r, g, b)) and (0 <= a <= 1)
        return False

    def get_contrast_color(self, color):
        """
        Calculate contrasting color (black or white) for:
        - Hex strings (e.g., "#FF0000", "F00", "FF0000")
        - RGB tuples (e.g., (255, 0, 0))
        """
        if self.parent.data_helper.validate_string(
            color, "color from get_contrast_color"
        ):
            hex_color = color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])
            rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        elif (
            self.parent.data_helper.validate_list(color, element_type=(tuple, list))  # pyright: ignore
            and len(color) == 3
        ):
            rgb = tuple(color)
        else:
            raise ValueError(
                "Input must be a hex string (e.g., '#FF0000') or RGB tuple (e.g., (255, 0, 0))"
            )
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return "#000000" if luminance > 0.5 else "#ffffff"

    def format_color_text(self, text):
        """Wrap color codes in markup with proper background/foreground colors."""
        text = self.parent.glib.markup_escape_text(text)
        color_pattern = re.compile(r"(?<!\w)(#?[0-9a-fA-F]{3}|#?[0-9a-fA-F]{6})(?!\w)")

        def replace_color(match):
            color = match.group(1)
            if not color.startswith("#"):
                color = f"#{color}"
            fg_color = self.get_contrast_color(color)
            return f'<span background="{color}" foreground="{fg_color}">{match.group(1)}</span>'

        return color_pattern.sub(replace_color, text)

    def shannon_entropy(self, s: str) -> float:
        """
        Calculate the Shannon entropy of a string.
        Entropy measures the randomness of the string:
        higher values indicate more unpredictability.
        Args:
            s (str): Input string.
        Returns:
            float: Shannon entropy of the string.
        """
        if not s:
            return 0.0
        counts = Counter(s)
        length = len(s)
        return -sum(
            (count / length) * math.log2(count / length) for count in counts.values()
        )

    def is_likely_password(self, text: str) -> bool:
        """
        Determine if a string is likely a password using refined heuristics.
        Heuristics include:
        - Length constraints (8-64 chars)
        - Exclusion of strings with multiple spaces (filters natural language)
        - Exclusion of emails and URLs
        - Exclusion of code-like strings containing parentheses
        - Character type diversity (requires 3+ types)
        - A restored minimum entropy threshold
        Args:
            text (str): Input string to evaluate.
        Returns:
            bool: True if the string is likely a password, False otherwise.
        """
        if len(text) < 8 or len(text) > 64:
            return False
        if " " in text and text.count(" ") > 2:
            return False
        if re.match(r"^\S+@\S+\.\S+$", text):
            return False
        if re.match(r"^(http|https)://", text):
            return False
        if "(" in text and ")" in text:
            return False
        has_lower = any(c.islower() for c in text)
        has_upper = any(c.isupper() for c in text)
        has_digit = any(c.isdigit() for c in text)
        has_special = any(c in string.punctuation for c in text)
        types_count = sum([has_lower, has_upper, has_digit, has_special])
        if types_count < 3:
            return False
        entropy = self.shannon_entropy(text)
        if entropy < 3.0:
            return False
        return True
