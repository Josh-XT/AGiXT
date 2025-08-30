# Stop Conversation Feature Implementation

## Overview

This document describes the implementation of a stop conversation feature that allows users to cancel active AI processes/conversations.

## Backend Implementation

### New Components

1. **WorkerRegistry** (`agixt/WorkerRegistry.py`)
   - Tracks active conversations and their async tasks
   - Provides methods to stop conversations by cancelling their tasks
   - Thread-safe implementation using locks

2. **Stop Endpoints** (`agixt/endpoints/Conversation.py`)
   - `POST /v1/conversation/{conversation_id}/stop` - Stop a specific conversation
   - `POST /v1/conversations/stop` - Stop all active conversations for a user
   - `GET /v1/conversations/active` - Get list of active conversations for a user

3. **Integration** (`agixt/XT.py`)
   - Modified `chat_completions` method to register/unregister conversations
   - Handles `asyncio.CancelledError` gracefully when conversations are stopped

## Frontend Requirements

### Stop Button Implementation

The frontend needs to add a stop button that appears when a conversation is active (i.e., the AI is generating a response).

#### 1. UI Components Needed

```javascript
// Example React component structure
const StopButton = ({ conversationId, onStop, isVisible }) => {
  const handleStop = async () => {
    try {
      const response = await fetch(`/v1/conversation/${conversationId}/stop`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${userToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (response.ok) {
        onStop(); // Callback to update UI state
      } else {
        console.error('Failed to stop conversation');
      }
    } catch (error) {
      console.error('Error stopping conversation:', error);
    }
  };

  if (!isVisible) return null;

  return (
    <button 
      onClick={handleStop}
      className="stop-button"
      title="Stop AI Response"
    >
      🛑 Stop
    </button>
  );
};
```

#### 2. State Management

The frontend should track:
- Whether a conversation is currently active (AI is responding)
- The current conversation ID
- Loading states for the stop action

```javascript
// Example state structure
const [conversationState, setConversationState] = useState({
  isActive: false,
  conversationId: null,
  isStopping: false
});

// Show stop button when AI is responding
const showStopButton = conversationState.isActive && !conversationState.isStopping;
```

#### 3. Integration Points

**When to show the stop button:**
- User sends a message and AI starts responding
- During streaming responses
- When conversation is in "thinking" state

**When to hide the stop button:**
- AI completes response
- User successfully stops the conversation
- Error occurs

**WebSocket Integration:**
If using the WebSocket streaming endpoint (`/v1/conversation/{conversation_id}/stream`), listen for:
- `message_added` events to detect when AI starts/stops responding
- Connection status to manage stop button visibility

#### 4. Error Handling

```javascript
const handleStopError = (error) => {
  // Show user-friendly error message
  console.error('Failed to stop conversation:', error);
  
  // Reset UI state
  setConversationState(prev => ({
    ...prev,
    isStopping: false
  }));
};
```

### API Endpoints for Frontend

#### Stop Specific Conversation
```
POST /v1/conversation/{conversation_id}/stop
Headers: Authorization: Bearer {token}
Response: { "message": "Successfully stopped conversation {id}" }
```

#### Stop All User Conversations
```
POST /v1/conversations/stop
Headers: Authorization: Bearer {token}
Response: { "message": "Stopped {count} active conversation(s)" }
```

#### Get Active Conversations
```
GET /v1/conversations/active
Headers: Authorization: Bearer {token}
Response: {
  "active_conversations": {
    "conv-id-1": {
      "conversation_id": "conv-id-1",
      "user_id": "user-123",
      "agent_name": "Assistant",
      "started_at": "2025-01-15T10:30:00Z"
    }
  }
}
```

## Testing

### Manual Testing Steps

1. **Basic Stop Functionality**
   - Start a conversation with a long-running AI response
   - Click the stop button
   - Verify the AI response stops immediately
   - Check that the conversation history shows a stop message

2. **Multiple Conversations**
   - Open multiple conversation tabs/windows
   - Start AI responses in each
   - Test stopping individual conversations
   - Test stopping all conversations

3. **WebSocket Streaming**
   - Test stopping during streaming responses
   - Verify WebSocket connection handles cancellation gracefully

4. **Edge Cases**
   - Rapid start/stop button clicking
   - Stopping already completed conversations
   - Network errors during stop requests

### Automated Testing

```python
# Example test case
async def test_stop_conversation():
    # Start a conversation
    conversation_id = "test-conv-123"
    
    # Simulate long-running AI task
    task = asyncio.create_task(long_running_ai_process())
    
    # Register the conversation
    worker_registry.register_conversation(
        conversation_id=conversation_id,
        user_id="test-user",
        agent_name="test-agent",
        task=task
    )
    
    # Stop the conversation
    success = await worker_registry.stop_conversation(conversation_id)
    
    assert success == True
    assert task.cancelled() == True
```

## Security Considerations

1. **Authorization**: Users can only stop their own conversations
2. **Rate Limiting**: Consider rate limiting stop requests to prevent abuse
3. **Logging**: Log stop actions for debugging and monitoring

## Monitoring

Track these metrics:
- Number of conversations stopped per hour/day
- Average conversation duration before stopping
- Stop success/failure rates
- User engagement with stop feature

## Future Enhancements

1. **Pause/Resume**: Allow pausing and resuming conversations
2. **Stop Confirmation**: Add confirmation dialog for important conversations
3. **Bulk Operations**: Stop multiple selected conversations
4. **Auto-Stop**: Automatically stop conversations after a timeout
