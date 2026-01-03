"""
Tests for AGiXT MCP Server
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

# Import the modules to test
import sys
sys.path.insert(0, "src")

from agixt_mcp_server.client import AGiXTClient, AGiXTClientConfig


@pytest.fixture
def client_config():
    """Create a test client configuration."""
    return AGiXTClientConfig(
        base_url="http://localhost:7437",
        api_key="test-api-key",
        default_agent="test-agent",
    )


@pytest.fixture
def client(client_config):
    """Create a test client."""
    return AGiXTClient(client_config)


class TestAGiXTClientConfig:
    """Tests for AGiXTClientConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = AGiXTClientConfig()
        assert config.base_url == "http://localhost:7437"
        assert config.api_key == ""
        assert config.default_agent == "gpt4"
        assert config.timeout == 300.0
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = AGiXTClientConfig(
            base_url="http://custom:8080",
            api_key="my-key",
            default_agent="my-agent",
            timeout=60.0,
        )
        assert config.base_url == "http://custom:8080"
        assert config.api_key == "my-key"
        assert config.default_agent == "my-agent"
        assert config.timeout == 60.0


class TestAGiXTClient:
    """Tests for AGiXTClient."""
    
    def test_headers_with_api_key(self, client):
        """Test headers include authorization when API key is set."""
        headers = client.headers
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["Content-Type"] == "application/json"
    
    def test_headers_without_api_key(self):
        """Test headers without authorization when no API key."""
        config = AGiXTClientConfig(api_key="")
        client = AGiXTClient(config)
        headers = client.headers
        assert "Authorization" not in headers
    
    def test_base_url_stripping(self):
        """Test that trailing slashes are stripped from base URL."""
        config = AGiXTClientConfig(base_url="http://localhost:7437/")
        client = AGiXTClient(config)
        assert client.base_url == "http://localhost:7437"
    
    @pytest.mark.asyncio
    async def test_list_agents(self, client):
        """Test listing agents."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"agents": [{"id": "1", "name": "test-agent"}]}
            
            result = await client.list_agents()
            
            mock_request.assert_called_once_with("GET", "/api/v1/agent")
            assert len(result) == 1
            assert result[0]["name"] == "test-agent"
    
    @pytest.mark.asyncio
    async def test_chat(self, client):
        """Test chat functionality."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "choices": [{"message": {"content": "Hello! How can I help?"}}]
            }
            
            result = await client.chat(
                agent_name="test-agent",
                user_input="Hello",
                conversation_name="test-conv",
            )
            
            assert result == "Hello! How can I help?"
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/v1/chat/completions"
    
    @pytest.mark.asyncio
    async def test_list_chains(self, client):
        """Test listing chains."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = [
                {"id": "1", "chainName": "Smart Instruct"},
                {"id": "2", "chainName": "Smart Chat"},
            ]
            
            result = await client.list_chains()
            
            mock_request.assert_called_once_with("GET", "/api/v1/chains")
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_query_memories(self, client):
        """Test querying memories."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            # First call returns agents list, second returns memories
            mock_request.side_effect = [
                {"agents": [{"id": "agent-123", "name": "test-agent"}]},
                {"memories": [{"text": "test memory", "score": 0.9}]},
            ]
            
            result = await client.query_memories(
                agent_name="test-agent",
                user_input="test query",
            )
            
            assert len(result) == 1
            assert result[0]["text"] == "test memory"
    
    @pytest.mark.asyncio
    async def test_run_chain(self, client):
        """Test running a chain."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"result": "Chain completed successfully"}
            
            result = await client.run_chain(
                chain_name="Smart Instruct",
                user_input="Create a Python function",
            )
            
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert "Smart Instruct" in call_args[0][1]
    
    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test client close."""
        # Create a mock client
        client._client = AsyncMock()
        client._client.is_closed = False
        
        await client.close()
        
        client._client.aclose.assert_called_once()


class TestToolHandlers:
    """Tests for MCP tool handlers."""
    
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, client):
        """Test that tool errors are handled gracefully."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("API Error")
            
            with pytest.raises(Exception) as exc_info:
                await client.list_agents()
            
            assert "API Error" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
