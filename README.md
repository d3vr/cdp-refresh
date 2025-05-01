# CDP Refresh Tool

A simple Python tool that connects to a running Chrome/Chromium instance via the Chrome DevTools Protocol (CDP). It watches a specified local directory for file changes and automatically reloads a selected browser tab.

Useful for web development workflows where you want instant browser refresh upon saving file changes, without needing browser extensions or complex build tools.

## Prerequisites

1.  **Python:** Version 3.11 or higher.
2.  **uv:** The `uv` package manager. Install from [Astral](https://github.com/astral-sh/uv).
3.  **Running Chrome/Chromium with Remote Debugging:** You **must** launch your browser with the remote debugging port enabled _before_ running this tool. The method varies by OS:
    - **Linux:**
      ```bash
      google-chrome --remote-debugging-port=9222
      # or
      chromium-browser --remote-debugging-port=9222
      ```
    - **macOS:**
      ```bash
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
      ```
    - **Windows:**
      ```bash
      "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
      # Adjust the path if Chrome is installed elsewhere
      ```
    - You can choose a different port, but you'll need to pass it to the tool using the `--cdp-port` option. The default is `9222`.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd cdp-refresh
    ```
2.  **Create and activate a virtual environment using `uv`:**
    ```bash
    uv venv
    source .venv/bin/activate # Linux/macOS
    # .venv\Scripts\activate # Windows (cmd)
    # .venv\Scripts\Activate.ps1 # Windows (PowerShell)
    ```
3.  **Install the package and its dependencies:**
    ```bash
    uv pip install -e .
    ```

## Usage (Planned)
