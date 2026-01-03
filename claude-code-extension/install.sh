#!/bin/bash

# AGiXT MCP Server Installation Script

set -e

echo "=========================================="
echo "AGiXT MCP Server for Claude Code"
echo "=========================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "Error: Python 3.10 or higher is required"
    echo "Current version: $PYTHON_VERSION"
    exit 1
fi

echo "Python version: $PYTHON_VERSION ✓"
echo ""

# Install the package
echo "Installing AGiXT MCP Server..."
pip install -e .

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure environment variables:"
echo "   cp .env.example .env"
echo "   # Edit .env with your AGiXT settings"
echo ""
echo "2. Add to Claude Code settings:"
echo '   {
     "mcpServers": {
       "agixt": {
         "command": "agixt-mcp-server",
         "env": {
           "AGIXT_API_URL": "http://localhost:7437",
           "AGIXT_API_KEY": "your-api-key",
           "AGIXT_AGENT_NAME": "gpt4"
         }
       }
     }
   }'
echo ""
echo "3. Restart Claude Code to load the extension"
echo ""
echo "For more information, see README.md"
