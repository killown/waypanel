import gi
from gi.repository import Gdk, Gtk

gi.require_version('Gtk', '4.0')


def get_nearest_icon_name(app_name: str, size=Gtk.IconSize.LARGE) -> str:
    """
    Get the best matching icon name for an application (GTK4 synchronous version).
    Returns immediately with the icon name or fallback.

    Args:
        app_name: Application name (e.g. 'firefox')
        size: Preferred icon size (Gtk.IconSize)

    Returns:
        Best matching icon name with fallbacks
    """
    icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    app_name = app_name.lower().strip()

    # Ordered list of possible icon name patterns
    patterns = [
        # Application-specific
        app_name,
        f"{app_name}-symbolic",
        f"org.{app_name}.Desktop",
        f"{app_name}-desktop",

        # Generic formats
        f"application-x-{app_name}",
        f"system-{app_name}",
        f"utility-{app_name}",

        # Vendor prefixes
        f"fedora-{app_name}",
        f"debian-{app_name}",
    ]

    # Check exact matches first
    for pattern in patterns:
        if icon_theme.has_icon(pattern):
            return pattern

    # Search for partial matches
    try:
        all_icons = icon_theme.get_icon_names()
        matches = [icon for icon in all_icons if app_name in icon.lower()]
        if matches:
            return matches[0]  # Return first match
    except Exception as e:
        print(f"Icon search error: {e}")

    # Final fallbacks
    for fallback in ["application-x-executable", "image-missing", "gtk-missing-image"]:
        if icon_theme.has_icon(fallback):
            return fallback

    return "image-missing"
