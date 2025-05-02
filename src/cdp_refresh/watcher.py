"""File watcher module for CDP refresh."""

import asyncio
import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Callable, List, Pattern, Set, Union

from watchfiles import awatch, Change

logger = logging.getLogger(__name__)


class WildMatchPattern:
    """Simple implementation for wildcard pattern matching."""

    def __init__(self, pattern: str):
        """Initialize with a wildcard pattern.

        Args:
            pattern: Wildcard pattern (e.g., "*.py", "build/")
        """
        self.raw_pattern = pattern.strip()

        # Handle empty patterns
        if not self.raw_pattern:
            self.pattern = None
            return

        # Handle directory-specific patterns
        self.directory_only = self.raw_pattern.endswith("/")
        if self.directory_only:
            pattern = self.raw_pattern[:-1]
        else:
            pattern = self.raw_pattern

        self.pattern = pattern

    def match(self, path: str) -> bool:
        """Match a path against this pattern.

        Args:
            path: Path to check

        Returns:
            True if the path matches this pattern
        """
        if not self.pattern:
            return False

        # Normalize path
        path = path.rstrip("/")

        # Get basename for simpler comparisons
        basename = os.path.basename(path)

        # Get pattern type for debugging
        pattern_type = "exact" if "*" not in self.pattern else "wildcard"
        pattern_type += (
            "_with_path" if "/" in self.pattern or "\\" in self.pattern else "_filename"
        )

        # For debugging
        from cdp_refresh.cli import DEBUG_MODE

        if DEBUG_MODE:
            logger.debug(
                f"Pattern match test: '{self.pattern}' against '{path}' (basename: '{basename}') - pattern type: {pattern_type}"
            )

        # For simple filename patterns (no path separators), match against the basename
        # This ensures patterns like "*.js" or "index.html" match files in any directory
        if (
            "/" not in self.pattern
            and "\\" not in self.pattern
            and "*" not in self.pattern
        ):
            # Exact filename match
            result = basename == self.pattern
            if DEBUG_MODE and result:
                logger.debug(
                    f"MATCHED: Exact filename match '{self.pattern}' == '{basename}'"
                )
            return result

        elif "/" not in self.pattern and "\\" not in self.pattern:
            # For wildcard patterns without path separators, match against basename
            result = fnmatch.fnmatch(basename, self.pattern)
            if DEBUG_MODE and result:
                logger.debug(
                    f"MATCHED: Wildcard filename match '{self.pattern}' matches '{basename}'"
                )
            return result

        # For patterns with path separators, match against the full path
        result = fnmatch.fnmatch(path, self.pattern)
        if DEBUG_MODE and result:
            logger.debug(
                f"MATCHED: Path pattern match '{self.pattern}' matches '{path}'"
            )
        return result


class GitIgnorePattern:
    """Simple implementation for gitignore pattern matching."""

    def __init__(self, pattern: str):
        """Initialize with a gitignore pattern.

        Args:
            pattern: Pattern from .gitignore file
        """
        self.raw_pattern = pattern

        # Remove leading and trailing whitespace
        pattern = pattern.strip()

        # Skip comments and empty lines
        if not pattern or pattern.startswith("#"):
            self.pattern = None
            return

        # Handle negated patterns (we don't support them fully, but acknowledge them)
        self.negated = pattern.startswith("!")
        if self.negated:
            pattern = pattern[1:]

        # Handle directory-specific patterns
        self.directory_only = pattern.endswith("/")
        if self.directory_only:
            pattern = pattern[:-1]

        # Process the pattern to make it compatible with Python's fnmatch
        if pattern.startswith("/"):
            # Anchored to the root, remove the leading slash
            pattern = pattern[1:]
        else:
            # Pattern can match anywhere in the path
            pattern = f"*/{pattern}" if "/" in pattern else pattern

        # Double asterisks for directory matching
        pattern = pattern.replace("**/", "**/")

        # Store the processed pattern
        self.pattern = pattern

    def match(self, path: str) -> bool:
        """Match a path against this gitignore pattern.

        Args:
            path: Path to check, relative to repo root

        Returns:
            True if the path matches this pattern
        """
        if not self.pattern:
            return False

        # Normalize path
        path = path.rstrip("/")

        # Use simpler fnmatch for pattern matching
        return fnmatch.fnmatch(path, self.pattern)


