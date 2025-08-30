# AGiXT Webhook System

## Overview

The AGiXT Webhook System provides comprehensive incoming and outgoing webhook capabilities, enabling seamless integration with external systems. The system allows AGiXT to:

- **Send notifications** to external systems when events occur (outgoing webhooks)
- **Receive and process data** from external systems (incoming webhooks)  
- **Transform and route data** to specific agents based on payload content
- **Monitor and log** all webhook activities for debugging and analytics

## Features

### Outgoing Webhooks
- **Event-driven notifications**: Send HTTP POST requests to external endpoints when specific events occur
- **28 predefined event types**: Comprehensive coverage of system events
- **Retry mechanism**: Automatic retry with exponential backoff for failed deliveries
- **Circuit breaker**: Prevents cascading failures by temporarily disabling failing endpoints
- **Rate limiting**: Configurable rate limits to prevent overwhelming external systems
- **HMAC signatures**: Secure webhook payloads with HMAC-SHA256 signatures
- **Custom headers**: Add custom HTTP headers to webhook requests
- **Event filtering**: Subscribe to specific event types per webhook

### Incoming Webhooks
- **External data ingestion**: Receive data from external systems
- **Agent routing**: Route incoming data to specific agents based on API key
- **Payload transformation**: Transform incoming data using Jinja2 templates
- **Rate limiting**: Protect against webhook abuse
- **Token-based authentication**: Secure incoming webhooks with unique tokens

## Event Types

AGiXT supports **26 different event types** that can trigger outgoing webhooks:

### Command Events

- `command.executed`: Triggered when a command is successfully executed
- `command.failed`: Triggered when a command execution fails

### Chat Events

- `chat.started`: Triggered when a chat conversation starts
- `chat.completed`: Triggered when a chat conversation completes
- `chat.message`: Triggered for each chat message

### Agent Events

- `agent.created`: Triggered when an agent is created
- `agent.updated`: Triggered when an agent is updated
- `agent.deleted`: Triggered when an agent is deleted

### Memory Events

- `memory.created`: Triggered when a memory is created
- `memory.updated`: Triggered when a memory is updated
- `memory.deleted`: Triggered when a memory is deleted

### Chain Events

- `chain.started`: Triggered when a chain execution starts
- `chain.step.completed`: Triggered when a chain step completes
- `chain.completed`: Triggered when a chain execution completes
- `chain.failed`: Triggered when a chain execution fails

### Task Events

- `task.created`: Triggered when a task is created
- `task.started`: Triggered when a task starts
- `task.completed`: Triggered when a task completes
- `task.failed`: Triggered when a task fails

### Provider Events

- `provider.changed`: Triggered when provider settings change

### Extension Events

- `extension.enabled`: Triggered when an extension is enabled
- `extension.disabled`: Triggered when an extension is disabled

### File Events

- `file.uploaded`: Triggered when a file is uploaded
- `file.processed`: Triggered when a file is processed

### Transcription Events

- `transcription.completed`: Triggered when transcription completes

### Training Events

- `training.started`: Triggered when training starts
- `training.completed`: Triggered when training completes

## API Endpoints

### Outgoing Webhooks

#### Create Outgoing Webhook
```http
POST /api/webhooks/outgoing
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "event_types": ["chat.message.received", "chat.response.sent"],
  "is_active": true,
  "description": "My webhook",
  "headers": {
    "X-Custom-Header": "value"
  },
  "secret": "webhook-secret",
  "agent_id": 1,
  "retry_count": 3,
  "retry_delay": 60
}
```

#### List Outgoing Webhooks
```http
GET /api/webhooks/outgoing
Authorization: Bearer {api_key}
```

#### Get Outgoing Webhook
```http
GET /api/webhooks/outgoing/{webhook_id}
Authorization: Bearer {api_key}
```

#### Update Outgoing Webhook
```http
PUT /api/webhooks/outgoing/{webhook_id}
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "event_types": ["agent.created", "agent.deleted"],
  "is_active": false
}
```

#### Delete Outgoing Webhook
```http
DELETE /api/webhooks/outgoing/{webhook_id}
Authorization: Bearer {api_key}
```

#### Test Outgoing Webhook
```http
POST /api/webhooks/outgoing/{webhook_id}/test
Authorization: Bearer {api_key}
```

#### Get Webhook Statistics

