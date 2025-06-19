# WebSocket Conversation Streaming

The AGiXT WebSocket endpoint allows real-time streaming of conversation updates, enabling clients to receive immediate notifications when messages are added, updated, or deleted.

## Endpoint

```
WebSocket: /v1/conversation/{conversation_id}/stream
```

## Authentication

Authentication can be provided in two ways:

1. **Query Parameter**: `?authorization=Bearer_your_token_here`
2. **WebSocket Headers**: Include `authorization` in connection headers

## Message Types

The WebSocket will send JSON messages with different types:

### Connection Established
```json
{
    "type": "connected",
    "conversation_id": "conversation-uuid",
    "conversation_name": "conversation-name"
}
```

### Initial Messages
When you first connect, you'll receive all existing messages:
```json
{
    "type": "initial_message",
    "data": {
        "id": "message-uuid",
        "role": "user",
        "message": "Hello, how are you?",
        "timestamp": "2025-06-19T10:30:00.000Z",
        "updated_at": "2025-06-19T10:30:00.000Z",
        "updated_by": null,
        "feedback_received": false
    }
}
```

### New Message Added
```json
{
    "type": "message_added",
    "data": {
        "id": "message-uuid",
        "role": "assistant",
        "message": "I'm doing well, thank you!",
        "timestamp": "2025-06-19T10:30:05.000Z",
        "updated_at": "2025-06-19T10:30:05.000Z",
        "updated_by": null,
        "feedback_received": false
    }
}
```

### Message Updated
```json
{
    "type": "message_updated", 
    "data": {
        "id": "message-uuid",
        "role": "assistant",
        "message": "I'm doing great, thank you for asking!",
        "timestamp": "2025-06-19T10:30:05.000Z",
        "updated_at": "2025-06-19T10:30:10.000Z",
        "updated_by": "user-uuid",
        "feedback_received": false
    }
}
```

### Heartbeat
Keep-alive messages sent every 30 seconds:
```json
{
    "type": "heartbeat",
    "timestamp": "2025-06-19T10:30:30.000Z"
}
```

### Error Messages
```json
{
    "type": "error",
    "message": "Authentication failed: Invalid token"
}
```

## JavaScript Example

```javascript
// Connect to WebSocket
const token = "your_bearer_token_here";
const conversationId = "your_conversation_id";
const ws = new WebSocket(`ws://localhost:7437/v1/conversation/${conversationId}/stream?authorization=${token}`);

ws.onopen = function(event) {
    console.log('Connected to conversation stream');
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    switch(message.type) {
        case 'connected':
            console.log('Connected to conversation:', message.conversation_name);
            break;
            
        case 'initial_message':
            console.log('Initial message:', message.data);
            // Display existing message in your UI
            break;
            
        case 'message_added':
            console.log('New message:', message.data);
            // Add new message to your UI
            break;
            
        case 'message_updated':
            console.log('Message updated:', message.data);
            // Update existing message in your UI
            break;
            
        case 'heartbeat':
            console.log('Heartbeat:', message.timestamp);
            break;
            
        case 'error':
            console.error('WebSocket error:', message.message);
            break;
            
        default:
            console.log('Unknown message type:', message.type);
    }
};

ws.onclose = function(event) {
    console.log('WebSocket connection closed');
};

ws.onerror = function(error) {
    console.error('WebSocket error:', error);
};

// Close connection when done
// ws.close();
```

## Python Example

```python
import asyncio
import websockets
import json

async def stream_conversation():
    token = "your_bearer_token_here"
    conversation_id = "your_conversation_id"
    uri = f"ws://localhost:7437/v1/conversation/{conversation_id}/stream?authorization={token}"
    
    async with websockets.connect(uri) as websocket:
        print("Connected to conversation stream")
        
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "connected":
                print(f"Connected to conversation: {data['conversation_name']}")
            elif data["type"] == "initial_message":
                print(f"Initial message: {data['data']['message']}")
            elif data["type"] == "message_added":
                print(f"New message from {data['data']['role']}: {data['data']['message']}")
            elif data["type"] == "message_updated":
                print(f"Updated message: {data['data']['message']}")
            elif data["type"] == "heartbeat":
                print(f"Heartbeat: {data['timestamp']}")
            elif data["type"] == "error":
                print(f"Error: {data['message']}")
                break

# Run the client
asyncio.run(stream_conversation())
```

## Use Cases

1. **Real-time Chat Applications**: Update UI immediately when new messages arrive
2. **Collaboration Tools**: Show live conversation updates to multiple users
3. **Monitoring Systems**: Track conversation activity in real-time
4. **AI Assistant UIs**: Display agent responses as they're generated
5. **Analytics Dashboards**: Monitor conversation metrics live

## Implementation Notes

- The WebSocket polls for updates every 2 seconds
- Messages are compared by timestamp to detect updates
- Connection heartbeats are sent every 30 seconds
- Authentication is required and validated on connection
- The endpoint handles disconnections gracefully
- Error messages are sent for authentication or conversation access issues

## Rate Limiting

The WebSocket endpoint respects the same rate limiting as other API endpoints. Ensure your application handles potential disconnections and implements appropriate reconnection logic.
