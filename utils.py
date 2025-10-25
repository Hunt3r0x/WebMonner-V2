import sys
import traceback
from datetime import datetime
from pathlib import Path

# --- Constants ---
DATA_DIR = Path.cwd() / "data"

# --- Color Logging ---
class Log:
    """A simple colorized logger."""
    COLORS = {
        "HEADER": '\033[95m',
        "BLUE": '\033[94m',
        "GREEN": '\033[92m',
        "WARNING": '\033[93m',
        "ERROR": '\033[91m',
        "MUTED": '\033[90m',
        "ENDC": '\033[0m',
    }
    # Disable colors on Windows if colorama is not installed
    IS_WINDOWS = sys.platform.startswith("win")

    def _print(self, color: str, message: str):
        if self.IS_WINDOWS:
            print(message)
        else:
            print(f"{self.COLORS[color]}{message}{self.COLORS['ENDC']}")

    def header(self, message: str):
        self._print("HEADER", f"\n--- {message} ---")

    def info(self, message: str):
        self._print("BLUE", f"[i] {message}")

    def success(self, message: str):
        self._print("GREEN", f"[+] {message}")

    def warning(self, message: str):
        self._print("WARNING", f"[!] {message}")

    def error(self, message: str, exc_info: bool = False):
        self._print("ERROR", f"[x] {message}")
        if exc_info:
            traceback.print_exc()

    def muted(self, message: str):
        self._print("MUTED", f"  > {message}")

    def separator(self):
        print("─" * 80)

    def get_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

log = Log()

# --- Formatting Helpers ---
def format_filesize(size_in_bytes: int) -> str:
    """Converts bytes to a human-readable string (KB, MB)."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"