```http
GET /api/webhooks/{webhook_id}/statistics?webhook_type=outgoing
Authorization: Bearer {api_key}
```

#### Get Available Event Types

```http
GET /api/webhooks/event-types
Authorization: Bearer {api_key}
```

**Response:**
```json
{
  "event_types": [
    {
      "type": "command.executed",
      "description": "Triggered when a command is executed"
    },
    {
      "type": "chat.started",
      "description": "Triggered when a chat conversation starts"
    }
  ]
}
```

#### Get Outgoing Webhook

```http
GET /api/webhooks/outgoing/{webhook_id}
Authorization: Bearer {api_key}
```

### Incoming Webhooks

#### Create Incoming Webhook
```http
POST /api/webhooks/incoming
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "name": "External System Webhook",
  "agent_id": 1,
  "description": "Receives data from external system",
  "is_active": true,
  "transform_template": "{{ data | tojson }}"
}
```

Response:
```json
{
  "id": 1,
  "name": "External System Webhook",
  "token": "unique-webhook-token",
  "agent_id": 1,
  "description": "Receives data from external system",
  "is_active": true,
  "transform_template": "{{ data | tojson }}",
  "created_at": "2025-01-01T00:00:00Z"
}
```

#### List Incoming Webhooks
```http
GET /api/webhooks/incoming
Authorization: Bearer {api_key}
```

#### Update Incoming Webhook
```http
PUT /api/webhooks/incoming/{webhook_id}
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "name": "Updated Webhook Name",
  "is_active": false
}
```

#### Delete Incoming Webhook
```http
DELETE /api/webhooks/incoming/{webhook_id}
Authorization: Bearer {api_key}
```

#### Send Data to Incoming Webhook
```http
POST /webhook/{webhook_token}
Content-Type: application/json

{
  "message": "Data from external system",
  "timestamp": "2025-01-01T00:00:00Z",
  "custom_data": {
    "key": "value"
  }
}
```

### Webhook Logs

#### Get Webhook Logs

```http
GET /api/webhooks/{webhook_id}/logs?webhook_type=outgoing&limit=100&offset=0
Authorization: Bearer {api_key}
```

**Query Parameters:**
- `webhook_type`: `incoming` or `outgoing` (required)
- `limit`: Maximum number of logs to return (default: 100)
- `offset`: Number of logs to skip for pagination (default: 0)

