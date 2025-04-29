# src/cdp_refresh/watcher.py
"""Handles file system watching using watchfiles."""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Callable, Set, Tuple

from watchfiles import Change, awatch


async def watch_directory(
    path: Path, callback: Callable[[], None]
) -> None:
    """
    Watches a directory for changes and calls an async callback.

    Args:
        path: The directory path to watch.
        callback: An asynchronous function to call when changes are detected.
    """
    print(f"Watching for file changes in: {path.resolve()}")
    try:
        async for changes in awatch(path, stop_event=asyncio.Event()): # Use dummy event for now
            # changes is a set of tuples: {(Change.added, 'path/to/file'), ...}
            # We just care that *any* change happened.
            if changes:
                change_list = ", ".join([f"{op.name}:{Path(f).name}" for op, f in changes])
                print(f"Detected changes: {change_list}")
                await callback()
    except FileNotFoundError:
        print(f"Error: Watch path '{path}' not found.", file=sys.stderr)
        # Consider raising an exception or handling it in the core logic
    except Exception as e:
        print(f"Error during file watching: {e}", file=sys.stderr)
        # Handle other potential errors from awatch

