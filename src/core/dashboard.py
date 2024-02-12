import sys
import gi
gi.require_version('Gtk', '4.0')

from gi.repository import Gtk,Gio,Gdk,Adw
from src.core.utils import Utils

css = b"""
        .h1 {
            font-size: 24px;
        }
        .h2 {
            font-weight: 300;
            font-size: 18px;
        }
        .h3 {
            font-size: 11px;
        }
        .h4 {
            color: alpha (@text_color, 0.7);
            font-weight: bold;
            text-shadow: 0 1px @text_shadow_color;
        }
        .icons {
            -gtk-icon-size: 48px;
        }
        """

class MainWindow(Adw.Window):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_ = self.get_application()
        self.set_default_size(600, 400)
        self.set_title("dashboard")
        self.utils = Utils(application_id="com.github.utils")
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display().get_default(),
                                                 style_provider, 
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.main_box = Gtk.Box.new( Gtk.Orientation.VERTICAL,0) #(orientation VERTICAL|HORIZONTAL  , spacing in pixels)
        self.set_content(self.main_box)
        self.set_modal(True)

        self.stack = Gtk.Stack.new()
        self.stack.props.hexpand = True
        self.stack.props.vexpand = True
        data_and_categories = {
                 ("Firefox" ,"Web Browser"            ,"firefox")    : "Internet",
                 ("Chromium","Web Browser"            ,"chromium")      : "Internet",
                 ("Webcord"   ,"Web Browser"            ,"webcord")              : "Internet",
                 ("gnome-terminal"   ,"Web Browser"            ,"gnome-terminal") : "Internet",
                 ("nautilus" ,"Web Browser"            ,"nautilus")            : "Internet",
                 ("Gimp"    ,"Image Manipulation"    ,"icons_folder/gimp.png")               : "Graphics",
                 ("Inkscape","svg Editor..."         ,"icons_folder/inkscape.png")           : "Graphics",
                 ("Krita"   ,"sketching and painting","icons_folder/krita.png")              : "Graphics",
                 ("Blender" ,"3D modeling..."        ,"icons_folder/Blender-icon.png")       : "Graphics",
                 ("Kdenlive","Video Editor..."       ,"icons_folder/kdenlive.png")           : "Graphics"
        }
        done = []
        for data,category in data_and_categories.items():
            if category not in done: # if flowbox not exist in stack
                sw  = Gtk.ScrolledWindow.new()
                print(data[2])
                flowbox = Gtk.FlowBox.new()
                sw.set_child(flowbox)
                flowbox.props.homogeneous = True
                flowbox.set_valign(Gtk.Align.START) # top to bottom
                flowbox.props.margin_start  = 20
                flowbox.props.margin_end    = 20
                flowbox.props.margin_top    = 20
                flowbox.props.margin_bottom = 20
                flowbox.props.hexpand = True
                flowbox.props.vexpand = True
                flowbox.props.max_children_per_line = 4
                flowbox.props.selection_mode = Gtk.SelectionMode.NONE
                self.stack.add_titled(sw,category,category) # Widget,name,title to show in Gtk.StackSidebar
                done.append(category)
            else: # if flowbox already exist in stack
                flowbox = self.stack.get_child_by_name(category).get_child().get_child() #Gtk.ScrolledWindow ===> get_child ====> Gtk.Viewport ===> get_child ====> Gtk.FlowBox


            icon_vbox = Gtk.Box.new( Gtk.Orientation.VERTICAL,0)
            icon_vbox.add_css_class("icons")
            icon = Adw.ButtonContent()
            icon.set_icon_name(data[2])#data[2] icons_folder/appicns_Firefox.png and ...

            # https://lazka.github.io/pgi-docs/#Gtk-4.0/classes/Image.html
            icon_vbox.append(icon)

            name_label = Gtk.Label.new(data[0]) #Firefox and ....
            name_label.add_css_class("h1") # look at css
            icon_vbox.append(name_label)

            summary_label = Gtk.Label.new(data[1])  #Web Browser and ....
            summary_label.add_css_class("h3") #look at css
            icon_vbox.append(summary_label)

            button = Gtk.Button.new()
            button.set_has_frame(False)
            button.set_child(icon_vbox)
            flowbox.append(button)
            button.connect("clicked",self.on_button_clicked,data[0]) 


        stack_switcher =  Gtk.StackSwitcher.new()
        stack_switcher.props.hexpand = False
        stack_switcher.props.vexpand = False
        stack_switcher.set_stack(self.stack)
        calendar = Gtk.Calendar()
        



        
        self.message_to_show_in_infobar = Gtk.Label(label="asdfasdfasdf")
        with open("/tmp/waypanel-notifications.txt","r") as file:
            message_limit = 6
            message_count = 0
            for label in reversed(file.readlines()):
                if message_count > message_limit:
                    break
                if label.startswith(":") or len(label) < 3:
                    continue
                infobar = Gtk.InfoBar.new()
                infobar.set_revealed(True) # hide
                infobar.set_show_close_button(True) # When clicked it emits the response Gtk.ResponseType.CLOSE
                #infobar.add_button("Yes", Gtk.ResponseType.YES ) # Action button on side.  When clicked it emits the response Gtk.ResponseType.YES
                #infobar.add_button("No", Gtk.ResponseType.NO ) # Action button on side. When clicked it emits the response Gtk.ResponseType.NO
                self.main_box.append(infobar)
                self.message_to_show_in_infobar = Gtk.Label(label=label)
                infobar.add_child(self.message_to_show_in_infobar)
                message_count += 1
        
        
        self.dashgrid = Gtk.Grid(column_spacing=10)
        self.calendarbox = Gtk.Box()
        self.infobarbox = Gtk.Box()
        self.infobarbox.append(infobar)
        self.calendarbox.append(calendar)
        self.dashgrid.attach(self.infobarbox, 1, 0, 1, 2)
        self.dashgrid.attach_next_to(
            self.calendarbox, self.infobarbox, Gtk.PositionType.RIGHT, 1, 2
        )
        
        self.main_box.append(self.dashgrid)
        #self.main_box.append(infobar)
        #self.main_box.append(stack_switcher)
        #self.main_box.append(self.stack)

    def on_button_clicked(self,button,programename):
        print(self.is_focus())
        self.utils.run_app(programename)
        self.close()
        

class Dashboard(Gtk.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def do_activate(self):
        active_window = self.props.active_window
        if active_window:
            active_window.present()
        else:
            self.win = MainWindow(application=self)
            self.win.present()

#app = MyApp(application_id="com.github.yucefsourani.myapplicationexample",flags= Gio.ApplicationFlags.FLAGS_NONE)
#app.run(sys.argv)