**Response:**
```json
[
  {
    "id": "log-123",
    "webhook_type": "outgoing",
    "webhook_id": "webhook-456",
    "event_type": "chat.completed",
    "request_payload": {...},
    "request_headers": {...},
    "response_status": 200,
    "response_body": "OK",
    "error_message": null,
    "retry_count": 0,
    "processing_time_ms": 150,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

## Webhook Payload Format

### Outgoing Webhook Payload
```json
{
  "event_type": "chat.message.received",
  "timestamp": "2025-01-01T00:00:00Z",
  "webhook_id": 1,
  "user_id": 123,
  "company_id": 456,
  "agent_id": 789,
  "data": {
    "message": "User message content",
    "conversation_id": "conv-123",
    "agent_name": "MyAgent"
  }
}
```

### Webhook Headers
- `X-Webhook-Event`: Event type (e.g., "chat.message.received")
- `X-Webhook-Signature`: HMAC-SHA256 signature of the payload (if secret is configured)
- `X-Webhook-ID`: Unique webhook configuration ID
- `X-Webhook-Timestamp`: ISO 8601 timestamp
- Custom headers as configured

## Security

### HMAC Signature Verification

When a secret is configured for a webhook, AGiXT will include an HMAC-SHA256 signature in the `X-Webhook-Signature` header. To verify the signature:

```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)
```

### Rate Limiting

- **Incoming webhooks**: Limited to 100 requests per minute per webhook token
- **Outgoing webhooks**: Configurable rate limiting per webhook configuration

## Payload Transformation (Incoming Webhooks)

Use Jinja2 templates to transform incoming webhook data before processing:

```json
{
  "transform_template": "{
    \"message\": \"{{ data.text }}\",
    \"user\": \"{{ data.user.name }}\",
    \"timestamp\": \"{{ data.created_at }}\"
  }"
}
```

## Error Handling

### Retry Logic
- Failed webhook deliveries are retried with exponential backoff
- Default: 3 retries with delays of 60s, 120s, 240s
- Configurable per webhook

### Circuit Breaker
- After 5 consecutive failures, the webhook is temporarily disabled
- Cooldown period: 5 minutes
- Automatically re-enabled after cooldown

### Logging
All webhook activities are logged:
- Delivery attempts
- Success/failure status
- Response codes
- Error messages
- Retry attempts

## Testing

Use the provided test script to verify webhook functionality:

```bash
cd tests
python test_webhooks.py
```

The test script includes:
- Basic webhook CRUD operations
- Event triggering and delivery verification
- Incoming webhook testing
- Stress testing capabilities

## Example Integrations

### Slack Integration

```python
# Create a webhook for Slack notifications
webhook_config = {
    "name": "Slack Notifications",
    "target_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    "event_types": ["chat.completed", "command.failed"],
    "headers": {
        "Content-Type": "application/json"
    },
    "description": "Send notifications to Slack channel"
}
```

### GitHub Integration

```python
# Create a webhook for GitHub issue creation on failures
webhook_config = {
    "name": "GitHub Issue Creator",
    "target_url": "https://api.github.com/repos/owner/repo/issues",
    "event_types": ["command.failed", "chain.failed"],
    "headers": {
        "Authorization": "token YOUR_GITHUB_TOKEN",
        "Accept": "application/vnd.github.v3+json"
    },
    "description": "Create GitHub issues for failures"
}
```

### Discord Integration

```python
# Send completion notifications to Discord
webhook_config = {
    "name": "Discord Bot",
    "target_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN",
    "event_types": ["task.completed", "training.completed"],
    "headers": {
        "Content-Type": "application/json"
    },
    "description": "Notify Discord channel of completions"
}
```

### Custom CRM Integration (Incoming)

```python
# Incoming webhook for CRM lead processing
incoming_config = {
    "name": "CRM Lead Processor",
    "agent_id": "sales_agent",
    "description": "Process new leads from CRM system",
    "payload_transformation": {
        "message": "New lead: {{ lead_name }} from {{ company }}",
        "context": {
            "email": "{{ email }}",
            "phone": "{{ phone }}",
            "source": "CRM System",
            "priority": "{{ priority | default('medium') }}"
        }
    }
}
```

### External API Data Processing

```python
# Transform external API data for agent processing
webhook_config = {
    "name": "API Data Processor",
    "agent_id": "data_agent",
    "payload_transformation": {
        "message": "Process this data: {{ data | tojson }}",
        "metadata": {
            "source": "{{ source | default('external_api') }}",
            "timestamp": "{{ timestamp }}",
            "processed": False
        }
    }
}
```

### Monitoring and Alerting

```python
# Set up monitoring webhook for failures
webhook_config = {
    "name": "System Monitor",
    "target_url": "https://your-monitoring-system.com/webhook",
    "event_types": [
        "command.failed",
        "chain.failed", 
        "task.failed",
        "agent.updated"  # Monitor configuration changes
    ],
    "headers": {
        "X-API-Key": "your-monitoring-api-key"
    },
    "filters": {
        "severity": "high"  # Only high-severity events
    }
}
```

## Advanced Configuration

### Event Filtering

You can use filters to control which specific events trigger webhooks:

```python
# Only send webhooks for specific agents
webhook_config = {
    "name": "Agent-Specific Monitor",
    "target_url": "https://your-endpoint.com/webhook",
    "event_types": ["command.executed", "command.failed"],
    "filters": {
        "agent_name": "production_agent",
        "user_id": "specific_user"
    }
}
```

### Payload Transformation Templates

For incoming webhooks, use Jinja2 templates to transform data:

```python
# Complex transformation example
transform_template = {
    "message": "{% if action == 'create' %}New {{ object_type }}: {{ object_name }}{% else %}{{ action | title }} {{ object_type }}: {{ object_name }}{% endif %}",
    "metadata": {
        "source": "github",
        "timestamp": "{{ timestamp }}",
        "priority": "{% if object_type == 'issue' and labels contains 'urgent' %}high{% else %}normal{% endif %}",
        "assignee": "{{ assignee.login | default('unassigned') }}"
    },
    "context": {
        "repository": "{{ repository.full_name }}",
        "branch": "{{ ref | default('main') }}",
        "commit": "{{ head_commit.id | default('unknown') }}"
    }
}
```

### Rate Limiting Configuration

```python
# Configure custom rate limits
incoming_webhook_config = {
    "name": "High-Volume Webhook",
    "agent_id": "processor_agent",
    "rate_limit": 1000,  # 1000 requests per minute
    "description": "Handle high-volume external data"
}
```

### IP Whitelisting

```python
# Restrict webhook access to specific IPs
webhook_config = {
    "name": "Secure Webhook",
    "agent_id": "secure_agent", 
    "allowed_ips": [
        "192.168.1.100",
        "10.0.0.0/8",
        "203.0.113.0/24"
    ]
}
```

### Retry and Timeout Configuration

```python
# Custom retry and timeout settings
webhook_config = {
    "name": "Reliable Webhook",
    "target_url": "https://unreliable-service.com/webhook",
    "event_types": ["task.completed"],
    "retry_count": 5,        # Retry 5 times instead of default 3
    "retry_delay": 30,       # 30 seconds between retries
    "timeout": 60,           # 60 second timeout
    "headers": {
        "User-Agent": "AGiXT-Webhook/1.0"
    }
}
```

1. **Use specific event subscriptions**: Only subscribe to events you need to minimize unnecessary webhook calls
2. **Implement signature verification**: Always verify HMAC signatures in production
3. **Handle retries gracefully**: Ensure your endpoint is idempotent to handle retry attempts
4. **Monitor webhook logs**: Regularly check logs for failed deliveries
5. **Use appropriate timeouts**: Configure reasonable timeout values for your endpoints
6. **Implement rate limiting**: Protect your endpoints from being overwhelmed
7. **Use HTTPS**: Always use secure endpoints in production
8. **Transform data appropriately**: Use transformation templates to normalize incoming data
9. **Document webhook endpoints**: Maintain clear documentation of your webhook integrations
10. **Test thoroughly**: Use the provided test utilities to verify webhook behavior

## Troubleshooting

### Common Issues

1. **Webhook not receiving events**
   - Check if webhook is active
   - Verify event type subscriptions
   - Check webhook logs for errors
   - Ensure network connectivity

2. **Authentication failures**
   - Verify API key is correct
   - Check webhook token for incoming webhooks
   - Ensure proper authorization headers

3. **Signature verification failures**
   - Ensure secret matches on both sides
   - Verify signature calculation method
   - Check for encoding issues

4. **Rate limiting errors**
   - Reduce request frequency
   - Implement exponential backoff
   - Contact administrator for limit adjustments

5. **Transformation errors**
   - Validate Jinja2 template syntax
   - Ensure data structure matches template expectations
   - Check logs for transformation errors

## Performance Considerations

- **Async processing**: Webhook events are processed asynchronously to avoid blocking main operations
- **Queue management**: Events are queued and processed in order
- **Batch processing**: Multiple events can be batched for efficiency
- **Connection pooling**: HTTP connections are pooled for better performance
- **Timeout configuration**: Appropriate timeouts prevent hanging connections

## Usage Patterns and SDKs

### Using the AGiXT Python SDK

```python
import agixt

