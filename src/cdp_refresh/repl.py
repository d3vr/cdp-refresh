# src/cdp_refresh/repl.py
"""Handles the asynchronous Read-Eval-Print Loop (REPL) using prompt_toolkit."""

import asyncio
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

if TYPE_CHECKING:
    from .browser import BrowserManager


async def run_repl(browser_manager: "BrowserManager"):
    """
    Runs the asynchronous REPL loop.

    Args:
        browser_manager: An instance of BrowserManager to interact with the browser.
    """
    history = InMemoryHistory()
    session = PromptSession(history=history)
    print("\n--- CDP Refresh REPL ---")
    print("Type 'choose-tab' to select a browser tab.")
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
                break
            # TODO: Implement 'choose-tab' and other commands (Steps 16-18)
            else:
                print(f"Unknown command: {command}")
                print("Available commands: choose-tab, exit")

        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL...")
            break
        except Exception as e:
            print(f"\nAn error occurred in the REPL: {e}")
            # Decide if the REPL should continue or exit on other errors
            await asyncio.sleep(1) # Prevent fast error loops

    # Signal shutdown or perform cleanup if needed when REPL exits
    print("REPL finished.")
    # In the core logic, the exit of this REPL might trigger app shutdown.

