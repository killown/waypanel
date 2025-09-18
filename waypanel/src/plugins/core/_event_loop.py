import asyncio
from concurrent.futures import ThreadPoolExecutor

global_executor = ThreadPoolExecutor(max_workers=4)
global_loop = asyncio.new_event_loop()


def get_global_loop():
    return global_loop


def get_global_executor():
    return global_executor