# Initialize client
client = agixt.AGiXTSDK(
    base_uri="http://localhost:7437",
    api_key="your-api-key"
)

# Create outgoing webhook
outgoing_webhook = client.create_outgoing_webhook({
    "name": "My Webhook",
    "target_url": "https://my-service.com/webhook",
    "event_types": ["chat.completed", "task.completed"],
    "secret": "webhook-secret-123"
})

# Create incoming webhook  
incoming_webhook = client.create_incoming_webhook({
    "name": "Data Processor",
    "agent_id": "processor_agent",
    "payload_transformation": {
        "message": "Process: {{ data | tojson }}",
        "priority": "{{ priority | default('normal') }}"
    }
})

# List and manage webhooks
webhooks = client.list_outgoing_webhooks()
client.update_outgoing_webhook(webhook_id, {"active": False})
client.delete_outgoing_webhook(webhook_id)
```

### Using Raw HTTP Requests

```python
import requests

headers = {
    "Authorization": "Bearer your-api-key",
    "Content-Type": "application/json"
}

# Create outgoing webhook
webhook_data = {
    "name": "API Webhook",
    "target_url": "https://api.example.com/webhooks/agixt",
    "event_types": ["command.executed"],
    "headers": {
        "X-Source": "AGiXT",
        "X-Version": "1.0"
    }
}

