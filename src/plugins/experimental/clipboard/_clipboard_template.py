class Helpers:
    def __init__(self, parent) -> None:
        self.parent = parent

    def apply_hints(self):
        self.parent.add_hint(
            ["The minimum width (in pixels) of the clipboard history popover."],
            [
                "client",
                "popover_min_width",
            ],
        )
        self.parent.add_hint(
            [
                "The maximum height (in pixels) of the clipboard history popover. The list will scroll if content exceeds this height."
            ],
            [
                "client",
                "popover_max_height",
            ],
        )
        self.parent.add_hint(
            [
                "The maximum size (width/height in pixels) for image thumbnails displayed in the history."
            ],
            [
                "client",
                "thumbnail_size",
            ],
        )
        self.parent.add_hint(
            [
                "The maximum number of characters of the clipboard content to display before truncating with '...'. Does not apply to pinned items with custom labels."
            ],
            [
                "client",
                "preview_text_length",
            ],
        )
        self.parent.add_hint(
            [
                "The fixed height (in pixels) used for rows containing image content, controlling the space allocated for the thumbnail."
            ],
            [
                "client",
                "image_row_height",
            ],
        )
        self.parent.add_hint(
            [
                "The fixed height (in pixels) used for rows primarily containing text content."
            ],
            [
                "client",
                "text_row_height",
            ],
        )
        self.parent.add_hint(
            [
                "The vertical spacing (in pixels) between individual items (rows) in the list."
            ],
            [
                "client",
                "item_spacing",
            ],
        )
        self.parent.add_hint(
            [
                "If True, the server will log every successful item addition and deletion to the waypanel log file. This is mostly for debugging the server operation."
            ],
            [
                "server",
                "log_enabled",
            ],
        )
        self.parent.add_hint(
            [
                "The maximum number of non-pinned clipboard items to store in the database. When the limit is reached, the oldest non-pinned item is deleted."
            ],
            [
                "server",
                "max_items",
            ],
        )
        self.parent.add_hint(
            [
                "The delay (in seconds) between checks for new clipboard content. Decreasing this value makes the history faster but consumes slightly more CPU."
            ],
            [
                "server",
                "monitor_interval",
            ],
        )
