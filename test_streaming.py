#!/usr/bin/env python3
"""
Test script for AGiXT streaming functionality
"""
import requests
import json
import sys
import os

# Add the agixt module to the path
sys.path.append('/home/josh/repos/common/AGiXT')

def test_streaming_api():
    """Test the streaming chat completions API"""
    
    # Configuration
    base_url = "http://localhost:7437"  # Default AGiXT URL
    api_key = "YOUR_API_KEY"  # Replace with actual API key if needed
    
    # Test payload
    payload = {
        "model": "gpt-3.5-turbo",  # Replace with an actual agent name
        "messages": [
            {"role": "user", "content": "Tell me a short story about a robot"}
        ],
        "stream": True,
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print("Testing AGiXT Streaming API...")
    print(f"Endpoint: {base_url}/v1/chat/completions")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("=" * 50)
    
    try:
        # Make the streaming request
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True
        )
        
        if response.status_code == 200:
            print("Request successful! Streaming response:")
            print("-" * 50)
            
            # Process the streaming response
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]  # Remove 'data: ' prefix
                        if data == '[DONE]':
                            print("\nStream completed!")
                            break
                        else:
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    delta = chunk['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        print(content, end='', flush=True)
                            except json.JSONDecodeError:
                                print(f"\nInvalid JSON: {data}")
            
        else:
            print(f"Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Connection failed. Make sure AGiXT is running on localhost:7437")
    except Exception as e:
        print(f"Error: {str(e)}")

def test_non_streaming_api():
    """Test the non-streaming chat completions API for comparison"""
    
    # Configuration
    base_url = "http://localhost:7437"
    api_key = "YOUR_API_KEY"
    
    # Test payload (without streaming)
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "Tell me a short story about a robot"}
        ],
        "stream": False,
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print("\n" + "=" * 50)
    print("Testing AGiXT Non-Streaming API for comparison...")
    
    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            print("Non-streaming request successful!")
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                print(f"Response: {content}")
        else:
            print(f"Non-streaming request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("Connection failed. Make sure AGiXT is running on localhost:7437")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    print("AGiXT Streaming Test Script")
    print("=" * 50)
    print("This script tests the new streaming functionality in AGiXT")
    print("Make sure AGiXT is running before executing this test")
    print()
    
    # Test streaming
    test_streaming_api()
    
    # Test non-streaming for comparison
    test_non_streaming_api()
    
    print("\n" + "=" * 50)
    print("Test completed!")