response = requests.post(
    "http://localhost:7437/api/webhooks/outgoing",
    json=webhook_data,
    headers=headers
)
webhook = response.json()

# Test the webhook
test_data = {"test_payload": {"message": "Hello, webhook!"}}
requests.post(
    f"http://localhost:7437/api/webhooks/test/{webhook['id']}",
    json=test_data,
    headers=headers
)
```

### Webhook Endpoint Implementation Examples

#### Python Flask Webhook Receiver

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)

@app.route('/webhook/agixt', methods=['POST'])
def handle_agixt_webhook():
    # Verify signature
    signature = request.headers.get('X-Webhook-Signature')
    if signature:
        payload = request.get_data()
        expected_sig = hmac.new(
            b'your-webhook-secret',
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return jsonify({"error": "Invalid signature"}), 401
    
    # Process webhook data
    data = request.json
    event_type = request.headers.get('X-Webhook-Event')
    
    print(f"Received {event_type} event:")
    print(f"Data: {data}")
    
    # Handle different event types
    if event_type == 'task.completed':
        handle_task_completion(data)
    elif event_type == 'command.failed':
        handle_command_failure(data)
    
    return jsonify({"status": "processed"}), 200

def handle_task_completion(data):
    # Send notification, update database, etc.
    print(f"Task completed: {data.get('data', {}).get('task_name')}")

def handle_command_failure(data):
    # Create incident, send alert, etc.
    print(f"Command failed: {data.get('data', {}).get('error_message')}")

if __name__ == '__main__':
    app.run(debug=True)
```

#### Node.js Express Webhook Receiver

```javascript
const express = require('express');
const crypto = require('crypto');
const app = express();

app.use(express.json());

app.post('/webhook/agixt', (req, res) => {
    const signature = req.headers['x-webhook-signature'];
    const eventType = req.headers['x-webhook-event'];
    
    // Verify signature
    if (signature) {
        const payload = JSON.stringify(req.body);
        const expectedSig = crypto
            .createHmac('sha256', 'your-webhook-secret')
            .update(payload, 'utf8')
            .digest('hex');
            
        if (signature !== expectedSig) {
            return res.status(401).json({ error: 'Invalid signature' });
        }
    }
    
    console.log(`Received ${eventType} event:`, req.body);
    
    // Process webhook based on event type
    switch (eventType) {
        case 'chat.completed':
            handleChatCompletion(req.body);
            break;
        case 'agent.created':
            handleAgentCreation(req.body);
            break;
        default:
            console.log('Unknown event type:', eventType);
    }
    
    res.json({ status: 'processed' });
});

function handleChatCompletion(data) {
    // Process chat completion
    console.log('Processing chat completion:', data.data);
}

function handleAgentCreation(data) {
    // Process agent creation
    console.log('New agent created:', data.data.agent_name);
}

app.listen(3000, () => {
    console.log('Webhook server running on port 3000');
});
```

## Testing and Debugging

### Testing Outgoing Webhooks

```python
# Test webhook with custom payload
import requests

headers = {"Authorization": "Bearer your-api-key"}
test_payload = {
    "test_payload": {
        "message": "Test webhook delivery",
        "timestamp": "2025-01-01T00:00:00Z",
        "custom_data": {"key": "value"}
    }
}

response = requests.post(
    f"http://localhost:7437/api/webhooks/test/{webhook_id}",
    json=test_payload,
    headers=headers
)
print(f"Test result: {response.status_code} - {response.json()}")
```

### Debugging Webhook Delivery Issues

```python
# Check webhook statistics
response = requests.get(
    f"http://localhost:7437/api/webhooks/{webhook_id}/statistics?webhook_type=outgoing",
    headers=headers
)
stats = response.json()
print(f"Total events sent: {stats['total_requests']}")
print(f"Successful deliveries: {stats['successful_requests']}")
print(f"Failed deliveries: {stats['failed_requests']}")
print(f"Average processing time: {stats['average_processing_time_ms']}ms")

# Check recent logs
response = requests.get(
    f"http://localhost:7437/api/webhooks/{webhook_id}/logs?webhook_type=outgoing&limit=10",
    headers=headers
)
logs = response.json()
for log in logs:
    if log['error_message']:
        print(f"Error: {log['error_message']} at {log['created_at']}")
```

