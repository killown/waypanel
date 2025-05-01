import asyncio

global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
