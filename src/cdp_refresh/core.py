# src/cdp_refresh/core.py
"""Core application logic orchestrating browser, watcher, and REPL."""

"""Core application logic orchestrating browser, watcher, and REPL."""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Set

import aiohttp # Added import
# Use prompt_toolkit only for initial selection if needed, REPL handles its own
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from .browser import BrowserManager
from .repl import run_repl
from .watcher import watch_directory


class App:
    """Orchestrates the CDP Refresh tool components."""

    def __init__(self, watch_path: str, cdp_port: int):
        """Initializes the App orchestrator."""
        try:
            # Resolve and validate watch path immediately
            self.watch_path = Path(watch_path).resolve(strict=True)
            if not self.watch_path.is_dir():
                print(f"Error: Watch path '{watch_path}' is not a directory.", file=sys.stderr)
                sys.exit(1) # Exit early if path is invalid
        except FileNotFoundError:
            print(f"Error: Watch path '{watch_path}' not found.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error resolving watch path '{watch_path}': {e}", file=sys.stderr)
            sys.exit(1)

        self.cdp_port = cdp_port
        # BrowserManager will be initialized later in run() after fetching the target URL
        self.browser_manager: Optional[BrowserManager] = None
        self._shutdown_event = asyncio.Event() # Used to signal shutdown across tasks
        self._tasks: Set[asyncio.Task] = set() # Keep track of running tasks

    async def _get_page_targets(self) -> List[dict]:
        """Fetches available page targets from the browser's JSON endpoint."""
        json_url = f"http://127.0.0.1:{self.cdp_port}/json/list" # Use /json/list explicitly
        print(f"Fetching CDP page targets from: {json_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, timeout=10) as response:
                    response.raise_for_status() # Raise exception for bad status codes
                    targets = await response.json()

                    # Filter for page targets with necessary info
                    page_targets = [
                        t for t in targets
                        if t.get("type") == "page" and "webSocketDebuggerUrl" in t and "title" in t and "url" in t
                    ]

                    if not page_targets:
                        print("Error: No suitable page targets found.", file=sys.stderr)
                        print("Ensure the browser has open tabs and is accessible.", file=sys.stderr)
                        # print(f"Available targets: {targets}", file=sys.stderr) # For debugging
                        return []

                    print(f"Found {len(page_targets)} potential page targets.")
                    return page_targets

        except aiohttp.ClientConnectorError as e:
            print(f"Error connecting to {json_url}: {e}", file=sys.stderr)
            print("Is the browser running with the correct remote debugging port?", file=sys.stderr)
            return []
        except aiohttp.ClientResponseError as e:
             print(f"Error fetching CDP targets from {json_url}: HTTP {e.status} {e.message}", file=sys.stderr)
             return []
        except asyncio.TimeoutError:
             print(f"Timeout connecting to {json_url}", file=sys.stderr)
             return []
        except Exception as e:
            print(f"An unexpected error occurred while fetching page targets: {e}", file=sys.stderr)
            return []

    async def _initial_tab_selection(self, page_targets: List[dict]) -> Optional[str]:
        """
        Prompts the user to select a target page from the list fetched via HTTP.

        Args:
            page_targets: A list of page target dictionaries from the /json/list endpoint.

        Returns:
            The webSocketDebuggerUrl of the selected page, or None if cancelled/error.
        """
        if not page_targets:
            print("No open tabs found to select from.", file=sys.stderr)
            return None

        print("\nAvailable Tabs for Initial Selection:")
        for i, target in enumerate(page_targets):
            # Use information directly from the JSON target data
            title = target.get('title', 'N/A')
            url = target.get('url', 'N/A')
            print(f"  [{i}] {title} ({url})")

        session = PromptSession(history=InMemoryHistory())
        while not self._shutdown_event.is_set(): # Allow shutdown during selection
            try:
                index_str = await session.prompt_async("Enter index of tab to target (or Ctrl+C/D to exit): ")
                if not index_str.strip():
                    continue
                index = int(index_str)
                if 0 <= index < len(page_targets):
                    selected_target = page_targets[index]
                    target_url = selected_target.get("webSocketDebuggerUrl")
                    if target_url:
                        print("-" * 20) # Separator after selection
                        print(f"Selected target: {selected_target.get('title', 'N/A')}")
                        return target_url
                    else:
                        # Should not happen if filtering in _get_page_targets worked
                        print(f"Error: Selected target at index {index} missing webSocketDebuggerUrl.", file=sys.stderr)
                        return None
                else:
                    print(f"Invalid index. Please enter a number between 0 and {len(page_targets) - 1}.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (EOFError, KeyboardInterrupt):
                print("\nInitial tab selection cancelled by user.")
                return None # User cancelled selection
            except Exception as e:
                 print(f"\nAn error occurred during tab selection: {e}", file=sys.stderr)
                 await asyncio.sleep(0.1) # Avoid tight loop on unexpected errors

        return None # Shutdown was triggered during selection

    async def _reload_callback(self):
        """Callback passed to the watcher to trigger page reload."""
        # Now BrowserManager handles the single connected page directly
        if self.browser_manager and self.browser_manager.is_connected:
            await self.browser_manager.reload_target_page()
        elif self.browser_manager and not self.browser_manager.is_connected:
                 print("Watcher Callback: Browser disconnected, cannot reload.", file=sys.stderr)
                 return
            await self.browser_manager.reload_target_page()
        elif self.browser_manager and not self.browser_manager.target_page:
             # This might happen if the target tab was closed and not re-selected
             print("Watcher Callback: File change detected, but no target tab is selected.", file=sys.stderr)
        # else: browser_manager might not be initialized (shouldn't happen here)

    async def run(self):
        """Runs the main application logic: connect, select tab, start tasks."""
        print(f"Starting CDP Refresh:")
        print(f"  Watching: '{self.watch_path}'")
        print(f"  Using CDP port: {self.cdp_port}")
        print("-" * 20)

        # 1. Get available page targets via HTTP
        page_targets = await self._get_page_targets()
        if not page_targets:
             print("Could not find any suitable page targets. Exiting.", file=sys.stderr)
             return # Exit if no targets found

        # 2. Prompt user to select a target page
        selected_target_url = await self._initial_tab_selection(page_targets)
        if not selected_target_url:
            print("No target tab selected. Exiting.")
            # No need to call shutdown() here as nothing is connected yet
            return # Exit if no selection made

        # 3. Initialize and Connect BrowserManager to the selected page URL
        self.browser_manager = BrowserManager(selected_target_url, shutdown_callback=self.shutdown)
        if not await self.browser_manager.connect():
            # Error message printed by connect()
            return # Exit if connection fails

        # If we reach here, connection to the specific page is successful.
        # We might not have the title readily available here anymore without extra calls.
        print(f"\nSuccessfully connected to target page.")
        print(f"Watching directory '{self.watch_path}' for changes...")
        print("Starting REPL. Type 'exit' to quit.") # Removed 'choose-tab'
        print("-" * 20)


        # 4. Define and Start Background Tasks
        try:
            watcher_task = asyncio.create_task(
                watch_directory(self.watch_path, self._reload_callback, self._shutdown_event)
            )
            self._tasks.add(watcher_task)
            watcher_task.add_done_callback(self._tasks.discard) # Auto-remove when done

            repl_task = asyncio.create_task(
                run_repl(self.browser_manager, shutdown_callback=self.shutdown)
            )
            self._tasks.add(repl_task)
            repl_task.add_done_callback(self._tasks.discard) # Auto-remove when done

            # 4. Wait for shutdown signal
            # This will block until shutdown() is called (by REPL, disconnect, signal)
            await self._shutdown_event.wait()

        except Exception as e:
            print(f"\nError during task setup or main wait loop: {e}", file=sys.stderr)
            await self.shutdown() # Trigger shutdown on unexpected error
        finally:
            # This block ensures cleanup happens even if _shutdown_event.wait()
            # is interrupted unexpectedly (though shutdown() should handle it).
            print("Main loop finished or interrupted. Ensuring cleanup...")
            if not self._shutdown_event.is_set():
                 # If shutdown wasn't triggered normally, trigger it now.
                 await self.shutdown()
            # Wait briefly for tasks to finish cancelling if shutdown was just called
            await asyncio.sleep(0.1)

        print("CDP Refresh finished.")


    async def shutdown(self):
        """Initiates graceful shutdown by setting the event and cleaning up tasks."""
        if self._shutdown_event.is_set():
            return # Shutdown already in progress

        print("\nInitiating shutdown...")
        self._shutdown_event.set() # Signal all waiting components (watcher, main loop)

        await self._cleanup_tasks()

        # Disconnect browser (might already be disconnected if that triggered shutdown)
        if self.browser_manager:
            await self.browser_manager.disconnect()

    async def _cleanup_tasks(self):
        """Cancel all tracked asyncio tasks."""
        if not self._tasks:
            return

        print("Cancelling background tasks...")
        # Create a copy as tasks remove themselves from the set on completion/cancellation
        tasks_to_cancel = list(self._tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish cancellation
        # Use a timeout to prevent hanging indefinitely if a task ignores cancellation
        try:
            await asyncio.wait(tasks_to_cancel, timeout=5.0)
        except asyncio.TimeoutError:
            print("Warning: Timeout waiting for tasks to cancel.", file=sys.stderr)

        # Explicitly gather results to potentially see cancellation errors (optional)
        # await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        self._tasks.clear()
        print("Background tasks cancelled.")


async def run_app(watch_path: str, cdp_port: int): # Changed cdp_endpoint to cdp_port
    """Sets up and runs the application, handling top-level exceptions."""
    app = None # Ensure app is defined for finally block
    try:
        app = App(watch_path, cdp_port) # Changed cdp_endpoint to cdp_port
        await app.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nApplication interrupted.")
        # Shutdown should be triggered internally by signal handlers or task cancellation
    except SystemExit:
         # Raised by sys.exit(1) in __init__ on path validation failure.
         # No further action needed here, error message already printed.
         pass
    except Exception as e:
        print(f"\nAn unexpected critical error occurred: {e}", file=sys.stderr)
        # Optionally add more detailed logging here, e.g., traceback
        # import traceback
        # traceback.print_exc()
    finally:
        if app and not app._shutdown_event.is_set():
             print("Ensuring final shutdown...")
             await app.shutdown()

