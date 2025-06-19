#!/usr/bin/env python3
"""
Test script for the AGiXT WebSocket conversation streaming endpoint.

This script demonstrates how to connect to the WebSocket endpoint and receive
real-time conversation updates.

Usage:
    python test_websocket.py --token YOUR_TOKEN --conversation_id CONVERSATION_ID
"""

import asyncio
import websockets
import json
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_conversation_stream(base_url: str, token: str, conversation_id: str):
    """
    Test the conversation WebSocket stream endpoint.

    Args:
        base_url: Base URL of the AGiXT server (e.g., "localhost:7437")
        token: Bearer authentication token
        conversation_id: ID of the conversation to stream
    """
    # Construct WebSocket URL
    ws_url = f"ws://{base_url}/v1/conversation/{conversation_id}/stream?authorization={token}"

    logger.info(f"Connecting to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            logger.info("✅ Successfully connected to WebSocket")

            # Listen for messages
            message_count = 0
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_count += 1

                    logger.info(f"📨 Message #{message_count}: {data['type']}")

                    if data["type"] == "connected":
                        logger.info(
                            f"🔗 Connected to conversation: {data.get('conversation_name', 'Unknown')}"
                        )

                    elif data["type"] == "initial_message":
                        msg_data = data["data"]
                        logger.info(
                            f"📜 Initial message from {msg_data['role']}: {msg_data['message'][:100]}..."
                        )

                    elif data["type"] == "message_added":
                        msg_data = data["data"]
                        logger.info(
                            f"🆕 New message from {msg_data['role']}: {msg_data['message'][:100]}..."
                        )

                    elif data["type"] == "message_updated":
                        msg_data = data["data"]
                        logger.info(
                            f"✏️ Updated message from {msg_data['role']}: {msg_data['message'][:100]}..."
                        )

                    elif data["type"] == "heartbeat":
                        logger.info(f"💓 Heartbeat: {data['timestamp']}")

                    elif data["type"] == "error":
                        logger.error(f"❌ Error: {data['message']}")
                        break

                    else:
                        logger.info(f"❓ Unknown message type: {data['type']}")

                    # Stop after receiving 50 messages to avoid infinite loop in testing
                    if message_count >= 50:
                        logger.info(
                            "🛑 Stopping after 50 messages for testing purposes"
                        )
                        break

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON message: {e}")
                except KeyError as e:
                    logger.error(f"Missing expected field in message: {e}")

    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"🔌 WebSocket connection closed: {e}")
    except websockets.exceptions.InvalidURI as e:
        logger.error(f"❌ Invalid WebSocket URI: {e}")
    except websockets.exceptions.InvalidHandshake as e:
        logger.error(f"❌ WebSocket handshake failed: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")


async def test_authentication_failure(base_url: str, conversation_id: str):
    """Test authentication failure handling."""
    ws_url = f"ws://{base_url}/v1/conversation/{conversation_id}/stream"

    logger.info("🧪 Testing authentication failure...")

    try:
        async with websockets.connect(ws_url) as websocket:
            # Should receive an error message about missing authentication
            message = await websocket.recv()
            data = json.loads(message)

            if data["type"] == "error" and "Authorization" in data["message"]:
                logger.info("✅ Authentication failure handled correctly")
            else:
                logger.error(f"❌ Unexpected response to missing auth: {data}")

    except websockets.exceptions.ConnectionClosed:
        logger.info("✅ Connection closed as expected for missing authentication")
    except Exception as e:
        logger.error(f"❌ Unexpected error during auth test: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Test AGiXT WebSocket conversation streaming"
    )
    parser.add_argument(
        "--base-url",
        default="localhost:7437",
        help="Base URL of AGiXT server (default: localhost:7437)",
    )
    parser.add_argument("--token", required=True, help="Bearer authentication token")
    parser.add_argument(
        "--conversation-id", required=True, help="ID of the conversation to stream"
    )
    parser.add_argument(
        "--test-auth-failure",
        action="store_true",
        help="Also test authentication failure handling",
    )

    args = parser.parse_args()

    # Run the tests
    async def run_tests():
        if args.test_auth_failure:
            await test_authentication_failure(args.base_url, args.conversation_id)
            await asyncio.sleep(1)  # Brief pause between tests

        await test_conversation_stream(args.base_url, args.token, args.conversation_id)

    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        logger.info("🛑 Test interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


if __name__ == "__main__":
    main()
