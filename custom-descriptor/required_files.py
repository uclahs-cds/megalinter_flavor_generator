"""Check that all of the required files are present."""

import sys
from pathlib import Path

# Define required files
REQUIRED_FILES = [
    "README.md",
    ".gitignore",
]


def missing_files() -> bool:
    """Check that all required files are present."""
    any_missing_files = False

    for filename in REQUIRED_FILES:
        if not Path(filename).is_file():
            print(f"Missing required file: {filename}")
            any_missing_files = True

    return any_missing_files


if __name__ == "__main__":
    sys.exit(1 if missing_files() else 0)