### Webhook Testing Tools

#### Using ngrok for Local Development

```bash
# Install ngrok
npm install -g ngrok

# Expose local server
ngrok http 3000

# Use the HTTPS URL for webhooks
# https://abc123.ngrok.io/webhook/agixt
```

#### Using curl for Manual Testing

```bash
# Test incoming webhook
curl -X POST http://localhost:7437/api/webhook/your-webhook-id \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Test message",
    "data": {"key": "value"}
  }'

# Test with webhook.site
curl -X POST https://webhook.site/unique-url \
  -H "X-Webhook-Event: test.webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "test.webhook",
    "timestamp": "2025-01-01T00:00:00Z",
    "data": {"message": "Test webhook"}
  }'
```

### Common Debug Scenarios

#### Webhook Not Receiving Events

```python
# Check webhook configuration
webhook = requests.get(
    f"http://localhost:7437/api/webhooks/outgoing/{webhook_id}",
    headers=headers
).json()

print(f"Webhook active: {webhook['active']}")
print(f"Event types: {webhook['event_types']}")
print(f"Target URL: {webhook['target_url']}")
print(f"Filters: {webhook.get('filters', {})}")
```

#### Signature Verification Issues

```python
# Test signature verification
import hmac
import hashlib

def verify_signature(payload, signature, secret):
    expected_signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    print(f"Expected: {expected_signature}")
    print(f"Received: {signature}")
    return hmac.compare_digest(signature, expected_signature)

# Test with sample data
payload = '{"test": "data"}'
signature = "your_received_signature"
secret = "your_webhook_secret"

is_valid = verify_signature(payload, signature, secret)
print(f"Signature valid: {is_valid}")
```

## Best Practices

1. **Use specific event subscriptions**: Only subscribe to events you need to minimize unnecessary webhook calls
2. **Implement signature verification**: Always verify HMAC signatures in production environments
3. **Handle retries gracefully**: Ensure your webhook endpoints are idempotent to handle retry attempts safely
4. **Monitor webhook logs**: Regularly check webhook logs for failed deliveries and performance issues
5. **Use appropriate timeouts**: Configure reasonable timeout values to prevent hanging connections
6. **Implement proper error handling**: Return appropriate HTTP status codes and handle errors gracefully
7. **Use HTTPS endpoints**: Always use secure endpoints in production environments
8. **Transform data appropriately**: Use payload transformation templates to normalize incoming data
9. **Document your integrations**: Maintain clear documentation of your webhook endpoints and expected payloads
10. **Test thoroughly**: Use the built-in test functionality to verify webhook behavior before deploying
11. **Implement rate limiting**: Protect your endpoints from being overwhelmed by webhook requests
12. **Use filters effectively**: Apply event filters to reduce noise and only receive relevant events
13. **Monitor performance**: Track webhook delivery times and success rates for optimization
14. **Implement circuit breakers**: Use the built-in circuit breaker functionality to handle failing endpoints

## Database Schema

### WebhookOutgoing Table
- `id`: Primary key
- `user_id`: Foreign key to User
- `company_id`: Foreign key to Company
- `agent_id`: Optional foreign key to Agent
- `url`: Webhook endpoint URL
- `event_types`: JSON array of subscribed events
- `is_active`: Boolean flag
- `secret`: Optional HMAC secret
- `headers`: Optional custom headers (JSON)
- `description`: Optional description
- `retry_count`: Number of retry attempts
- `retry_delay`: Delay between retries (seconds)
- `created_at`: Timestamp
- `updated_at`: Timestamp

### WebhookIncoming Table
- `id`: Primary key
- `user_id`: Foreign key to User
- `company_id`: Foreign key to Company
- `agent_id`: Foreign key to Agent
- `name`: Webhook name
- `token`: Unique webhook token
- `description`: Optional description
- `is_active`: Boolean flag
- `transform_template`: Optional Jinja2 template
- `created_at`: Timestamp
- `updated_at`: Timestamp

### WebhookLog Table
- `id`: Primary key
- `webhook_id`: Foreign key to WebhookOutgoing
- `event_type`: Event type string
- `status`: Delivery status (pending/delivered/failed)
- `response_code`: HTTP response code
- `response_body`: Response body (truncated)
- `error_message`: Error details if failed
- `retry_count`: Number of retries attempted
- `created_at`: Timestamp
