#!/usr/bin/env python3
"""Check that all of templated text has been removed from the README."""

import sys
import re
from pathlib import Path


def is_readme_valid() -> bool:
    """Check if there is any templated text in the README."""
    bad_regexes = (
        re.compile(regex)
        for regex in (
            r"\bProject/Repo Title\b",
            r"\btool_name\b",
            r"\bX\.X\.X\b",
            r"Tool specific references",
            r"\bName1\b",
            r"\bdocker-tool_name\b",
            r"\btool_name\b",
            r"\[docker repo name\]",
            r"\[pipeline name\]",
            r"\[This project\]",
            r"<one line to give",
            r"link-to-issues-page",
            r"link-to-discussions",
            r"link-to-pull-requests",
        )
    )

    readme_path = Path("README.md")
    if not readme_path.is_file():
        print("No README.md file found")
        return False

    text = readme_path.read_text(encoding="utf-8")

    readme_valid = True

    for regex in bad_regexes:
        if matches := regex.findall(text):
            print(f"Found {len(matches)} instances of: {regex.pattern}")
            readme_valid = False

    return readme_valid


if __name__ == "__main__":
    sys.exit(0 if is_readme_valid() else 1)
