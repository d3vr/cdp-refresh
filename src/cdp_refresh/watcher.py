# src/cdp_refresh/watcher.py
"""Handles file system watching using watchfiles."""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Callable, Set, Tuple, Optional, Awaitable

from watchfiles import Change, awatch


async def watch_directory(
    path: Path,
    callback: Callable[[], Awaitable[None]],
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Watches a directory for changes and calls an async callback until stop_event is set.

    Args:
        path: The directory path to watch.
        callback: An asynchronous function to call when changes are detected.
        stop_event: An asyncio.Event to signal when watching should stop.
    """
    print(f"Watcher: Starting to watch {path.resolve()}")
    if not stop_event:
        stop_event = asyncio.Event() # Create a dummy event if none provided

    try:
        async for changes in awatch(path, stop_event=stop_event):
            # Check if stop event was set during await
            if stop_event.is_set():
                print("Watcher: Stop event received, exiting watch loop.")
                break

            # changes is a set of tuples: {(Change.added, 'path/to/file'), ...}
            if changes:
                change_list = ", ".join([f"{op.name}:{Path(f).name}" for op, f in changes])
                print(f"Watcher: Detected changes: {change_list}")
                try:
                    await callback()
                except Exception as e:
                    print(f"Watcher: Error executing callback: {e}", file=sys.stderr)

            # Check stop event again after callback, in case it took time
            if stop_event.is_set():
                print("Watcher: Stop event received after callback, exiting watch loop.")
                break

    except FileNotFoundError:
        print(f"Watcher Error: Watch path '{path}' not found.", file=sys.stderr)
    except asyncio.CancelledError:
        print("Watcher: Task cancelled.") # Expected during shutdown
    except Exception as e:
        print(f"Watcher Error: An unexpected error occurred: {e}", file=sys.stderr)
    finally:
        print(f"Watcher: Stopping watch on {path.resolve()}.")