class FileWatcher:
    """Watch for file changes and trigger refresh."""

    def __init__(
        self,
        path: Union[str, Path],
        on_change: Callable,
        ignore_patterns: List[str] = None,
        use_git_ignore: bool = True,
    ):
        """Initialize file watcher.

        Args:
            path: Directory to watch
            on_change: Callback function to call when files change
            ignore_patterns: Custom patterns to ignore
            use_git_ignore: Whether to use .gitignore patterns
        """
        self.path = Path(path).resolve()
        self.on_change = on_change
        self.ignore_patterns = ignore_patterns or []
        self.use_git_ignore = use_git_ignore
        self.watch_task = None

        if not self.path.exists():
            raise ValueError(f"Path does not exist: {self.path}")

        if not self.path.is_dir():
            raise ValueError(f"Path is not a directory: {self.path}")

        # Create ignore filter for watchfiles
        self._create_watch_filter()

        if self.use_git_ignore:
            gitignore_status = "enabled" if self.use_git_ignore else "disabled"
            logger.debug(
                f"Watching directory: {self.path} (gitignore: {gitignore_status})"
            )

        if self.ignore_patterns:
            logger.debug(f"Custom ignore patterns: {', '.join(self.ignore_patterns)}")

    def _create_watch_filter(self):
        """Create a filter function for watchfiles."""
        # For debugging
        from cdp_refresh.cli import DEBUG_MODE

        # Create pattern matchers for custom ignore patterns
        self.custom_matchers = []

        if DEBUG_MODE and self.ignore_patterns:
            logger.debug(f"Setting up ignore patterns: {self.ignore_patterns}")

        for pattern in self.ignore_patterns:
            if DEBUG_MODE:
                logger.debug(f"Adding custom ignore pattern: '{pattern}'")
            self.custom_matchers.append(WildMatchPattern(pattern))

        # Always ignore .git directory
        if DEBUG_MODE:
            logger.debug("Adding built-in .git ignore patterns")
        self.custom_matchers.append(WildMatchPattern(".git"))
        self.custom_matchers.append(WildMatchPattern(".git/*"))

        # Find .gitignore if enabled
        self.git_matchers = []
        if self.use_git_ignore:
            gitignore_path = self.path / ".gitignore"
            if gitignore_path.exists():
                if DEBUG_MODE:
                    logger.debug(f"Loading .gitignore from {gitignore_path}")
                with open(gitignore_path, "r") as f:
                    gitignore_content = f.read()

                # Parse .gitignore patterns
                for line in gitignore_content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if DEBUG_MODE:
                            logger.debug(f"Adding gitignore pattern: '{line}'")
                        self.git_matchers.append(GitIgnorePattern(line))

    async def _watch_callback(self, changes: Set) -> None:
        """Handle file changes.

        Args:
            changes: Set of changes
        """
        try:
            # For debugging
            from cdp_refresh.cli import DEBUG_MODE

            # Extract paths from changes, handling different change formats
            changed_files = []
            for change_item in changes:
                if isinstance(change_item, tuple) and len(change_item) == 2:
                    # Tuple format (Change enum, path string)
                    change_type, path = change_item
                    if DEBUG_MODE:
                        logger.debug(f"Change detected: {change_type} - {path}")
                    if isinstance(path, str):
                        rel_path = str(Path(path).relative_to(self.path))
                        # Skip .git directory changes that made it through the filter
                        if rel_path.startswith(".git/"):
                            if DEBUG_MODE:
                                logger.debug(f"Skipping .git file change: {rel_path}")
                            continue

                        # Check if this file should be ignored based on patterns
                        should_ignore = False
                        for matcher in self.custom_matchers:
                            if matcher.match(rel_path):
                                if DEBUG_MODE:
                                    logger.debug(
                                        f"Change ignored due to pattern '{matcher.raw_pattern}': {rel_path}"
                                    )
                                should_ignore = True
                                break

                        if not should_ignore:
                            changed_files.append(rel_path)
                            if DEBUG_MODE:
                                logger.debug(f"Adding changed file: {rel_path}")
                elif isinstance(change_item, str):
                    # String format (just the path)
                    if DEBUG_MODE:
                        logger.debug(f"String format change detected: {change_item}")
                    rel_path = str(Path(change_item).relative_to(self.path))
                    # Skip .git directory changes that made it through the filter
                    if rel_path.startswith(".git/"):
                        if DEBUG_MODE:
                            logger.debug(f"Skipping .git file change: {rel_path}")
                        continue

                    # Check if this file should be ignored based on patterns
                    should_ignore = False
                    for matcher in self.custom_matchers:
                        if matcher.match(rel_path):
                            if DEBUG_MODE:
                                logger.debug(
                                    f"Change ignored due to pattern '{matcher.raw_pattern}': {rel_path}"
                                )
                            should_ignore = True
                            break

                    if not should_ignore:
                        changed_files.append(rel_path)
                        if DEBUG_MODE:
                            logger.debug(f"Adding changed file: {rel_path}")

            if changed_files:
                logger.debug(f"Files changed: {', '.join(changed_files)}")

                # Use a small delay to debounce multiple rapid changes
                await asyncio.sleep(0.2)  # Wait for additional changes
                # Pass changed files to the callback
                await self.on_change(changed_files)
        except Exception as e:
            # Log any errors but don't crash
            logger.error(f"Error processing file changes: {e}")
        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            logger.debug("File watch callback task was cancelled")
            raise

    def _watch_filter(self, path, dirs):
        """Filter function for watchfiles.

        Args:
            path: File path
            dirs: Whether the path is a directory

        Returns:
            True if the path should be watched, False otherwise
        """
        # For debugging
        from cdp_refresh.cli import DEBUG_MODE

        # Convert path to string if it's not already
        if not isinstance(path, str):
            try:
                path = str(path)
            except Exception:
                # If we can't convert to string, include it
                return True

        # Get relative path
        try:
            rel_path = os.path.relpath(path, str(self.path))
        except ValueError:
            # If paths are on different drives, include it
            return True

        if DEBUG_MODE:
            logger.debug(
                f"Filter checking path: '{path}' (relative: '{rel_path}', is_dir: {dirs})"
            )

        # Explicitly ignore .git directory and its contents
        if (
            rel_path == ".git"
            or rel_path.startswith(".git/")
            or rel_path.startswith(".git\\")
        ):
            if DEBUG_MODE:
                logger.debug(f"IGNORED: '{rel_path}' is in .git directory")
            return False

        # Apply custom matchers
        for matcher in self.custom_matchers:
            try:
                if matcher.match(rel_path):
                    if DEBUG_MODE:
                        logger.debug(
                            f"IGNORED: '{rel_path}' matched custom pattern '{matcher.raw_pattern}'"
                        )
                    return False
            except Exception as e:
                if DEBUG_MODE:
                    logger.warning(f"Error in custom matcher for '{rel_path}': {e}")
                # If matching fails, continue
                pass

        # Apply git matchers if enabled
        if self.use_git_ignore:
            for matcher in self.git_matchers:
                try:
                    if matcher.match(rel_path):
                        if DEBUG_MODE:
                            logger.debug(
                                f"IGNORED: '{rel_path}' matched gitignore pattern '{matcher.raw_pattern}'"
                            )
                        return False
                except Exception as e:
                    if DEBUG_MODE:
                        logger.warning(
                            f"Error in gitignore matcher for '{rel_path}': {e}"
                        )
                    # If matching fails, continue
                    pass

        # Include everything else
        if DEBUG_MODE:
            logger.debug(f"WATCHING: '{rel_path}' - no ignore patterns matched")
        return True

    async def start(self) -> None:
        """Start watching for file changes."""
        try:
            # Keep track of any background tasks we create
            pending_tasks = set()

            # Create a watch_filter only if we have patterns to match
            watch_filter = None
            if self.custom_matchers or self.git_matchers:
                watch_filter = self._watch_filter

            # Start watching with proper error handling
            async for changes in awatch(self.path, watch_filter=watch_filter):
                if changes:
                    # Clean up completed tasks
                    pending_tasks = {t for t in pending_tasks if not t.done()}

                    # Create a new task for handling the callback, don't block awatch
                    callback_task = asyncio.create_task(self._watch_callback(changes))
                    pending_tasks.add(callback_task)

        except asyncio.CancelledError:
            logger.debug("File watcher task was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error watching files: {e}")
            raise

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self.watch_task and not self.watch_task.done():
            self.watch_task.cancel()
            logger.debug("File watcher stopped")
