---

## For power users / developers

- **Dev mode:** When developing, `run.py` prefers installed package paths but can run from the repo (dev path). It sets `PYTHONPATH` accordingly so your local `src/` is used if running from the cloned repo. This makes iterative development simple.
- **Logging & debugging:**

- **Plugin Imports Rule:** **Plugins MUST NOT use top-level imports** (i.e., imports outside of functions or class methods). All dependencies (`gi`, `Gtk`, `BasePlugin`, etc.) must be imported inside `get_plugin_class()` to prevent loading issues and maintain a clean global namespace.

- **Plugin lifecycle:**

  Use `BasePlugin` as a superclass for common helpers (ipc, notifier, gtk helpers). It provides `enable()`, `disable()`, and safe widget removal helpers. See the plugin core docs for event subscriptions and threading details.

---
