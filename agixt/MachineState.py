"""
Global state for Machine Control Extension

This module provides a centralized storage for WebSocket connections
that persists across extension reloads.
"""

import sys

# Ensure this module is registered in sys.modules to prevent reimports
if "MachineState" not in sys.modules:
    sys.modules["MachineState"] = sys.modules[__name__]

# Global storage for active WebSocket connections
# Key: terminal_id (str), Value: WebSocket connection object
ACTIVE_TERMINALS = {}
