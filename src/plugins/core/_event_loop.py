import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

_GLOBAL_EXECUTOR: Optional[ThreadPoolExecutor] = None
_GLOBAL_LOOP: Optional[asyncio.AbstractEventLoop] = None


def get_global_loop() -> asyncio.AbstractEventLoop:
    """
    Returns the global asyncio event loop instance.

    If the loop has not been initialized, it creates a new one. This approach
    bypasses the deprecated asyncio policy system by maintaining a local
    singleton reference.

    Returns:
        asyncio.AbstractEventLoop: The active global event loop.
    """
    global _GLOBAL_LOOP
    if _GLOBAL_LOOP is None:
        _GLOBAL_LOOP = asyncio.new_event_loop()
    return _GLOBAL_LOOP


def get_global_executor() -> ThreadPoolExecutor:
    """
    Returns the global thread pool executor.

    Returns:
        ThreadPoolExecutor: The shared executor for blocking operations.
    """
    global _GLOBAL_EXECUTOR
    if _GLOBAL_EXECUTOR is None:
        max_workers = (os.cpu_count() or 1) + 4
        _GLOBAL_EXECUTOR = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="WaypanelWorker"
        )
    return _GLOBAL_EXECUTOR
