"""Core functionality for CDP Refresh."""

import asyncio
import json
import logging
from typing import Dict, List, Optional

import httpx
import websockets.client as websockets
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TabInfo(BaseModel):
    """Information about a Chrome tab."""

    id: str
    title: str
    type: str
    url: str
    websocket_url: str


class CDPClient:
    """Chrome DevTools Protocol client."""

    def __init__(self, host: str = "localhost", port: int = 9222):
        """Initialize CDP client.

        Args:
            host: Chrome host
            port: Chrome debugging port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.message_id = 0
        self.current_tab: Optional[TabInfo] = None  # Track current tab

    async def get_tabs(self) -> List[TabInfo]:
        """Get list of available Chrome tabs.

        Returns:
            List of tab information

        Raises:
            Exception: If unable to connect to Chrome
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/json/list")
                response.raise_for_status()

                # Get raw text for debugging
                raw_response = response.text

                # Try to check if DEBUG_MODE is defined in the cli module
                debug_mode = False
                try:
                    from cdp_refresh.cli import DEBUG_MODE

                    debug_mode = DEBUG_MODE
                except (ImportError, AttributeError):
                    pass

                # Print raw response in debug mode
                if debug_mode:
                    logger.debug(f"Raw CDP response: {raw_response}")

                try:
                    # Simple JSON parsing with no fancy fixes
                    tabs_data = response.json()
                    if debug_mode:
                        logger.debug("Successfully parsed JSON response")
                except Exception as e:
                    if debug_mode:
                        logger.error(f"JSON parsing error: {e}")
                        logger.error(f"Response content: {raw_response}")
                    raise

                return [
                    TabInfo(
                        id=tab["id"],
                        title=tab["title"],
                        type=tab["type"],
                        url=tab["url"],
                        websocket_url=tab["webSocketDebuggerUrl"],
                    )
                    for tab in tabs_data
                    if tab.get("type") == "page" and "webSocketDebuggerUrl" in tab
                ]
        except (httpx.RequestError, KeyError) as e:
            logger.error(f"Error getting Chrome tabs: {e}")
            raise Exception(
                f"Unable to connect to Chrome at {self.base_url}. "
                f"Make sure Chrome is running with remote debugging enabled."
            ) from e

    async def connect(self, websocket_url: str, tab: Optional[TabInfo] = None) -> None:
        """Connect to a Chrome tab via WebSocket.

        Args:
            websocket_url: WebSocket URL for the tab
            tab: Tab information (optional)

        Raises:
            Exception: If connection fails
        """
        try:
            self.ws_connection = await websockets.connect(websocket_url)
            logger.debug(f"Connected to Chrome tab via WebSocket: {websocket_url}")

            # Store the current tab info if provided
            if tab:
                self.current_tab = tab
            # Otherwise try to find the tab from websocket_url
            elif (
                not self.current_tab or self.current_tab.websocket_url != websocket_url
            ):
                try:
                    tabs = await self.get_tabs()
                    for t in tabs:
                        if t.websocket_url == websocket_url:
                            self.current_tab = t
                            break
                except Exception:
                    # If we can't get the tab info, that's fine
                    pass

        except Exception as e:
            logger.error(f"Failed to connect to Chrome tab: {e}")
            raise Exception(
                f"Unable to connect to Chrome tab via WebSocket: {e}"
            ) from e

    async def disconnect(self) -> None:
        """Disconnect from the Chrome tab with timeout to prevent hanging."""
        if self.ws_connection and not self.ws_connection.closed:
            try:
                # Use a timeout to prevent hanging on disconnect
                close_task = self.ws_connection.close()
                await asyncio.wait_for(close_task, timeout=0.5)
                logger.debug("Disconnected from Chrome tab")
            except asyncio.TimeoutError:
                logger.warning("Timed out while closing WebSocket connection")
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {e}")
            finally:
                # Ensure the connection is marked as closed
                self.ws_connection = None
                # Don't clear current_tab as we might reconnect to it

    async def reload_page(self) -> None:
        """Reload the current page."""
        await self._send_command("Page.reload", {"ignoreCache": True})

    async def _send_command(self, method: str, params: Dict = None) -> Dict:
        """Send a command to Chrome via CDP.

        Args:
            method: CDP method name
            params: Command parameters

        Returns:
            Command result

        Raises:
            Exception: If not connected or command fails
        """
        if not self.ws_connection or self.ws_connection.closed:
            raise Exception("Not connected to Chrome")

        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
        }

        if params:
            message["params"] = params

        try:
            await self.ws_connection.send(json.dumps(message))
            response = await self.ws_connection.recv()
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error sending command to Chrome: {e}")
            raise Exception(f"Failed to send command to Chrome: {e}") from e
