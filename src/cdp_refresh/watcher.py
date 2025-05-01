"""File watcher module for CDP refresh."""

import asyncio
import logging
from pathlib import Path
from typing import Callable, Set, Union

from watchfiles import awatch, Change

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watch for file changes and trigger refresh."""
    
    def __init__(
        self,
        path: Union[str, Path],
        on_change: Callable,
        ignore_patterns: Set[str] = None,
    ):
        """Initialize file watcher.
        
        Args:
            path: Directory to watch
            on_change: Callback function to call when files change
            ignore_patterns: Patterns to ignore
        """
        self.path = Path(path)
        self.on_change = on_change
        self.ignore_patterns = ignore_patterns or set()
        self.watch_task = None
        
        if not self.path.exists():
            raise ValueError(f"Path does not exist: {self.path}")
        
        if not self.path.is_dir():
            raise ValueError(f"Path is not a directory: {self.path}")
        
        logger.info(f"Watching directory: {self.path}")
        
    async def _watch_callback(self, changes: Set[tuple[Change, str]]) -> None:
        """Handle file changes.
        
        Args:
            changes: Set of changes
        """
        changed_files = [str(Path(f).relative_to(self.path)) for _, f in changes]
        logger.info(f"Files changed: {', '.join(changed_files)}")
        await self.on_change()
    
    async def start(self) -> None:
        """Start watching for file changes."""
        try:
            async for changes in awatch(self.path, watch_filter=None):
                if changes:
                    await self._watch_callback(changes)
        except Exception as e:
            logger.error(f"Error watching files: {e}")
            raise
    
    def stop(self) -> None:
        """Stop watching for file changes."""
        if self.watch_task and not self.watch_task.done():
            self.watch_task.cancel()
            logger.info("File watcher stopped")