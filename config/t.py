import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import toml


class TOMLEditor(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="TOML Editor")
        self.set_default_size(800, 600)

        # Initialize data attribute
        self.data = {}

        # Create a notebook (tabs container)
        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        # Add initial tab
        self.add_new_tab()

        # Add button to create new tab
        add_tab_button = Gtk.Button(label="Add Tab")
        add_tab_button.connect("clicked", self.on_add_tab_clicked)
        self.add(add_tab_button)

    def add_new_tab(self):
        # Create a scrolled window for each tab
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_border_width(10)

        # Create a grid for each tab
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(5)
        scrolled_window.add(grid)

        # Add labels and entry fields for each editable value
        row = 0
        for section, items in self.data.items():
            section_label = Gtk.Label(label=section)
            grid.attach(section_label, 0, row, 2, 1)

            row += 1
            for item_key, item_value in items.items():
                if isinstance(item_value, list):
                    for idx, item in enumerate(item_value):
                        for key, value in item.items():
                            key_label = Gtk.Label(label=f"{item_key} - {key}")
                            grid.attach(key_label, 0, row, 1, 1)

                            entry = Gtk.Entry()
                            entry.set_text(str(value))
                            entry.set_hexpand(True)  # Expand horizontally
                            entry.set_size_request(300, -1)  # Set minimum width
                            entry.connect(
                                "changed",
                                self.on_entry_changed,
                                section,
                                item_key,
                                idx,
                                key,
                            )
                            grid.attach(entry, 1, row, 1, 1)

                            row += 1
                else:
                    key_label = Gtk.Label(label=item_key)
                    grid.attach(key_label, 0, row, 1, 1)

                    entry = Gtk.Entry()
                    entry.set_text(str(item_value))
                    entry.set_hexpand(True)  # Expand horizontally
                    entry.set_size_request(300, -1)  # Set minimum width
                    entry.connect("changed", self.on_entry_changed, section, item_key)
                    grid.attach(entry, 1, row, 1, 1)

                    row += 1

        # Add the grid to a new tab
        tab_label = Gtk.Label(label="New Tab")
        self.notebook.append_page(scrolled_window, tab_label)

    def on_entry_changed(self, entry, section, item_key, idx=None, key=None):
        value = entry.get_text()
        if idx is None:
            self.data[section][item_key] = value
        else:
            self.data[section][item_key][idx][key] = value

    def save_toml_data(self):
        with open(self.file_path, "w") as file:
            toml.dump(self.data, file)

    def on_add_tab_clicked(self, button):
        self.add_new_tab()


win = TOMLEditor()
win.connect("destroy", Gtk.main_quit)

# Add a save button
save_button = Gtk.Button(label="Save")
save_button.connect("clicked", lambda button: win.save_toml_data())
win.add(save_button)

win.show_all()
Gtk.main()
