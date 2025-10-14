from concurrent.futures import Future
from asyncio import Task
from typing import Any, Callable, Optional, Set, Awaitable
from gi.repository import GLib  # pyright: ignore
from src.plugins.core._event_loop import get_global_executor, get_global_loop
import asyncio


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
        if future in self._running_futures:
            self._running_futures.remove(future)

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
        background asyncio loop using the thread-safe API (asyncio.run_coroutine_threadsafe).
        This guarantees safe execution when called from the GTK thread.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.global_loop)
        self._running_futures.add(future)
        coro_name = getattr(coro, "__qualname__", repr(coro).split(" object")[0])

        def done_callback(future: Future[Any]):
            """Handles completion, cancellation, and exceptions."""
            if future in self._running_futures:
                self._running_futures.remove(future)
            if future.cancelled():
                self.logger.debug(f"Async coroutine {coro_name} submission cancelled.")
                return
            try:
                exception = future.exception()
                if exception:
                    self.logger.error(
                        f"Async coroutine {coro_name} execution failed: {exception}",
                        exc_info=True,
                    )
                elif on_finish:
                    self.schedule_in_gtk_thread(on_finish, future.result())
            except Exception as e:
                self.logger.error(
                    f"Error processing completion of async coroutine {coro_name}: {e}",
                    exc_info=True,
                )

        future.add_done_callback(done_callback)
        self.logger.debug(f"Scheduled async coroutine {coro_name} via threadsafe API.")

    def cleanup_tasks_and_futures(self):
        """Safely cancels all active background tasks and futures when the plugin is disabled."""
        self.logger.debug("Starting concurrent task cleanup...")
        for future in list(self._running_futures):
            if not future.done():
                future.cancel()
                self.logger.debug(
                    "Attempted to cancel thread Future/Async Coroutine Future."
                )
        for task in list(self._running_tasks):
            if not task.done():
                task.cancel()
                task_name = getattr(task, "get_name", lambda: "Unnamed Task")()
                self.logger.debug(
                    f"Attempted to cancel explicit async task: {task_name}"
                )
        self.logger.info("Concurrent tasks cleanup complete.")
