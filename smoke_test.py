"""Smoke test for dragon-tui — all modules."""
import sys
sys.path.insert(0, ".")

from config import load_settings
settings = load_settings()
print(f"api_key: {'***' + settings.api_key[-4:] if settings.api_key else 'NOT SET'}")

# API client (new: ChatResponse, ToolCall, chat())
from api.client import DragonClient, ChatResponse, ToolCall as APIToolCall
print("API client OK")

# Session modules
from session.manager import ConversationManager
from session.storage import SessionStorage, SessionRecord
print("Session modules OK")

# Tool system
from tools.registry import ToolRegistry, ToolCall, ToolResult
from tools.builtins import registry
print(f"Tools: {len(registry.get_schemas())} registered")
for s in registry.get_schemas():
    name = s["function"]["name"]
    print(f"  {name} (approval={'⚠' if registry.needs_approval(name) else '✓'})")

# UI widgets
from ui.markdown_message import MarkdownMessage
from ui.chat_input import ChatInput
from ui.session_screen import SessionListScreen
from ui.tool_widget import ToolCallWidget
from ui.shell_approve import ShellApprovalScreen
print("UI widgets OK")

# App
from app import ChatApp
print("ChatApp OK")

print("\n✅ All modules OK.")
