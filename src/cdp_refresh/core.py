# src/cdp_refresh/core.py
"""Core application logic orchestrating browser, watcher, and REPL."""

"""Core application logic orchestrating browser, watcher, and REPL."""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Set

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

        # Construct the endpoint URL from the port
        self.cdp_port = cdp_port
        self.cdp_endpoint = f"ws://127.0.0.1:{cdp_port}"
        # Pass the constructed endpoint URL and self.shutdown callback to BrowserManager
        self.browser_manager = BrowserManager(self.cdp_endpoint, shutdown_callback=self.shutdown)
        self._shutdown_event = asyncio.Event() # Used to signal shutdown across tasks
        self._tasks: Set[asyncio.Task] = set() # Keep track of running tasks

    async def _initial_tab_selection(self) -> bool:
        """Guides the user through selecting the initial target tab."""
        if not self.browser_manager: # Should not happen if init is correct
            return False

        pages = await self.browser_manager.list_pages()
        if not pages:
            print("No open tabs found in the browser.", file=sys.stderr)
            print("Please open a tab in the target browser instance and restart.", file=sys.stderr)
            return False # Cannot proceed without tabs

        print("\nAvailable Tabs for Initial Selection:")
        for i, page in enumerate(pages):
            try:
                # Fetch title within try-except as page might close
                title = await page.title()
                print(f"  [{i}] {title} ({page.url})")
            except Exception as e:
                 print(f"  [{i}] Error retrieving title ({page.url}): {e}")

        # Use prompt_toolkit for robust input handling during selection
        session = PromptSession(history=InMemoryHistory())
        while not self._shutdown_event.is_set(): # Allow shutdown during selection
            try:
                index_str = await session.prompt_async("Enter index of tab to target (or Ctrl+C/D to exit): ")
                if not index_str.strip():
                    continue
                index = int(index_str)
                if self.browser_manager.set_target_page_by_index(index):
                    print("-" * 20) # Separator after selection
                    return True # Successfully selected
                else:
                    # Error message printed by set_target_page_by_index
                    print(f"Please enter a number between 0 and {len(pages) - 1}.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (EOFError, KeyboardInterrupt):
                print("\nInitial tab selection cancelled by user.")
                return False # User cancelled selection
            except Exception as e:
                 print(f"\nAn error occurred during tab selection: {e}", file=sys.stderr)
                 await asyncio.sleep(0.1) # Avoid tight loop on unexpected errors

        return False # Shutdown was triggered during selection

    async def _reload_callback(self):
        """Callback passed to the watcher to trigger page reload."""
        if self.browser_manager and self.browser_manager.target_page:
            # Check connection before attempting reload
            if not self.browser_manager.is_connected:
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
        print(f"  Connecting to CDP on port: {self.cdp_port} (Endpoint: {self.cdp_endpoint})")
        print("-" * 20)

        # 1. Connect to Browser
        if not await self.browser_manager.connect():
            # Error message printed by connect()
            return # Exit if connection fails

        # 2. Initial Tab Selection
        if not await self._initial_tab_selection():
            print("No initial tab selected. Exiting.")
            await self.shutdown() # Ensure cleanup even if no tab selected
            return

        # If we reach here, a tab is selected.
        target_title = await self.browser_manager.target_page.title()
        print(f"\nSuccessfully targeted tab: '{target_title}'")
        print(f"Watching directory '{self.watch_path}' for changes...")
        print("Starting REPL. Type 'choose-tab' or 'exit'.")
        print("-" * 20)


        # 3. Define and Start Background Tasks
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


async def run_app(watch_path: str, cdp_endpoint: str):
    """Sets up and runs the application, handling top-level exceptions."""
    app = None # Ensure app is defined for finally block
    try:
        app = App(watch_path, cdp_endpoint)
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

