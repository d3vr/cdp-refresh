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
        # Removed _target_page and _available_pages as we connect to one page directly

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
        # No _target_page or _available_pages to clear

    def _handle_disconnect(self):
        """Callback function for when the browser disconnects unexpectedly."""
        # This might represent the specific page closing, or the whole browser.
        print("\nConnection to target page lost (page closed or browser disconnected).", file=sys.stderr)
        # We can't use async methods directly in the sync handler from playwright's event
        # Signal the main application loop or user about the disconnection if needed.
        # For now, just print. The next reload attempt will likely fail.
        self._browser = None
        self._playwright = None # Assume playwright instance is no longer valid
        # No _target_page or _available_pages to clear
        # Trigger application shutdown if a callback is provided
        # Schedule the callback to run in the event loop
        if self._shutdown_callback:
            print("Scheduling application shutdown due to browser disconnect.")
            asyncio.create_task(self._shutdown_callback())

    async def list_pages(self) -> List[Page]:
        """
        Retrieves a list of currently open pages (tabs) in the first browser context.

        Returns:
            List[Page]: A list containing the single connected Page object, or empty list on error.
        """
        # When connected directly to a page, we can only see that page.
        if not self.is_connected:
            print("Error: Not connected.", file=sys.stderr)
            return []
        try:
            # The connected page should be the only one in the first context.
            if not self._browser.contexts:
                 print("Error: No browser contexts available.", file=sys.stderr)
                 return []
            context = self._browser.contexts[0]
            # Return the list (should contain 0 or 1 page)
            return context.pages
        except Error as e:
            print(f"Error retrieving connected page: {e}", file=sys.stderr)
            return []

    # Removed set_target_page and set_target_page_by_index as they are no longer applicable

    async def reload_target_page(self):
        """Reloads the connected page."""
        if not self.is_connected:
             print("Error: Cannot reload, not connected.", file=sys.stderr)
             return

        connected_pages = await self.list_pages()
        if not connected_pages:
             print("Error: Cannot find the connected page to reload.", file=sys.stderr)
             return

        target_page = connected_pages[0] # Get the single connected page

        if target_page.is_closed():
            print(
                f"Error: Connected page '{target_page.url}' is closed.",
                file=sys.stderr,
            )
            # Disconnect might be triggered by the disconnect handler anyway
            return

        try:
            page_title = await target_page.title() # Get title before reload potentially changes it
            print(f"Reloading connected page: '{page_title}'...")
            # Use a reasonable timeout for reload
            await target_page.reload(wait_until="domcontentloaded", timeout=30000)
            print("Reload complete.")
        except Error as e:
            print(f"Error reloading page: {e}", file=sys.stderr)
            # The disconnect handler should manage cleanup if the page/browser closed
        except asyncio.TimeoutError:
             print(f"Timeout reloading page: '{await target_page.title()}'.", file=sys.stderr)


    # Removed target_page property

    @property
    def is_connected(self) -> bool:
        """Checks if the browser is connected."""
        return self._browser is not None and self._browser.is_connected()

