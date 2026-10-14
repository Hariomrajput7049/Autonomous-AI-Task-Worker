"""
Central tool registry for the Autonomous AI Task Worker.
Contains:
1. Tool schemas for LLM function/tool calling (OpenAI/Gemini/Anthropic compatible format).
2. Dispatch table mapping tool name -> python function.
Adding a new tool requires exactly ONE entry here.
"""

from typing import Dict, Any, List, Callable
import json

from tools.files import list_files, read_file
from tools.api import api_request
from tools.human import ask_human

# Dispatch table mapping tool names directly to callable Python functions
TOOL_DISPATCH: Dict[str, Callable] = {
    "list_files": list_files,
    "read_file": read_file,
    "api_request": api_request,
    "ask_human": ask_human,
}

# Standardized tool definitions for LLM function calling
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a project directory (default: 'data/invoices') to discover available documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to directory to list, relative to project root.",
                        "default": "data/invoices"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read text or PDF document content. Use this to read invoices, company rules, or API specifications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Relative path of file to read (e.g. 'data/invoices/invoice_acme_cloud_oct2026.txt', 'data/api_spec.md')."
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "api_request",
            "description": "Execute an HTTP request against the internal company ERP API (supports GET, POST, PATCH, DELETE).",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PATCH", "DELETE"],
                        "description": "HTTP method."
                    },
                    "path": {
                        "type": "string",
                        "description": "Endpoint path (e.g. '/auth/login', '/invoices', '/invoices/1', '/vendors', '/openapi.json')."
                    },
                    "json_body": {
                        "type": "object",
                        "description": "Optional JSON payload object for POST/PATCH requests."
                    },
                    "token": {
                        "type": "string",
                        "description": "Bearer token obtained from /auth/login (omit if calling login endpoint)."
                    }
                },
                "required": ["method", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": "Ask the human operator for clarification or required approval when policies mandate it (e.g., invoice amount > $50,000, destructive updates, or ambiguous documents).",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The exact question or approval request to present to the user."
                    }
                },
                "required": ["question"]
            }
        }
    }
]


def execute_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Safely executes a tool from the registry with the given arguments.
    Returns a string observation.
    """
    if tool_name not in TOOL_DISPATCH:
        return f"Error: Tool '{tool_name}' is not recognized in the registry."

    func = TOOL_DISPATCH[tool_name]
    try:
        # If arguments is passed as a string by accident, deserialize it
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                return f"Error: Could not parse arguments JSON: {arguments}"
                
        result = func(**arguments)
        return str(result)
    except TypeError as te:
        return f"Tool Execution Error (Argument mismatch): {str(te)}"
    except Exception as e:
        return f"Tool Execution Error ({type(e).__name__}): {str(e)}"
