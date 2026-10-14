"""
File tools for inspecting and reading documents (text and PDF).
Trims large files to prevent context window explosion.
"""

import os
from typing import List, Optional
import pypdf

MAX_TEXT_CHARS = 4000

def list_files(directory: str = "data/invoices") -> str:
    """
    Lists all files in a given directory relative to the project root.
    """
    if not os.path.exists(directory):
        return f"Error: Directory '{directory}' does not exist."

    try:
        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        if not files:
            return f"Directory '{directory}' is empty."
        return f"Files in '{directory}':\n" + "\n".join(f"- {f}" for f in sorted(files))
    except Exception as e:
        return f"Error listing directory '{directory}': {str(e)}"


def read_file(filepath: str) -> str:
    """
    Reads the content of a text or PDF file.
    Returns trimmed text output with total character count.
    """
    if not os.path.exists(filepath):
        return f"Error: File '{filepath}' does not exist."

    _, ext = os.path.splitext(filepath.lower())

    try:
        content = ""
        if ext == ".pdf":
            reader = pypdf.PdfReader(filepath)
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                content += f"--- Page {idx + 1} ---\n{page_text}\n"
        else:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

        total_length = len(content)
        if total_length > MAX_TEXT_CHARS:
            trimmed = content[:MAX_TEXT_CHARS]
            return f"{trimmed}\n\n[TRUNCATED: Showing first {MAX_TEXT_CHARS} of {total_length} characters]"
        return content

    except Exception as e:
        return f"Error reading file '{filepath}': {str(e)}"
