import os

# List of all valid panel positions
VALID_POSITIONS = [
    "top-panel-left",
    "top-panel-center",
    "top-panel-right",
    "top-panel-systray",
    "top-panel-after-systray",
    "bottom-panel-left",
    "bottom-panel-center",
    "bottom-panel-right",
    "left-panel-top",
    "left-panel-center",
    "left-panel-bottom",
    "right-panel-top",
    "right-panel-center",
    "right-panel-bottom",
    "background",
]

PLUGIN_TEMPLATE = '''from gi.repository import Gtk, GLib
from waypanel.src.plugins.core._base import BasePlugin

ENABLE_PLUGIN = True  # Set to False to disable this plugin
DEPS = {deps}

def get_plugin_placement(panel_instance):
    """Define where the plugin should be placed in the panel."""
    position = "{position}"
    order = 10  # Adjust as needed
    priority = 10  # Lower numbers load earlier
    return position, order, priority

def initialize_plugin(panel_instance):
    if ENABLE_PLUGIN:
        return {plugin_class}(panel_instance)

class {plugin_class}(BasePlugin):
    def __init__(self, panel_instance):
        super().__init__(panel_instance)
        self.button = None
        self.main_widget = self.create_widget(), "append"

    def create_widget(self):
        """Create and return the widget shown in the panel."""
        self.button = Gtk.Button(label="{plugin_name}")
        self.button.connect("clicked", self.on_click)
        return self.button

    def on_click(self, _):
        print("{plugin_name} clicked!")
'''


def get_user_input():
    plugin_name = input("Enter plugin name (e.g., my_plugin): ").strip()
    if not plugin_name:
        print("Plugin name is required.")
        return None, None

    print("\nAvailable Positions:")
    for pos in VALID_POSITIONS:
        print(f" - {pos}")

    position = input("Enter position (choose from above): ").strip()
    if position not in VALID_POSITIONS:
        print("Invalid position selected.")
        return None, None

    return plugin_name, position


def determine_deps(position):
    """Determine which panels are required based on the position."""
    deps = []

    if position.startswith("top-panel"):
        deps.append("top_panel")
    elif position.startswith("bottom-panel"):
        deps.append("bottom_panel")
    elif position.startswith("left-panel"):
        deps.append("left_panel")
    elif position.startswith("right-panel"):
        deps.append("right_panel")

    return deps


def generate_plugin_file(plugin_name, position):
    plugin_dir = os.path.expanduser("~/.config/waypanel/plugins")
    os.makedirs(plugin_dir, exist_ok=True)
    plugin_path = os.path.join(plugin_dir, f"{plugin_name}.py")

    if os.path.exists(plugin_path):
        print(f"⚠️ A plugin named '{plugin_name}' already exists at {plugin_path}")
        overwrite = input("Do you want to overwrite it? (y/N): ").strip().lower()
        if overwrite != "y":
            print("Operation canceled.")
            return

    plugin_class = "".join(word.capitalize() for word in plugin_name.split("_"))
    deps = determine_deps(position)

    with open(plugin_path, "w") as f:
        f.write(
            PLUGIN_TEMPLATE.format(
                plugin_name=plugin_name,
                plugin_class=plugin_class,
                position=position,
                deps=str(deps) if deps else "[]",
            )
        )

    print(f"✅ Plugin '{plugin_name}' created successfully at {plugin_path}")


if __name__ == "__main__":
    plugin_name, position = get_user_input()
    if plugin_name and position:
        generate_plugin_file(plugin_name, position)
