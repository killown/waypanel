from concurrent.futures import Future
from asyncio import Task
from typing import Any, Callable, Optional, Set, Awaitable
from gi.repository import GLib  # pyright: ignore
from src.plugins.core._event_loop import get_global_executor, get_global_loop


class ConcurrencyHelper:
    """
    Reusable helper class to manage all asynchronous and threading operations
    for a plugin, ensuring automatic task tracking and safe cleanup during disable.
    """

    def __init__(self, plugin_instance: Any):
        self._plugin = plugin_instance
        self.global_loop = get_global_loop()
        self.global_executor = get_global_executor()
        self._running_futures: Set[Future[Any]] = set()
        self._running_tasks: Set[Task] = set()

    @property
    def logger(self):
        """Access the plugin's logger."""
        return self._plugin.logger

    def run_in_thread(self, func: Callable, *args, **kwargs) -> Future:
        """
        Executes a blocking function in a background thread via the shared executor.
        The resulting Future is automatically tracked for cleanup.
        """
        self.logger.debug(f"Scheduling function {func.__name__} in background thread.")
        future = self.global_executor.submit(func, *args, **kwargs)
        self._running_futures.add(future)
        future.add_done_callback(self._cleanup_future)
        return future

    def _cleanup_future(self, future: Future[Any]):
        """Internal callback to remove a Future from the tracking set once it's done."""
        try:
            if future in self._running_futures:
                self._running_futures.remove(future)
        except Exception as e:
            self.logger.error(f"Error cleaning up Future tracking: {e}")

    def schedule_in_gtk_thread(self, func: Callable, *args, **kwargs) -> None:
        """
        Schedules a function to be executed in the main GTK (GLib) thread.
        Crucial for any UI updates.
        """

        def wrapper():
            try:
                func(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"Error executing function {func.__name__} in GTK thread: {e}",
                    exc_info=True,
                )
            return GLib.SOURCE_REMOVE

        GLib.idle_add(wrapper)
        self.logger.debug(f"Scheduled function {func.__name__} in GTK main thread.")

    def run_in_async_task(
        self,
        coro: Awaitable[Any],
        on_finish: Optional[Callable[[Any], None]] = None,
    ) -> None:
        """
        Schedules an awaitable (async def function) to run as a task in the
        background asyncio loop. The task is tracked for cleanup.
        """
        coro_name = getattr(coro, "__name__", repr(coro).split(" object")[0])

        def done_callback(task: Task[Any]):
            if task in self._running_tasks:
                self._running_tasks.remove(task)
            if task.cancelled():
                self.logger.debug(f"Async task {coro_name} cancelled.")
                return
            exception = task.exception()
            if exception:
                self.logger.error(
                    f"Async task {coro_name} raised exception: {exception}",
                    exc_info=True,
                )
            elif on_finish:
                self.schedule_in_gtk_thread(on_finish, task.result())

        task = self.global_loop.create_task(coro)
        self._running_tasks.add(task)
        task.add_done_callback(done_callback)
        self.logger.debug(f"Scheduled async task {coro_name} in global loop.")

    def cleanup_tasks_and_futures(self):
        """Safely cancels all active background tasks and futures when the plugin is disabled."""
        self.logger.debug("Starting concurrent task cleanup...")
        for task in list(self._running_tasks):
            if not task.done():
                task.cancel()
                task_name = getattr(task, "get_name", lambda: "Unnamed Task")()
                self.logger.debug(f"Attempted to cancel async task: {task_name}")
        for future in list(self._running_futures):
            if not future.done():
                future.cancel()
                self.logger.debug("Attempted to cancel thread Future.")
        self.logger.info("Concurrent tasks cleanup complete.")
