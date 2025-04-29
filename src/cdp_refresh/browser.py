# src/cdp_refresh/browser.py
"""Handles Playwright browser connection and interactions via CDP."""

import asyncio
import sys
from typing import List, Optional

from playwright.async_api import Browser, Error, Page, Playwright, async_playwright


from typing import List, Optional, Callable, Awaitable # Added Callable, Awaitable

from playwright.async_api import Browser, Error, Page, Playwright, async_playwright

# Type hint for an async callable with no arguments
AsyncVoidCallback = Callable[[], Awaitable[None]]


class BrowserManager:
    """Manages the connection and interaction with the browser via CDP."""

    def __init__(self, cdp_url: str, shutdown_callback: Optional[AsyncVoidCallback] = None):
        """
        Initializes the BrowserManager.

        Args:
            cdp_url: The CDP endpoint URL.
            shutdown_callback: An async function to call if the browser disconnects unexpectedly.
        """
        self.cdp_url = cdp_url
        self._shutdown_callback = shutdown_callback # Added
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._target_page: Optional[Page] = None
        self._available_pages: List[Page] = []

    async def connect(self) -> bool:
        """
        Connects to the browser instance via CDP.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.cdp_url
            )
            print(f"Successfully connected to browser via CDP: {self.cdp_url}")
            # Ensure there's at least one context (usually the default one)
            if not self._browser.contexts:
                print(
                    "Error: No browser contexts found. Is the browser running correctly?",
                    file=sys.stderr,
                )
                await self.disconnect()
                return False
            # Add listener for browser disconnection
            self._browser.on("disconnected", self._handle_disconnect)
            return True
        except (Error, ConnectionRefusedError, asyncio.TimeoutError) as e:
            print(
                f"Error connecting to browser via CDP ({self.cdp_url}): {e}",
                file=sys.stderr,
            )
            print(
                "Please ensure Chrome/Chromium is running with --remote-debugging-port enabled.",
                file=sys.stderr,
            )
            await self.disconnect() # Ensure cleanup even if connection failed partially
            return False

    async def disconnect(self):
        """Disconnects from the browser and cleans up Playwright."""
        if self._browser and self._browser.is_connected():
            # Remove listener to avoid issues during explicit disconnect
            try:
                self._browser.remove_listener("disconnected", self._handle_disconnect)
            except Exception: # pylint: disable=broad-except
                 # Ignore errors if listener wasn't attached or already removed
                 pass
            await self._browser.close()
            print("Disconnected from browser.")
        if self._playwright:
            await self._playwright.stop()
            print("Playwright stopped.")
        self._browser = None
        self._playwright = None
        self._target_page = None
        self._available_pages = []

    def _handle_disconnect(self):
        """Callback function for when the browser disconnects unexpectedly."""
        print("\nBrowser disconnected unexpectedly.", file=sys.stderr)
        # We can't use async methods directly in the sync handler from playwright's event
        # Signal the main application loop or user about the disconnection if needed.
        # For now, just print. The next reload attempt will likely fail.
        self._browser = None
        self._playwright = None # Assume playwright instance is no longer valid
        self._target_page = None
        self._available_pages = []
        # Trigger application shutdown if a callback is provided
        # Schedule the callback to run in the event loop
        if self._shutdown_callback:
            print("Scheduling application shutdown due to browser disconnect.")
            asyncio.create_task(self._shutdown_callback())

    async def list_pages(self) -> List[Page]:
        """
        Retrieves a list of currently open pages (tabs) in the first browser context.

        Returns:
            List[Page]: A list of Playwright Page objects. Returns empty list on error.
        """
        if not self._browser or not self._browser.is_connected():
            print("Error: Not connected to the browser.", file=sys.stderr)
            return []
        try:
            # Assuming we only care about the first context (usually the default one)
            # If multiple browser windows/profiles are open via CDP, this might need adjustment
            if not self._browser.contexts:
                 print("Error: No browser contexts available.", file=sys.stderr)
                 return []
            context = self._browser.contexts[0]
            self._available_pages = context.pages
            return self._available_pages
        except Error as e:
            print(f"Error retrieving pages: {e}", file=sys.stderr)
            return []

    def set_target_page(self, page: Page):
        """Sets the target page for reloading."""
        if page in self._available_pages:
            self._target_page = page
            print(f"Target tab set to: '{page.title()}' ({page.url})")
        else:
            print("Error: Selected page is not valid or available.", file=sys.stderr)

    def set_target_page_by_index(self, index: int) -> bool:
        """Sets the target page by its index in the last fetched list."""
        if 0 <= index < len(self._available_pages):
            self.set_target_page(self._available_pages[index])
            return True
        else:
            print(f"Error: Invalid index {index}.", file=sys.stderr)
            return False

    async def reload_target_page(self):
        """Reloads the currently selected target page."""
        if not self._target_page:
            print("Warning: No target tab selected for reload.", file=sys.stderr)
            return

        if not self._browser or not self._browser.is_connected():
             print("Error: Cannot reload, browser is disconnected.", file=sys.stderr)
             # Attempt to clear the target page if it's no longer valid
             if self._target_page.is_closed():
                 self._target_page = None
             return

        if self._target_page.is_closed():
            print(
                f"Error: Target tab '{self._target_page.url}' is closed. Please choose a new tab.",
                file=sys.stderr,
            )
            self._target_page = None # Clear the closed target page
            # TODO: Signal REPL or core to re-prompt for tab selection?
            return

        try:
            print(f"Reloading target tab: '{await self._target_page.title()}'...")
            await self._target_page.reload(wait_until="domcontentloaded")
            print("Reload complete.")
        except Error as e:
            print(f"Error reloading page: {e}", file=sys.stderr)
            # Check if the page closed during the reload attempt
            if self._target_page.is_closed():
                 print("Target tab closed during reload.", file=sys.stderr)
                 self._target_page = None

    @property
    def target_page(self) -> Optional[Page]:
        """Returns the currently selected target page."""
        return self._target_page

    @property
    def is_connected(self) -> bool:
        """Checks if the browser is connected."""
        return self._browser is not None and self._browser.is_connected()

