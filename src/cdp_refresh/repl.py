# src/cdp_refresh/repl.py
"""Handles the asynchronous Read-Eval-Print Loop (REPL) using prompt_toolkit."""

import asyncio
import sys # Added sys
from typing import TYPE_CHECKING, Optional, Callable, Awaitable # Added Optional, Callable, Awaitable

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

if TYPE_CHECKING:
    from .browser import BrowserManager

# Type hint for an async callable with no arguments
AsyncVoidCallback = Callable[[], Awaitable[None]]


async def run_repl(browser_manager: "BrowserManager", shutdown_callback: Optional[AsyncVoidCallback] = None):
    """
    Runs the asynchronous REPL loop.

    Args:
        browser_manager: An instance of BrowserManager to interact with the browser.
        shutdown_callback: An async function to call when the REPL requests shutdown.
    """
    history = InMemoryHistory()
    session = PromptSession(history=history)
    print("\n--- CDP Refresh REPL ---")
    # print("Type 'choose-tab' to select a browser tab.") # Removed choose-tab
    print("Type 'exit' to quit.")
    print("------------------------")

    while True:
        try:
            # Use run_in_executor to avoid blocking the event loop if prompt_async does
            # This might not be strictly necessary depending on prompt_toolkit's internals,
            # but it's safer for ensuring responsiveness.
            command = await session.prompt_async("> ")
            command = command.strip().lower()

            if not command:
                continue
            elif command == "exit":
                print("Exiting REPL...")
                if shutdown_callback:
                    await shutdown_callback() # Signal shutdown
                break # Exit the loop regardless
            # Removed 'choose-tab' command block
            else:
                print(f"Unknown command: '{command}'")
                print("Available commands: exit")

        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL (Ctrl+D / Ctrl+C)...")
            if shutdown_callback:
                await shutdown_callback() # Signal shutdown
            break # Exit the loop regardless
        except Exception as e:
            print(f"\nAn error occurred in the REPL: {e}", file=sys.stderr)
            # Decide if the REPL should continue or exit on other errors
            await asyncio.sleep(0.1) # Prevent fast error loops

    # This part is reached only if the loop breaks without calling shutdown_callback
    # (e.g., if shutdown was initiated elsewhere)
    print("REPL finished.")

