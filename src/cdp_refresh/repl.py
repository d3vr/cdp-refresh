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
                if shutdown_callback:
                    await shutdown_callback() # Signal shutdown
                break # Exit the loop regardless
            elif command == "choose-tab":
                if not browser_manager.is_connected:
                    print("Browser is not connected. Cannot list tabs.", file=sys.stderr)
                    continue
                pages = await browser_manager.list_pages()
                if not pages:
                    print("No open tabs found in the browser.")
                    continue

                print("\nAvailable Tabs:")
                for i, page in enumerate(pages):
                    title = await page.title()
                    print(f"  [{i}] {title} ({page.url})")

                while True:
                    try:
                        index_str = await session.prompt_async("Enter tab index to target: ")
                        if not index_str.strip(): # Allow empty input to cancel
                            print("Tab selection cancelled.")
                            break
                        index = int(index_str)
                        if browser_manager.set_target_page_by_index(index):
                            break # Successfully set
                        else:
                            # Error message printed by set_target_page_by_index
                            print(f"Please enter a number between 0 and {len(pages) - 1}.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
                    except (EOFError, KeyboardInterrupt):
                        print("\nTab selection cancelled.")
                        break
            # TODO: Implement other commands (Step 17: exit is done, Step 18: unknown is done)
            else:
                print(f"Unknown command: {command}")
                print("Available commands: choose-tab, exit")

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

