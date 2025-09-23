import gi
import os
import tomllib
import tomli_w
import rapidfuzz
from typing import Dict, Any

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib, Adw, Gdk
from src.shared.notify_send import Notifier


class ControlCenter(Adw.Application):
    """
    A GTK4/Adwaita application for managing Waypanel configuration files.
    """

    def __init__(self):
        """
        Initializes the application, setting up configuration paths and data structures.
        """
        super().__init__(application_id="org.waypanel.ControlCenter")
        self.config = {}
        self.config_path = os.path.expanduser("~/.config/waypanel/config.toml")
        self.widget_map = {}
        self.notifier = Notifier()

    def code_explanation(self):
        """
        This method explains the core logic of the MyControlCenter application.

        The application is built using the GTK4 toolkit and the Adwaita library for a modern look and feel.
        Its primary purpose is to provide a graphical user interface (GUI) for editing a configuration file,
        specifically a TOML file.

        The application's logic is structured around three main phases:

        1.  **Initialization and UI Setup**:
            - The `__init__` method sets up essential paths and an empty configuration dictionary.
            - The `do_activate` method builds the main application window, including the header bar,
              a sidebar (`Gtk.ListBox`) for categories, and a content area (`Gtk.Stack`) to display
              the settings for the selected category. The `save_button_stack` is used to
              dynamically show or hide the Save button.

        2.  **Configuration Loading and Widget Creation**:
            - The `load_config` method attempts to read the `config.toml` file. If the file is not
              found or is invalid, the application starts with an empty configuration, which is
              handled gracefully by displaying a message to the user.
            - The `setup_categories` method populates the sidebar with a `Gtk.ListBoxRow` for each
              top-level category in the TOML file. It also sets a property on each row to store
              the original, unformatted category name, ensuring the `Gtk.Stack` displays the
              correct content page.
            - The `create_content_page` method is the core of the UI generation. It iterates through
              a category's data and dynamically creates widgets based on the data type:
                - Simple key-value pairs (`str`, `int`, `float`, `bool`) are displayed in a `Gtk.Grid`
                  using appropriate widgets like `Gtk.Entry`, `Gtk.SpinButton`, or `Gtk.Switch`.
                - Nested dictionaries are handled by the `create_nested_widgets` method, which
                  recursively calls itself to create expandable sections (`Gtk.Expander`).
                - Lists of dictionaries (e.g., for scripts) are handled by the `Notes_widgets`
                  method, which creates a user-friendly, structured view for each item in the list.
            - The `widget_map` dictionary is crucial for state management, as it stores a reference
              to every created widget, allowing the application to retrieve their values later.

        3.  **Saving and Feedback**:
            - The `on_save_clicked` method is triggered by the save button. It identifies the currently
              active category page.
            - The `save_category` method, with the help of the nested `update_config_from_widgets`
              function, traverses the `widget_map` and updates the `self.config` dictionary with the
              current values from the widgets. This includes handling simple values, nested dictionaries,
              and lists of dictionaries.
            - Finally, the `tomli_w.dump` function writes the updated `self.config` dictionary back to
              the `config.toml` file, and a `notify-send` command is used to provide the user with a
              desktop notification confirming the successful save.
        """
        return self.code_explanation.__doc__

    def create_content_page(self, category_name, data: Dict[str, Any]):
        """
        Creates a content page for a given configuration category.
        """
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)

        page_title = Gtk.Label(
            label=f"<b>{category_name.replace('_', ' ').capitalize()} Settings</b>",
            xalign=0,
        )
        page_title.set_use_markup(True)
        main_box.prepend(page_title)

        grid = Gtk.Grid()
        grid.set_column_spacing(20)
        grid.set_row_spacing(10)
        grid.set_column_homogeneous(False)
        main_box.append(grid)

        size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self.widget_map[category_name] = {}

        row_count = 0
        for key, value in data.items():
            if isinstance(value, dict):
                expander = Gtk.Expander.new(
                    f"<b>{key.replace('_', ' ').capitalize()}</b>"
                )
                expander.set_use_markup(True)
                self.widget_map[category_name][key] = {}
                expander_content = self.create_nested_widgets(
                    self.widget_map[category_name][key], value
                )
                expander.set_child(expander_content)
                main_box.append(expander)
            elif isinstance(value, list) and all(
                isinstance(item, dict) for item in value
            ):
                expander = Gtk.Expander.new(
                    f"<b>{key.replace('_', ' ').capitalize()}</b>"
                )
                expander.set_use_markup(True)
                self.widget_map[category_name][key] = []
                list_content_box = self.create_list_widgets(
                    self.widget_map[category_name][key], value
                )
                expander.set_child(list_content_box)
                main_box.append(expander)
            else:
                label = Gtk.Label(
                    label=key.replace("_", " ").capitalize() + ":", xalign=0
                )
                label.set_halign(Gtk.Align.START)
                label.set_hexpand(False)
                size_group.add_widget(label)

                widget = self.create_widget_for_value(value)
                if widget:
                    if isinstance(widget, Gtk.Entry):
                        widget.set_hexpand(True)
                    else:
                        widget.set_hexpand(False)

                    grid.attach(label, 0, row_count, 1, 1)
                    grid.attach(widget, 1, row_count, 1, 1)

                    self.widget_map[category_name][key] = widget

                row_count += 1

        scrolled_window.set_child(main_box)
        return scrolled_window

    def create_list_widgets(self, widget_list, data_list):
        """
        Creates widgets for a list of dictionaries.
        """
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for i, item_dict in enumerate(data_list):
            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            item_box.add_css_class("card")
            item_box.set_margin_top(5)
            item_box.set_margin_bottom(5)

            name_label = Gtk.Label(label=item_dict.get("name", "Untitled"), xalign=0)
            name_label.set_halign(Gtk.Align.START)
            name_label.add_css_class("title-4")
            item_box.append(name_label)

            cmd_label = Gtk.Label(label="Command:", xalign=0)
            cmd_entry = Gtk.Entry()
            cmd_entry.set_text(item_dict.get("cmd", ""))
            cmd_entry.set_hexpand(True)

            cmd_grid = Gtk.Grid()
            cmd_grid.set_column_spacing(10)
            cmd_grid.attach(cmd_label, 0, 0, 1, 1)
            cmd_grid.attach(cmd_entry, 1, 0, 1, 1)

            item_box.append(cmd_grid)
            list_box.append(item_box)

            widget_list.append({"name_label": name_label, "cmd_entry": cmd_entry})

        return list_box

    def create_nested_widgets(self, widget_dict, subdict):
        """
        Recursively creates widgets for nested dictionaries.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid = Gtk.Grid()
        grid.set_column_spacing(20)
        grid.set_row_spacing(10)
        grid.set_column_homogeneous(False)

        row_count = 0
        for key, value in subdict.items():
            if isinstance(value, dict):
                expander = Gtk.Expander.new(
                    f"<b>{key.replace('_', ' ').capitalize()}</b>"
                )
                expander.set_use_markup(True)
                widget_dict[key] = {}
                nested_box = self.create_nested_widgets(widget_dict[key], value)
                expander.set_child(nested_box)
                box.append(expander)
            elif isinstance(value, list) and all(
                isinstance(item, dict) for item in value
            ):
                expander = Gtk.Expander.new(
                    f"<b>{key.replace('_', ' ').capitalize()}</b>"
                )
                expander.set_use_markup(True)
                widget_dict[key] = []
                list_content_box = self.create_list_widgets(widget_dict[key], value)
                expander.set_child(list_content_box)
                box.append(expander)
            else:
                label = Gtk.Label(
                    label=key.replace("_", " ").capitalize() + ":", xalign=0
                )
                label.set_halign(Gtk.Align.START)
                label.set_hexpand(False)

                widget = self.create_widget_for_value(value)
                if widget:
                    if isinstance(widget, Gtk.Entry):
                        widget.set_hexpand(True)
                    else:
                        widget.set_hexpand(False)

                    grid.attach(label, 0, row_count, 1, 1)
                    grid.attach(widget, 1, row_count, 1, 1)

                    widget_dict[key] = widget

                row_count += 1

        if row_count > 0:
            box.prepend(grid)

        return box

    def create_widget_for_value(self, value: Any):
        """
        Creates a Gtk widget based on the data type of the value.
        """
        if isinstance(value, str):
            entry = Gtk.Entry()
            entry.set_text(value)
            entry.set_width_chars(30)
            entry.set_max_width_chars(50)
            return entry
        elif isinstance(value, int) or isinstance(value, float):
            entry = Gtk.SpinButton()
            adjustment = Gtk.Adjustment(
                value=float(value),
                lower=-10000.0,
                upper=10000.0,
                step_increment=1.0,
                page_increment=10.0,
                page_size=0.0,
            )
            entry.set_adjustment(adjustment)
            entry.set_width_chars(15)
            entry.set_max_width_chars(20)
            return entry
        elif isinstance(value, bool):
            switch = Gtk.Switch()
            switch.set_active(value)
            return switch
        elif isinstance(value, list):
            entry = Gtk.Entry()
            entry.set_text(", ".join(map(str, value)))
            entry.set_sensitive(True)
            entry.set_width_chars(30)
            entry.set_max_width_chars(50)
            return entry
        else:
            value_label = Gtk.Label(label=str(value), xalign=0)
            return value_label

    def do_activate(self):
        """
        Activates the application, creating and showing the main window.
        """
        self.win = self.props.active_window
        if not self.win:
            self.win = Adw.ApplicationWindow(application=self)
            self.win.set_title("Waypanel Control Center")
            self.win.set_default_size(800, 600)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.win.set_content(vbox)

            header_bar = Adw.HeaderBar()
            vbox.append(header_bar)

            self.save_button = Gtk.Button(label="Save")
            self.save_button.add_css_class("suggested-action")
            self.save_button.connect("clicked", self.on_save_clicked)

            self.save_button_stack = Gtk.Stack()
            self.save_button_stack.set_vexpand(False)
            self.save_button_stack.set_hexpand(False)

            empty_box = Gtk.Box()
            self.save_button_stack.add_named(empty_box, "empty")
            self.save_button_stack.add_named(self.save_button, "save_button")
            self.save_button_stack.set_visible_child_name("empty")

            header_bar.pack_end(self.save_button_stack)

            main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            vbox.append(main_box)

            left_panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            left_panel_box.set_size_request(300, -1)
            left_panel_box.set_hexpand(False)

            left_listbox = Gtk.ListBox()
            left_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_child(left_listbox)
            scrolled_window.set_vexpand(True)
            scrolled_window.set_hexpand(False)
            scrolled_window.set_size_request(300, -1)

            left_panel_box.append(scrolled_window)
            main_box.append(left_panel_box)

            right_wrapper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            right_wrapper.set_hexpand(True)
            right_wrapper.set_vexpand(True)
            main_box.append(right_wrapper)

            self.content_stack = Gtk.Stack()
            self.content_stack.set_size_request(500, -1)
            self.content_stack.set_hexpand(False)
            self.content_stack.set_vexpand(True)
            right_wrapper.append(self.content_stack)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            right_wrapper.append(spacer)

            self.load_config()
            self.setup_categories(left_listbox, self.content_stack)

            left_listbox.connect("row-activated", self.on_category_activated)
            if left_listbox.get_row_at_index(0):
                left_listbox.select_row(left_listbox.get_row_at_index(0))

        self.win.present()

    def get_icon_for_category(self, category_name: str) -> str:
        """
        Finds a suitable icon for a given category name using a tiered search.
        It uses the first word of a multi-word category name to find an icon.

        Args:
            category_name (str): The name of the configuration category.

        Returns:
            str: The name of the best-matching icon, or a fallback if none is found.
        """

        norm_name = category_name.replace("_", " ").split()[0].lower()

        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())

        # Tier 1: Direct matches and common patterns
        icon_patterns = [
            norm_name,
            f"{norm_name}-symbolic",
            f"preferences-{norm_name}-symbolic",
            f"utilities-{norm_name}-symbolic",
        ]

        for icon_name in icon_patterns:
            if icon_theme.has_icon(icon_name):
                return icon_name

        # Tier 2: Check first word for better matching on multi-word names
        norm_name_patterns = [
            norm_name,
            f"{norm_name}-symbolic",
            f"preferences-{norm_name}-symbolic",
            f"utilities-{norm_name}-symbolic",
        ]
        for icon_name in norm_name_patterns:
            if icon_theme.has_icon(icon_name):
                return icon_name

        # Tier 3: Search a list of hardcoded fallbacks
        fallback_map = {
            "wayfire": "preferences-desktop-display-symbolic",
            "scripts": "utilities-terminal-symbolic",
            "wallpaper": "preferences-desktop-wallpaper-symbolic",
            "panel": "preferences-system-symbolic",
            "settings": "preferences-system-symbolic",
            "theme": "preferences-desktop-theme-symbolic",
            "colors": "preferences-desktop-color-symbolic",
            "keyboard": "input-keyboard-symbolic",
            "mouse": "input-mouse-symbolic",
            "network": "network-wired-symbolic",
            "app-launcher": "system-run-symbolic",
            "powermenu": "system-shutdown-symbolic",
            "main": "preferences-panel-symbolic",
            "folders": "folder",
            "menu": "application-menu",
            "launcher": "app-launcher",
            "cmd": "terminal",
        }

        if norm_name in fallback_map:
            return fallback_map[norm_name]

        # Tier 4: Fuzzy matching as a last resort
        try:
            all_icons = icon_theme.get_icon_names()
            processed_all_icons = [name.lower() for name in all_icons]

            best_match = rapidfuzz.process.extractOne(
                query=norm_name,
                choices=processed_all_icons,
                scorer=rapidfuzz.fuzz.token_set_ratio,
                score_cutoff=65,
            )
            if best_match:
                return best_match[0]

        except NameError:
            pass

        return "preferences-system-symbolic"

    def load_config(self):
        """
        Loads the configuration from the TOML file.
        """
        try:
            with open(self.config_path, "rb") as f:
                self.config = tomllib.load(f)
        except FileNotFoundError:
            self.config = {}
        except Exception as e:
            self.config = {}

    def on_category_activated(self, listbox, row):
        """
        Handles the activation of a category row in the sidebar.
        """
        category_name = row.get_property("name")
        self.content_stack.set_visible_child_name(category_name)
        self.save_button_stack.set_visible_child_name("save_button")

    def on_save_clicked(self, button):
        """
        Handles the "Save" button click event.
        """
        current_category = self.content_stack.get_visible_child_name()
        if current_category:
            self.save_category(current_category)

    def save_category(self, category_name):
        """
        Saves the configuration for a specific category to the TOML file.
        """

        def get_value_from_widget(widget):
            if isinstance(widget, Gtk.Entry):
                text = widget.get_text()
                if "," in text:
                    return [x.strip() for x in text.split(",")]
                try:
                    return int(text)
                except (ValueError, TypeError):
                    try:
                        return float(text)
                    except (ValueError, TypeError):
                        return text
            elif isinstance(widget, Gtk.SpinButton):
                return widget.get_value()
            elif isinstance(widget, Gtk.Switch):
                return widget.get_active()
            return None

        def update_config_from_widgets(config_dict, widget_dict):
            for key, value in widget_dict.items():
                if isinstance(value, dict):
                    if key in config_dict:
                        update_config_from_widgets(config_dict[key], value)
                elif isinstance(value, list):
                    if key in config_dict and isinstance(config_dict[key], list):
                        for i, list_item_widgets in enumerate(value):
                            if i < len(config_dict[key]):
                                cmd_entry = list_item_widgets.get("cmd_entry")
                                if cmd_entry:
                                    config_dict[key][i]["cmd"] = get_value_from_widget(
                                        cmd_entry
                                    )
                else:
                    new_value = get_value_from_widget(value)
                    if new_value is not None:
                        config_dict[key] = new_value

        if category_name in self.widget_map:
            if category_name in self.config:
                update_config_from_widgets(
                    self.config[category_name], self.widget_map[category_name]
                )
            else:
                return

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "wb") as f:
                tomli_w.dump(self.config, f)

            self.notifier.notify_send(
                "Waypanel Config",
                f"The {category_name.replace('_', ' ').capitalize()} settings have been saved successfully!",
                "configure-symbolic",
            )

        except Exception as e:
            pass

    def setup_categories(self, listbox, stack):
        """
        Sets up the categories in the sidebar and the corresponding content pages,
        sorted alphabetically by category name.
        """
        self.widget_map = {}
        if not self.config:
            label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            label = Gtk.Label(
                label="No configuration file found or loaded.\n\n"
                "Please create a file at ~/.config/waypanel/config.toml\n"
                "and restart the application.",
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
                justify=Gtk.Justification.CENTER,
            )
            label.set_wrap(True)
            label_box.append(label)
            stack.add_named(label_box, "no_config")
            stack.set_visible_child_name("no_config")
            return

        sorted_category_names = sorted(self.config.keys())

        for category_name in sorted_category_names:
            category_data = self.config[category_name]
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(10)
            box.set_margin_end(10)

            icon_name = self.get_icon_for_category(category_name)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(48)
            box.append(icon)

            display_name = category_name.replace("_", " ").capitalize()
            label = Gtk.Label(
                label=f'<b><span size="12288">{display_name}</span></b>', xalign=0
            )
            label.set_use_markup(True)
            box.append(label)
            row.set_child(box)
            listbox.append(row)

            row.set_property("name", category_name)

            content_page = self.create_content_page(category_name, category_data)
            stack.add_named(content_page, category_name)


if __name__ == "__main__":
    app = MyControlCenter()
    app.run(None)
