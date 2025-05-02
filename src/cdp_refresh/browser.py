"""Browser-specific utilities for CDP refresh."""

import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


def get_chrome_paths() -> List[Path]:
    """Get list of possible Chrome/Chromium paths based on the platform.
    
    Returns:
        List of potential Chrome paths
    """
    system = platform.system()
    
    if system == "Windows":
        return [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path(f"C:/Users/{Path.home().name}/AppData/Local/Google/Chrome/Application/chrome.exe"),
        ]
    elif system == "Darwin":  # macOS
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:  # Linux and others
        return [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
        ]


def find_chrome() -> Optional[Path]:
    """Find Chrome/Chromium executable on the system.
    
    Returns:
        Path to Chrome executable or None if not found
    """
    for path in get_chrome_paths():
        if path.exists():
            logger.debug(f"Found Chrome at: {path}")
            return path
    
    logger.warning("Chrome not found in standard locations")
    return None


def get_chrome_launch_command(port: int = 9222) -> str:
    """Get command to launch Chrome with remote debugging enabled.
    
    Args:
        port: Debugging port
        
    Returns:
        Command string to launch Chrome
    """
    chrome_path = find_chrome()
    if not chrome_path:
        return "Chrome not found. Please install Chrome or provide the path manually."
    
    system = platform.system()
    
    if system == "Windows":
        return f'"{chrome_path}" --remote-debugging-port={port}'
    elif system == "Darwin":  # macOS
        return f'"{chrome_path}" --remote-debugging-port={port}'
    else:  # Linux and others
        return f"{chrome_path} --remote-debugging-port={port}"