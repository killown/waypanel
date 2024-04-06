import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GObject


class InvalidGioTaskError(Exception):
    pass


class AlreadyRunningError(Exception):
    pass


class Background(GObject.Object):
    __gtype_name__ = "BackgroundUtils"

    def __init__(self, function, finish_callback, **kwargs):
        super().__init__(**kwargs)
        self.function = function
        self.finish_callback = finish_callback
        self._current = None

    def start(self):
        if self._current:
            raise AlreadyRunningError("Task is already running")
        finish_callback = lambda self, task, nothing: self.finish_callback()
        task = Gio.Task.new(self, None, finish_callback, None)
        task.run_in_thread(self._thread_cb)
        self._current = task

    @staticmethod
    def _thread_cb(task, self, task_data, cancellable):
        try:
            retval = self.function()
            task.return_value(retval)
        except Exception as e:
            task.return_value(e)

    def finish(self):
        task = self._current
        self._current = None

        if not Gio.Task.is_valid(task, self):
            raise InvalidGioTaskError()

        value = task.propagate_value().value

        if isinstance(value, Exception):
            raise value

        return value
