#!/usr/bin/env python
# coding: utf-8

# # AGiXT Python SDK Tests
#
# This test suite runs all tests for both "company_admin" (role_id=2) and "user" (role_id=3)
# roles to ensure proper scope validation.
#
# ## Setup and Imports

# In[8]:


import random
import string
import time
import openai
from agixtsdk import AGiXTSDK
import requests
import os
import re
import pyotp
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

# Get the directory containing this test file for resolving relative paths
TEST_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================
# Test Context and User Management
# ============================================


@dataclass
class UserContext:
    """Stores context for a test user"""

    email: str
    role_name: str
    role_id: int
    sdk: AGiXTSDK = None
    otp_uri: str = ""
    mfa_token: str = ""
    user_id: str = ""
    company_id: str = ""
    agent_id: str = ""  # ID of agent created by this user
    agent_name: str = ""  # Name of agent created by this user


@dataclass
class TestContext:
    """Manages test context for multi-role testing"""

    base_uri: str = "http://localhost:7437"
    verbose: bool = True
    admin_user: UserContext = None
    regular_user: UserContext = None
    current_user: UserContext = None
    test_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def set_current_user(self, user: UserContext):
        """Switch the current test user context"""
        self.current_user = user
        print(f"\n{'='*60}")
        print(f"🔄 Switched to user: {user.email} (role: {user.role_name})")
        print(f"{'='*60}\n")

    def record_result(
        self,
        test_name: str,
        role: str,
        success: bool,
        error: str = None,
        expected_to_fail: bool = False,
    ):
        """Record a test result"""
        if test_name not in self.test_results:
            self.test_results[test_name] = {}
        self.test_results[test_name][role] = {
            "success": success,
            "error": error,
            "expected_to_fail": expected_to_fail,
            "passed": success if not expected_to_fail else not success,
        }

    def print_summary(self):
        """Print summary of all test results"""
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80)

        passed = 0
        failed = 0

        for test_name, roles in self.test_results.items():
            print(f"\n📋 {test_name}:")
            for role, result in roles.items():
                status = "✅ PASS" if result["passed"] else "❌ FAIL"
                expected = " (expected to fail)" if result["expected_to_fail"] else ""
                error = (
                    f" - {result['error']}"
                    if result["error"] and not result["passed"]
                    else ""
                )
                print(f"   {role}: {status}{expected}{error}")
                if result["passed"]:
                    passed += 1
                else:
                    failed += 1

        print(f"\n{'='*80}")
        print(f"Total: {passed} passed, {failed} failed")
        print(f"{'='*80}\n")

        return failed  # Return number of failures for exit code


# Define which tests should fail for the "user" role (due to scope restrictions)
# These are operations that require admin privileges
ADMIN_ONLY_TESTS = {
    "create_agent",
    "delete_agent",
    "rename_agent",
    "update_agent_settings",
    "update_agent_commands",
    "toggle_command",
    "create_chain",
    "delete_chain",
    "rename_chain",
    "add_chain_step",
    "update_chain_step",
    "move_chain_step",
    "delete_chain_step",
    "run_chain",
    "create_prompt",
    "update_prompt",
    "delete_prompt",
    "create_webhook",
    "update_webhook",
    "delete_webhook",
    "wipe_agent_memories",
    "invite_user",
}

# Initialize test context
ctx = TestContext()


def display_content(content, headers=None):
    """Display content with media handling"""
    outputs_url = f"http://localhost:7437/outputs/"
    os.makedirs("outputs", exist_ok=True)
    if headers is None and ctx.current_user:
        headers = ctx.current_user.sdk.headers
    try:
        from IPython.display import Audio, display, Image, Video
    except:
        print(content)
        return
    if "http://localhost:8091/outputs/" in content:
        if outputs_url != "http://localhost:8091/outputs/":
            content = content.replace("http://localhost:8091/outputs/", outputs_url)
    if outputs_url in content:
        urls = re.findall(f"{re.escape(outputs_url)}[^\"' ]+", content)
        urls = urls[0].split("\n\n")
        for url in urls:
            file_name = url.split("/")[-1]
            url = f"{outputs_url}{file_name}"
            data = requests.get(url, headers=headers).content
            if url.endswith(".jpg") or url.endswith(".png"):
                content = content.replace(url, "")
                display(Image(url=url))
            elif url.endswith(".mp4"):
                content = content.replace(url, "")
                display(Video(url=url, autoplay=True))
            elif url.endswith(".wav"):
                content = content.replace(url, "")
                display(Audio(url=url, autoplay=True))
    print(content)


def run_test(test_name: str, test_func, expected_to_fail_for_user: bool = False):
    """
    Run a test for the current user context, handling expected failures for restricted roles.

    Args:
        test_name: Name of the test for logging
        test_func: Function to execute
        expected_to_fail_for_user: If True, the test is expected to fail for "user" role
    """
    role = ctx.current_user.role_name
    should_fail = expected_to_fail_for_user and role == "user"

    try:
        result = test_func()
        if should_fail:
            print(
                f"⚠️ [{role}] {test_name}: Succeeded but was expected to fail (scope issue?)"
            )
            ctx.record_result(test_name, role, success=True, expected_to_fail=True)
        else:
            print(f"✅ [{role}] {test_name}: Passed")
            ctx.record_result(test_name, role, success=True)
        return result
    except Exception as e:
        error_msg = str(e)
        if should_fail:
            # Check if it's a permission error (403, 401, or scope-related)
            if (
                "403" in error_msg
                or "401" in error_msg
                or "Unauthorized" in error_msg
                or "scope" in error_msg.lower()
                or "permission" in error_msg.lower()
            ):
                print(
                    f"✅ [{role}] {test_name}: Correctly denied (as expected for user role)"
                )
                ctx.record_result(
                    test_name,
                    role,
                    success=False,
                    error=error_msg,
                    expected_to_fail=True,
                )
            else:
                print(
                    f"❌ [{role}] {test_name}: Failed with unexpected error: {error_msg}"
                )
                ctx.record_result(
                    test_name,
                    role,
                    success=False,
                    error=error_msg,
                    expected_to_fail=True,
                )
        else:
            print(f"❌ [{role}] {test_name}: Failed - {error_msg}")
            ctx.record_result(test_name, role, success=False, error=error_msg)
        return None


def register_user(email: str, first_name: str, last_name: str) -> tuple:
    """Register a new user and return (sdk, otp_uri, mfa_token)"""
    sdk = AGiXTSDK(base_uri=ctx.base_uri, verbose=ctx.verbose)
    failures = 0

    while failures < 100:
        try:
            otp_uri = sdk.register_user(
                email=email, first_name=first_name, last_name=last_name
            )
            mfa_token = str(otp_uri).split("secret=")[1].split("&")[0]
            return sdk, otp_uri, mfa_token
        except Exception as e:
            print(f"Registration attempt failed: {e}")
            failures += 1
            time.sleep(5)

    raise Exception(f"Failed to register user {email} after {failures} attempts")


def invite_and_register_user(
    admin_sdk: AGiXTSDK,
    company_id: str,
    email: str,
    first_name: str,
    last_name: str,
    role_id: int = 3,
) -> tuple:
    """
    Invite a user to a company and register them.

    Returns: (sdk, invitation_response)
    """
    # Create invitation using admin's token
    invitation_data = {"email": email, "company_id": company_id, "role_id": role_id}

    response = requests.post(
        f"{ctx.base_uri}/v1/invitations",
        json=invitation_data,
        headers=admin_sdk.headers,
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to create invitation: {response.status_code} - {response.text}"
        )

    invitation = response.json()
    invitation_id = invitation.get("id")
    invitation_link = invitation.get("invitation_link", "")

    print(f"✅ Created invitation for {email} with role_id={role_id}")
    print(f"   Invitation ID: {invitation_id}")

    # If user already exists (is_accepted=True), we can just login
    if invitation.get("is_accepted"):
        print(f"   User already exists, logging in...")
        # User exists, need to login - but we need their MFA token
        # For testing, we'll register a fresh user instead
        pass

    # Register the new user with the invitation
    sdk = AGiXTSDK(base_uri=ctx.base_uri, verbose=ctx.verbose)

    # The registration endpoint accepts invitation_id
    register_response = requests.post(
        f"{ctx.base_uri}/v1/user",
        json={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "invitation_id": invitation_id if invitation_id != "none" else "",
        },
    )

    if register_response.status_code != 200:
        raise Exception(
            f"Failed to register invited user: {register_response.status_code} - {register_response.text}"
        )

    reg_data = register_response.json()

    if "otp_uri" in reg_data:
        mfa_token = str(reg_data["otp_uri"]).split("secret=")[1].split("&")[0]
        totp = pyotp.TOTP(mfa_token)
        sdk.login(email=email, otp=totp.now())
        print(f"✅ Registered and logged in invited user: {email}")
        return sdk, reg_data["otp_uri"], mfa_token, invitation
    else:
        raise Exception(f"Unexpected registration response: {reg_data}")


# ============================================
# Setup: Register Admin User (Company Admin)
# ============================================

random_string = "".join(
    random.choices(string.ascii_uppercase + string.digits, k=10)
).lower()
admin_email = f"{random_string}_admin@test.com"

print("=" * 60)
print("SETTING UP ADMIN USER (Company Admin - role_id=2)")
print("=" * 60)

admin_sdk, admin_otp_uri, admin_mfa_token = register_user(
    email=admin_email, first_name="Admin", last_name="User"
)

# Get admin user details to find company_id
admin_user_details = admin_sdk.get_user()
admin_company_id = None
if admin_user_details and admin_user_details.get("companies"):
    admin_company_id = admin_user_details["companies"][0]["id"]
    admin_user_id = admin_user_details.get("id", "")
    print(f"✅ Admin user company_id: {admin_company_id}")

ctx.admin_user = UserContext(
    email=admin_email,
    role_name="company_admin",
    role_id=2,
    sdk=admin_sdk,
    otp_uri=admin_otp_uri,
    mfa_token=admin_mfa_token,
    user_id=admin_user_id,
    company_id=admin_company_id,
)

# ============================================
# Setup: Invite and Register Regular User
# ============================================

print("\n" + "=" * 60)
print("SETTING UP REGULAR USER (User - role_id=3)")
print("=" * 60)

user_email = f"{random_string}_user@test.com"

try:
    user_sdk, user_otp_uri, user_mfa_token, invitation = invite_and_register_user(
        admin_sdk=admin_sdk,
        company_id=admin_company_id,
        email=user_email,
        first_name="Regular",
        last_name="User",
        role_id=3,  # "user" role
    )

    user_details = user_sdk.get_user()
    user_id = user_details.get("id", "") if user_details else ""

    ctx.regular_user = UserContext(
        email=user_email,
        role_name="user",
        role_id=3,
        sdk=user_sdk,
        otp_uri=user_otp_uri,
        mfa_token=user_mfa_token,
        user_id=user_id,
        company_id=admin_company_id,  # Same company as admin
    )
    print(f"✅ Regular user setup complete: {user_email}")
except Exception as e:
    print(f"⚠️ Failed to set up regular user: {e}")
    print("   Tests will only run for admin user")
    ctx.regular_user = None

# Set initial context to admin user
ctx.set_current_user(ctx.admin_user)

# Setup openai client for current user
openai.base_url = "http://localhost:7437/v1/"
openai.api_key = ctx.current_user.sdk.headers["Authorization"]
openai.api_type = "openai"

# For backward compatibility, maintain these global variables
agixt = ctx.current_user.sdk
test_email = ctx.current_user.email

# Show QR code for MFA setup (admin user)
import qrcode

qr = qrcode.QRCode()
qr.add_data(admin_otp_uri)
qr.make(fit=True)
img = qr.make_image(fill="black", back_color="white")
qr_path = os.path.join(TEST_DIR, "qr.png")
img.save(qr_path)
print(f"QR code saved to {qr_path} for MFA setup")

# Display in Jupyter if available
try:
    from IPython.display import Image as IPImage

    IPImage(filename=qr_path)
except ImportError:
    pass


# ## Confirm user exists
#

# In[9]:


user_exists = agixt.user_exists(email=test_email)


# ## Update User's Name

# In[10]:


update_user = agixt.update_user(first_name="Super", last_name="Man")


# ## Get User Details

# In[11]:


user_details = agixt.get_user()


#
# ## Get a list of Providers
#
# This will get a list of AI Providers available to use with AGiXT.
#

# In[5]:


providers = agixt.get_providers()


# ## Get a list of Providers for a services
#
# - Service options are `llm`, `tts`, `image`, `embeddings`, `transcription`, and `translation`.
#

# In[6]:


services = agixt.get_providers_by_service(service="tts")


# ## Get Default Provider Settings
#
# Choose a provider from the list of AI providers and get the default settings for that provider.
#

# In[7]:


provider_name = "ezlocalai"
provider_settings = agixt.get_provider_settings(provider_name=provider_name)


# ## Get Embedding Providers
#
# Embedding providers are used to embed information to vectors to store in the vector database to be searched for context injection.
#

# In[8]:


embed_providers = agixt.get_embed_providers()


# ### Chat Completion Tests
#
# [OpenAI API Reference](https://platform.openai.com/docs/api-reference/chat)
#

# In[9]:


# Modify this prompt to generate different outputs
prompt = "Write a short poem about Pikachu with a picture."
agent_name = "XT"

response = openai.chat.completions.create(
    model=agent_name,  # Model is Agent Name
    messages=[{"role": "user", "content": prompt}],
    stream=False,
    user="Pikachu Poem",  # User is Conversation Name
)
display_content(response.choices[0].message.content)


# ## Get Extension Settings
#
# This is where we get all third party extension settings for the agent with defaults to fill in when there is nothing entered on the front end.
#

# In[10]:


ext_settings_resp = agixt.get_extension_settings()


# In[11]:


import requests
from pprint import pprint

response = requests.get(
    f"{agixt.base_uri}/v1/extension/categories", headers=agixt.headers
)
pprint(response.json())


#

# In[ ]:


# ## Webhook Tests
#
# This section tests the webhook system endpoints including incoming and outgoing webhooks using the AGiXT SDK.

# In[14]:


# Test creating an outgoing webhook using requests
from datetime import datetime
import json

outgoing_webhook_data = {
    "name": "Test Webhook",
    "description": f"Test webhook created at {datetime.now().isoformat()}",
    "target_url": "https://webhook.site/test",
    "event_types": ["agent.created", "agent.deleted"],
    "active": True,
    "headers": {"Content-Type": "application/json"},
    "secret": "test-secret-123",
}

# Using requests to create webhook
response = requests.post(
    "http://localhost:7437/api/webhooks/outgoing",
    json=outgoing_webhook_data,
    headers=agixt.headers,
)
print(f"Created outgoing webhook: {response.status_code} - {response.json()}")
created_webhook = response.json() if response.status_code == 200 else None


# In[13]:


# Test listing outgoing webhooks using requests
response = requests.get(
    "http://localhost:7437/api/webhooks/outgoing",
    headers=agixt.headers,
)
print(f"Get webhooks response: {response.status_code}")
if response.status_code == 200:
    webhooks = response.json()
    print(f"Found {len(webhooks)} outgoing webhooks")
    for webhook in webhooks:
        print(
            f"  - {webhook.get('name', 'Unnamed')}: {webhook.get('target_url', 'No URL')}"
        )
else:
    print(f"Error getting webhooks: {response.text}")
    webhooks = []


# In[ ]:


# Test incoming webhook with agent_id parameter (alternative format)
print("--- Testing incoming webhook with agent_id parameter ---")

# Get the user details which contains the agent_id
user_details = agixt.get_user()
agent_id = (
    user_details["companies"][0]["agents"][0]["id"]
    if user_details and user_details.get("companies")
    else None
)

if agent_id:
    print(f"Found user agent_id: {agent_id}")

    incoming_webhook_data_with_id = {
        "name": "Agent ID Test Webhook",
        "description": "Testing webhook creation with agent_id parameter",
        "agent_id": agent_id,  # Using agent_id instead of agent_name
        "secret": "agent-id-secret-456",
        "transform_template": json.dumps(
            {"event": "{{ event_type }}", "data": "{{ data }}"}
        ),
    }

    response = requests.post(
        "http://localhost:7437/api/webhooks/incoming",
        json=incoming_webhook_data_with_id,
        headers=agixt.headers,
    )

    print(f"Incoming webhook with agent_id: {response.status_code}")
    if response.status_code == 200:
        print("✅ Successfully created incoming webhook using agent_id parameter")
        agent_id_webhook = response.json()
        print(f"Webhook ID: {agent_id_webhook.get('id', 'Unknown')}")
    else:
        print(f"❌ Failed to create webhook with agent_id: {response.text}")
else:
    print("❌ Could not get agent_id from user details, skipping agent_id test")

print("--- Agent ID parameter test completed ---\n")


# In[ ]:


# Test webhook event emission
# This would trigger any configured webhooks for agent events
test_agent = "webhook_test_agent"

# Create an agent to trigger webhook events
agixt.add_agent(
    agent_name=test_agent,
    settings={
        "mode": "prompt",
        "prompt_category": "Default",
        "prompt_name": "Think About It",
        "persona": "",
    },
)
print(f"Created agent {test_agent}, webhook events should have been triggered")


# In[ ]:


# Test webhook logs and statistics using requests
# Get webhook statistics
stats_response = requests.get(
    "http://localhost:7437/api/webhooks/stats",
    headers=agixt.headers,
)
if stats_response.status_code == 200:
    webhook_stats = stats_response.json()
    print(f"Webhook statistics: {json.dumps(webhook_stats, indent=2)}")
else:
    print(f"Error getting webhook stats: {stats_response.text}")

# Get webhook logs
logs_response = requests.get(
    "http://localhost:7437/api/webhooks/logs?limit=10",
    headers=agixt.headers,
)
if logs_response.status_code == 200:
    webhook_logs = logs_response.json()
    print(f"Found {len(webhook_logs)} webhook log entries")
    if webhook_logs:
        print(f"Latest log: {webhook_logs[0]}")
else:
    print(f"Error getting webhook logs: {logs_response.text}")


# In[ ]:


# Test webhook stats and logs endpoint response structure
print("--- Validating webhook stats and logs response structure ---")

# Test webhook stats response structure
stats_response = requests.get(
    "http://localhost:7437/api/webhooks/stats",
    headers=agixt.headers,
)

if stats_response.status_code == 200:
    stats_data = stats_response.json()
    print("✅ Webhook stats endpoint accessible")

    # Validate expected fields in stats response
    expected_stats_fields = [
        "total_outgoing",
        "total_incoming",
        "active_outgoing",
        "active_incoming",
    ]
    missing_stats_fields = [
        field for field in expected_stats_fields if field not in stats_data
    ]

    if missing_stats_fields:
        print(f"⚠️ Stats response missing expected fields: {missing_stats_fields}")
        print(f"Available fields: {list(stats_data.keys())}")
    else:
        print("✅ Stats response has all expected fields")
        print(f"Stats summary: {stats_data}")
else:
    print(
        f"❌ Webhook stats endpoint failed: {stats_response.status_code} - {stats_response.text}"
    )

# Test webhook logs response structure
logs_response = requests.get(
    "http://localhost:7437/api/webhooks/logs?limit=5",
    headers=agixt.headers,
)

if logs_response.status_code == 200:
    logs_data = logs_response.json()
    print("✅ Webhook logs endpoint accessible")

    if isinstance(logs_data, list):
        print(f"✅ Logs returned as list with {len(logs_data)} entries")

        if logs_data:
            # Validate log entry structure
            log_entry = logs_data[0]
            expected_log_fields = ["id", "webhook_id", "direction", "timestamp"]
            missing_log_fields = [
                field for field in expected_log_fields if field not in log_entry
            ]

            if missing_log_fields:
                print(f"⚠️ Log entry missing expected fields: {missing_log_fields}")
                print(f"Available fields: {list(log_entry.keys())}")
            else:
                print("✅ Log entries have expected structure")
        else:
            print("ℹ️ No webhook logs found (this is expected for new installations)")
    else:
        print(f"❌ Logs response should be a list, got {type(logs_data)}")
else:
    print(
        f"❌ Webhook logs endpoint failed: {logs_response.status_code} - {logs_response.text}"
    )

print("--- Endpoint structure validation completed ---\n")


# In[ ]:


# Cleanup: Delete test webhooks and agent using requests
# Get all outgoing webhooks and delete test ones
response = requests.get(
    "http://localhost:7437/api/webhooks/outgoing",
    headers=agixt.headers,
)
if response.status_code == 200:
    webhooks = response.json()
    for webhook in webhooks:
        if webhook.get("name") == "Test Webhook":
            delete_response = requests.delete(
                f"http://localhost:7437/api/webhooks/outgoing/{webhook['id']}",
                headers=agixt.headers,
            )
            if delete_response.status_code == 200:
                print(f"Deleted outgoing webhook: {webhook['name']}")
            else:
                print(f"Error deleting outgoing webhook: {delete_response.text}")

# Get all incoming webhooks and delete test ones
response = requests.get(
    "http://localhost:7437/api/webhooks/incoming",
    headers=agixt.headers,
)
if response.status_code == 200:
    webhooks = response.json()
    for webhook in webhooks:
        if webhook.get("name") == "GitHub Webhook":
            delete_response = requests.delete(
                f"http://localhost:7437/api/webhooks/incoming/{webhook['id']}",
                headers=agixt.headers,
            )
            if delete_response.status_code == 200:
                print(f"Deleted incoming webhook: {webhook['name']}")
            else:
                print(f"Error deleting incoming webhook: {delete_response.text}")


# In[ ]:


# Test updating an outgoing webhook using requests
# First, create a fresh webhook to ensure we have one owned by current user
from datetime import datetime

print("--- Creating a webhook for update test ---")
test_webhook_data = {
    "name": "Webhook for Update Test",
    "description": f"Test webhook created at {datetime.now().isoformat()}",
    "target_url": "https://webhook.site/update-test",
    "event_types": ["agent.created", "agent.deleted"],
    "active": True,
    "headers": {"Content-Type": "application/json"},
    "secret": "update-test-secret",
}

response = requests.post(
    "http://localhost:7437/api/webhooks/outgoing",
    json=test_webhook_data,
    headers=agixt.headers,
)

if response.status_code == 200:
    webhook_for_update = response.json()
    webhook_id = webhook_for_update["id"]
    print(f"✅ Created webhook for update test: {webhook_id}")

    # Now test updating the webhook
    print("\n--- Testing webhook update ---")
    update_data = {
        "name": "Updated Test Webhook",
        "description": "Updated webhook description",
        "event_types": ["agent.created", "agent.deleted", "chat.completed"],
        "active": True,
    }

    response = requests.put(
        f"http://localhost:7437/api/webhooks/outgoing/{webhook_id}",
        json=update_data,
        headers=agixt.headers,
    )

    if response.status_code == 200:
        updated_webhook = response.json()
        print(
            f"✅ Successfully updated webhook: {updated_webhook.get('name', 'Unknown')}"
        )
        print(f"   Description: {updated_webhook.get('description', 'No description')}")
        print(f"   Event types: {updated_webhook.get('event_types', [])}")
        print(f"   Webhook ID: {updated_webhook.get('id', 'Unknown')}")
    else:
        print(f"❌ Error updating webhook: {response.status_code} - {response.text}")
else:
    print(
        f"❌ Failed to create webhook for update test: {response.status_code} - {response.text}"
    )
    print("Skipping update test")


# ## Get Extension Commands
#

# In[ ]:


ext = agixt.get_extensions()


# ## Get command arguments
#

# In[ ]:


command_args = agixt.get_command_args(command_name="Write to File")


# ## Create a new Agent
#
# Creates a new agent with the `ezlocalai` provider.
#

# In[12]:


# Create a new agent and capture the returned ID
agent_name = "test_agent"
add_agent_resp = agixt.add_agent(
    agent_name=agent_name,
    settings={
        "mode": "prompt",
        "prompt_category": "Default",
        "prompt_name": "Think About It",
        "persona": "",
    },
)
# The response includes the agent ID
test_agent_id = add_agent_resp.get("id") or add_agent_resp.get("agent_id")
print(f"Created agent with ID: {test_agent_id}")


# # Test creating an incoming webhook for an agent using requests

# In[ ]:


# Using test_agent_id instead of hardcoded agent_name
incoming_webhook_data = {
    "name": "GitHub Webhook",
    "description": "Webhook for GitHub events",
    "agent_id": test_agent_id,
    "secret": "github-secret-123",
    "transform_template": json.dumps(
        {
            "action": "{{ action }}",
            "repository": "{{ repository.name }}",
            "sender": "{{ sender.login }}",
        }
    ),
}

response = requests.post(
    "http://localhost:7437/api/webhooks/incoming",
    json=incoming_webhook_data,
    headers=agixt.headers,
)
print(
    f"Created incoming webhook: {response.status_code} - {response.json() if response.status_code == 200 else response.text}"
)
incoming_webhook = response.json() if response.status_code == 200 else None
# Additional webhook validation tests
print("=== Running additional webhook validation tests ===")

# Test 1: Verify webhook creation response structure
if created_webhook and isinstance(created_webhook, dict):
    required_fields = ["id", "name", "target_url", "event_types", "active"]
    missing_fields = [
        field for field in required_fields if field not in created_webhook
    ]
    if missing_fields:
        print(f"❌ Created webhook missing required fields: {missing_fields}")
    else:
        print("✅ Created webhook has all required fields")

    # Verify field types
    if "id" in created_webhook and not isinstance(created_webhook["id"], str):
        print(f"❌ Webhook ID should be string, got {type(created_webhook['id'])}")
    else:
        print("✅ Webhook ID is properly formatted as string")
else:
    print("❌ Webhook creation failed - cannot validate response structure")

# Test 2: Test webhook with different event types (using valid event types only)
print("\n--- Testing webhook with different event types ---")
event_test_data = {
    "name": "Event Test Webhook",
    "description": "Testing different event types",
    "target_url": "https://httpbin.org/post",
    # Use only valid core event types from WebhookManager.CORE_WEBHOOK_EVENT_TYPES
    "event_types": ["conversation.started", "conversation.ended", "chat.message"],
    "active": True,
}

event_response = requests.post(
    "http://localhost:7437/api/webhooks/outgoing",
    json=event_test_data,
    headers=agixt.headers,
)
print(f"Event types test webhook: {event_response.status_code}")
if event_response.status_code == 200:
    print("✅ Webhook with different event types created successfully")
    event_webhook = event_response.json()
    print(f"Created webhook with events: {event_webhook.get('event_types', [])}")
else:
    print(f"❌ Failed to create event webhook: {event_response.text}")

# Test 3: Incoming webhook validation
# The incoming webhook response uses 'webhook_id' instead of 'id'
if incoming_webhook and isinstance(incoming_webhook, dict):
    incoming_required = ["webhook_id", "name", "agent_id", "api_key", "webhook_url"]
    missing_incoming = [
        field for field in incoming_required if field not in incoming_webhook
    ]
    if missing_incoming:
        print(f"❌ Incoming webhook missing fields: {missing_incoming}")
    else:
        print("✅ Incoming webhook has all required fields")
else:
    print("❌ Incoming webhook creation failed - cannot validate")

print("=== Webhook validation tests completed ===\n")


# ## Get Extensions Available to Agent
#
# This function will get a list of extensions available to the agent as well as the required settings keys and available commands per extension. If the agent does not have the settings keys for the specific extension, the list of commands will be empty.

# In[ ]:


# Get extensions available to the agent by ID
agent_extensions = agixt.get_agent_extensions(agent_id=test_agent_id)


# ## Execute a Command
#

# In[ ]:


# Execute a command using the agent ID
command_execution = agixt.execute_command(
    agent_id=test_agent_id,
    command_name="Write to File",
    command_args={"filename": "test files.txt", "text": "This is just a test!"},
    conversation_id="",  # Empty string for new conversation
)


# ## Get a list of all current Agents
#
# Any agents that you have created will be listed here. The `status` field is to say if the agent is currently running a task or not.
#

# In[ ]:


# Get a list of all agents with their IDs
agents = agixt.get_agents()
print(f"Found {len(agents)} agents")
for a in agents:
    print(f"  - {a.get('name', 'N/A')} (id: {a.get('id', 'N/A')})")


# ## Rename the test agent
#
# We will just rename it to `new_agent`.
#

# In[ ]:


# Rename the agent using its ID
new_agent_name = "new_agent"
rename_agent_resp = agixt.rename_agent(agent_id=test_agent_id, new_name=new_agent_name)
print(f"Renamed agent: {rename_agent_resp}")


# ## Get the agent's settings
#
# This will get the settings for the agent we just created, this will tell you all commands available to the agent as well as all of the provider settings for the agent.
#

# In[ ]:


# Get the agent's config by ID
agent_config = agixt.get_agentconfig(agent_id=test_agent_id)
print(
    f"Agent config keys: {agent_config.keys() if isinstance(agent_config, dict) else 'N/A'}"
)


# ## Update the agent's settings
#
# We'll just update the temperature from the default `0.7` to `0.8` to confirm that we can modify a setting.
#

# In[ ]:


# Update the agent's settings by ID
agent_config = agixt.get_agentconfig(agent_id=test_agent_id)
agent_settings = agent_config["settings"]
# We'll just change the AI_TEMPERATURE setting for the test
agent_settings["AI_TEMPERATURE"] = 0.8
update_agent_settings_resp = agixt.update_agent_settings(
    agent_id=test_agent_id, settings=agent_settings
)
print("Update agent settings response:", update_agent_settings_resp)
agent_config = agixt.get_agentconfig(agent_id=test_agent_id)


# ## Get a list of the agent's commands
#
# This will get a list of all commands available to the agent.
#

# In[ ]:


# Get a list of commands for the agent by ID
commands = agixt.get_commands(agent_id=test_agent_id)


# ## Toggle a Command for the Agent
#
# We'll toggle the `Write to File` command to `true` to confirm that we can toggle a command.
#

# In[ ]:


# Toggle the Write to File command using agent ID
toggle_command_resp = agixt.toggle_command(
    agent_id=test_agent_id, command_name="Write to File", enable=True
)
print(f"Toggle command response: {toggle_command_resp}")


# ## Update Agent Commands
#
# In this example, we'll only change the `Convert Markdown to PDF` command to `False`, but we could change any (or all) of the commands with this API call.

# In[ ]:


# Update agent commands using agent ID
agent_config = agixt.get_agentconfig(agent_id=test_agent_id)
if agent_config.get("commands") is not None:
    agent_commands = agent_config["commands"]
else:
    agent_commands = {}
agent_commands["Convert Markdown to PDF"] = False
update_agent_commands_resp = agixt.update_agent_commands(
    agent_id=test_agent_id, commands=agent_commands
)
print(f"Update commands response: {update_agent_commands_resp}")
agent_config = agixt.get_agentconfig(agent_id=test_agent_id)


# ## Create a new conversation
#

# In[ ]:


# Create a new conversation using agent ID
conversation_resp = agixt.new_conversation(
    agent_id=test_agent_id, conversation_name="Talk for Tests"
)
talk_conversation_id = conversation_resp.get("id")
print(f"Created conversation with ID: {talk_conversation_id}")


# ## Get Conversations
#

# In[ ]:


# Get all conversations (returns dict with conversation IDs as keys)
conversations = agixt.get_conversations()
print(f"Found {len(conversations)} conversations")
# conversations is a dict like {"conv_id": {"name": "...", "agent_id": "...", ...}}
for conv_id, conv_data in list(conversations.items())[:5]:  # Show first 5
    print(f"  - {conv_data.get('name', 'N/A')} (id: {conv_id})")


# ## Manual Conversation Message

# In[ ]:


# Create a new conversation for message tests
msg_conv_resp = agixt.new_conversation(
    agent_id=test_agent_id, conversation_name="AGiXT Conversation"
)
agixt_conversation_id = msg_conv_resp.get("id")
print(f"Created AGiXT Conversation with ID: {agixt_conversation_id}")

# Add messages using conversation ID
agixt.new_conversation_message(
    role="USER",
    conversation_id=agixt_conversation_id,
    message="This is a test message from the user!",
)
agixt.new_conversation_message(
    role="new_agent",
    conversation_id=agixt_conversation_id,
    message="This is a test message from the agent!",
)


# ## Get Conversation Details
#

# In[ ]:


# Get conversation details by ID
conversation = agixt.get_conversation(
    conversation_id=agixt_conversation_id, limit=100, page=1
)
print(f"Got {len(conversation)} messages in conversation")


# ## Fork a Conversation

# In[ ]:


# Add extra messages to the conversation for forking
agixt.new_conversation_message(
    role="USER",
    conversation_id=agixt_conversation_id,
    message="This is a test message from the user!",
)
agixt.new_conversation_message(
    role="new_agent",
    conversation_id=agixt_conversation_id,
    message="This is a test message from the agent!",
)

# Get updated conversation to get message IDs
conversation = agixt.get_conversation(
    conversation_id=agixt_conversation_id, limit=100, page=1
)

# Fork the conversation from the second message
if len(conversation) >= 2:
    message_id = conversation[1]["id"]
    forked_resp = agixt.fork_conversation(
        conversation_id=agixt_conversation_id, message_id=message_id
    )
    forked_conversation_id = (
        forked_resp.get("id") if isinstance(forked_resp, dict) else None
    )
    print(f"Forked conversation ID: {forked_conversation_id}")

    # Get the forked conversation
    if forked_conversation_id:
        fork = agixt.get_conversation(conversation_id=forked_conversation_id)
        print(f"Forked conversation has {len(fork)} messages")


# ## Delete Message from Conversation
#

# In[ ]:


# Delete a message from the conversation by IDs
conversation = agixt.get_conversation(
    conversation_id=agixt_conversation_id, limit=100, page=1
)
if len(conversation) > 0:
    message_to_delete = conversation[0]
    message_id = message_to_delete["id"]
    print(f"Deleting message: {message_to_delete['message'][:50]}...")
    delete_msg_resp = agixt.delete_conversation_message(
        conversation_id=agixt_conversation_id, message_id=message_id
    )
    print(f"Delete response: {delete_msg_resp}")


# ## Delete a Conversation
#

# In[ ]:


# Delete the conversation by ID
delete_conv_resp = agixt.delete_conversation(conversation_id=agixt_conversation_id)
print(f"Delete conversation response: {delete_conv_resp}")


# ## Have the Agent Learn from specified Text
#

# In[ ]:


# Learn text using agent ID
text_learning = agixt.learn_text(
    agent_id=test_agent_id,
    user_input="What is AGiXT?",
    text="AGiXT is an open-source artificial intelligence automation platform.",
    collection_number="0",
)
print(f"Learn text response: {text_learning}")


# ## Have the Agent Learn from Files
#

# ### Zip

# In[ ]:


import base64

learn_file_path = os.path.join(TEST_DIR, "test.zip")
with open(learn_file_path, "rb") as f:
    learn_file_content = base64.b64encode(f.read()).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="test.zip",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn zip file response: {file_learning}")


# ### CSV

# In[ ]:


import base64

learn_file_path = os.path.join(TEST_DIR, "test.csv")
with open(learn_file_path, "rb") as f:
    learn_file_content = base64.b64encode(f.read()).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="test.csv",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn csv file response: {file_learning}")


# ### XLS/XLSX

# In[ ]:


import base64

learn_file_path = os.path.join(TEST_DIR, "test.xlsx")
with open(learn_file_path, "rb") as f:
    learn_file_content = base64.b64encode(f.read()).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="test.xlsx",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn xlsx file response: {file_learning}")


# ### DOC/DOCX

# In[ ]:


import base64

learn_file_path = os.path.join(TEST_DIR, "test.docx")
with open(learn_file_path, "rb") as f:
    learn_file_content = base64.b64encode(f.read()).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="test.docx",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn docx file response: {file_learning}")


# ### PPT/PPTX

# In[ ]:


import requests
import base64

ppt_url = "https://getsamplefiles.com/download/pptx/sample-1.pptx"
response = requests.get(ppt_url)
learn_file_path = os.path.join(TEST_DIR, "sample-1.pptx")
with open(learn_file_path, "wb") as f:
    f.write(response.content)
learn_file_content = base64.b64encode(response.content).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="sample-1.pptx",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn pptx file response: {file_learning}")


# ### PDF

# In[ ]:


import requests
import base64

pdf_url = "https://getsamplefiles.com/download/pdf/sample-1.pdf"
response = requests.get(pdf_url)
learn_file_path = os.path.join(TEST_DIR, "sample-1.pdf")
with open(learn_file_path, "wb") as f:
    f.write(response.content)
learn_file_content = base64.b64encode(response.content).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="sample-1.pdf",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn pdf file response: {file_learning}")


# ### TXT

# In[ ]:


import base64

learn_file_path = os.path.join(TEST_DIR, "test.txt")
with open(learn_file_path, "rb") as f:
    learn_file_content = base64.b64encode(f.read()).decode("utf-8")

file_learning = agixt.learn_file(
    agent_id=test_agent_id,
    file_name="test.txt",
    file_content=learn_file_content,
    collection_number="0",
)
print(f"Learn txt file response: {file_learning}")


# ## Have the Agent Learn from a URL
#

# In[ ]:


# Learn from a URL using agent ID
url_learning = agixt.learn_url(
    agent_id=test_agent_id,
    url="https://josh-xt.github.io/AGiXT",
    collection_number="0",
)
print(f"Learn URL response: {url_learning}")


# ## Get the Agents Memories
#
# Get some relevant memories from the agent about AGiXT.
#

# In[ ]:


# Get agent memories using agent ID
memories = agixt.get_agent_memories(
    agent_id=test_agent_id,
    user_input="What can you tell me about AGiXT?",
    limit=10,
    min_relevance_score=0.2,
    collection_number="0",
)
print(f"Found {len(memories)} relevant memories")


# ## Delete a Memory
#
# Delete a specific memory by Memory ID.
#

# In[ ]:


# Get agent memories to find one to delete
memories = agixt.get_agent_memories(
    agent_id=test_agent_id,
    user_input="What can you tell me about AGiXT?",
    limit=1,
    min_relevance_score=0.2,
    collection_number="0",
)
# Remove the first memory
if memories:
    memory = memories[0]
    memory_id = memory.get("id")
    print(f"Memory: {memory}")
    if memory_id:
        print(f"Memory ID: {memory_id}")
        delete_memory_resp = agixt.delete_agent_memory(
            agent_id=test_agent_id, memory_id=memory_id, collection_number="0"
        )
        print(f"Delete memory response: {delete_memory_resp}")


# ## Wipe the agents memories
#
# This is necessary if you want the agent to serve a different purpose than its original intent after it has learned things. It may inject unnecessary context into the conversation if you don't wipe its memory and try to give it a different purpose, even temporarily.
#

# In[ ]:


# Wipe agent memories using agent ID
# Note: Use this function with caution as it will erase the agent's memory.
wipe_mem_resp = agixt.wipe_agent_memories(agent_id=test_agent_id, collection_number="0")
print(f"Wipe memories response: {wipe_mem_resp}")


# ## Get a list of Chains available to use
#

# In[ ]:


# Get a list of chains (returns list with IDs)
chains = agixt.get_chains()
print(f"Found {len(chains)} chains")
for c in chains[:5]:  # Show first 5
    print(f"  - {c.get('chainName', 'N/A')} (id: {c.get('id', 'N/A')})")


# ## Create a new chain
#

# In[ ]:


# Create a new chain and capture the ID
chain_name = "Write another Poem"
add_chain_resp = agixt.add_chain(chain_name=chain_name)
test_chain_id = add_chain_resp.get("id")
print(f"Created chain with ID: {test_chain_id}")


# ## Rename the chain
#

# In[ ]:


# Rename the chain using ID
new_chain_name = "Poem Writing Chain"
rename_chain_resp = agixt.rename_chain(chain_id=test_chain_id, new_name=new_chain_name)
print(f"Rename chain response: {rename_chain_resp}")


# ## Add Chain Steps
#

# In[ ]:


# Add chain steps using chain ID and agent ID
add_step_resp = agixt.add_step(
    chain_id=test_chain_id,
    step_number=1,
    agent_id=test_agent_id,
    prompt_type="Prompt",
    prompt={
        "prompt_name": "Write a Poem",
        "subject": "Artificial Intelligence",
    },
)
print(f"Add step 1 response: {add_step_resp}")

add_step_resp = agixt.add_step(
    chain_id=test_chain_id,
    step_number=2,
    agent_id=test_agent_id,
    prompt_type="Prompt",
    prompt={
        "prompt_name": "Write a Poem",
        "subject": "Quantum Computers",
    },
)
print(f"Add step 2 response: {add_step_resp}")


# ## Get the content of the chain
#

# In[ ]:


# Get the chain content by ID
chain = agixt.get_chain(chain_id=test_chain_id)
print(f"Chain: {chain}")


# ## Get Chain Arguments
#

# In[ ]:


# Get chain arguments by ID
chain_args = agixt.get_chain_args(chain_id=test_chain_id)
print(f"Chain args: {chain_args}")


# ## Modify a chain step
#
# Instead of the subject of the poem just being Artificial Intelligence, we'll change it to be Artificial General Intelligence.
#

# In[ ]:


# Update a chain step using chain ID and agent ID
update_step_resp = agixt.update_step(
    chain_id=test_chain_id,
    step_number=1,
    agent_id=test_agent_id,
    prompt_type="Prompt",
    prompt={
        "prompt_name": "Write a Poem",
        "subject": "Artificial General Intelligence",
    },
)
print(f"Update step response: {update_step_resp}")


# ## Move the chain step
#
# When you move a step, it will automatically reassign the order of the steps to match the new order. If there are only 2 steps like in our case, it will just swap them.
#

# In[ ]:


# Move a chain step using chain ID
move_step_resp = agixt.move_step(
    chain_id=test_chain_id, old_step_number=1, new_step_number=2
)
print(f"Move step response: {move_step_resp}")


# ## Delete a step from the chain
#

# In[ ]:


# Delete a step from the chain using chain ID
delete_step_resp = agixt.delete_step(chain_id=test_chain_id, step_number=2)
print(f"Delete step response: {delete_step_resp}")


# ## Add a Command to the Chain
#
# We'll write the result to a file for an example.
#

# In[ ]:


# Add a command to the chain using chain ID and agent ID
add_step_resp = agixt.add_step(
    chain_id=test_chain_id,
    step_number=2,
    agent_id=test_agent_id,
    prompt_type="Command",
    prompt={
        "command_name": "Write to File",
        "filename": "{user_input}.txt",
        "text": "Poem:\n{STEP1}",
    },
)
print(f"Add command step response: {add_step_resp}")


# ## Run the chain
#

# In[ ]:


# Run the chain using chain ID
user_input = "Super Poems"
run_chain_resp = agixt.run_chain(
    chain_id=test_chain_id, user_input=user_input, from_step=1
)
print(f"Run chain response: {run_chain_resp}")


# ## Delete the chain
#

# In[ ]:


# Delete the chain using chain ID
delete_chain_resp = agixt.delete_chain(chain_id=test_chain_id)
print(f"Delete chain response: {delete_chain_resp}")


# ## Get a list of prompts available to use
#

# In[ ]:


# Get all prompts with IDs
prompts = agixt.get_prompts(prompt_category="Default")
print(f"Found {len(prompts)} prompts in Default category")
# Each prompt has: name, category, id
for p in prompts[:5]:  # Show first 5
    print(f"  - {p['name']} (id: {p.get('id', 'N/A')})")


# ## Get the content of a prompt
#

# In[ ]:


# Get a prompt by ID (use the first prompt from the list)
if prompts:
    prompt_id = prompts[0]["id"]
    get_prompt_resp = agixt.get_prompt(prompt_id=prompt_id)
    print(f"Got prompt: {get_prompt_resp}")


# ## Create a new prompt
#
# We'll make a basic prompt that asks the AI to tell us a short story about a subject. The subject is not yet defined, it would be defined in a chain. Using `{variable_name}` in a prompt will allow you to define the variable in a chain and have it be used in the prompt.
#

# In[ ]:


# Create a new prompt and capture the returned ID
add_prompt_resp = agixt.add_prompt(
    prompt_name="Short Story",
    prompt="Tell me a short story about {subject}",
    prompt_category="Default",
)
short_story_prompt_id = add_prompt_resp.get("id")
print(f"Created prompt with ID: {short_story_prompt_id}")


# ## Get the prompt variables
#

# In[ ]:


# Get prompt arguments by ID
get_prompt_args_resp = agixt.get_prompt_args(prompt_id=short_story_prompt_id)
print(f"Prompt args: {get_prompt_args_resp}")


# ## Update the prompt content
#
# We'll ask it to `Add a dragon to the story somehow` in the prompt to make the short story more interesting.
#

# In[ ]:


# Update the prompt content by ID
update_prompt_resp = agixt.update_prompt(
    prompt_id=short_story_prompt_id,
    prompt="Tell me a short story about {subject}. Add a dragon to the story somehow.",
)
print(f"Update response: {update_prompt_resp}")


# ## Delete the prompt
#
# If you don't want the prompt anymore, delete it.
#

# In[ ]:


# Delete the prompt by ID
delete_prompt_resp = agixt.delete_prompt(prompt_id=short_story_prompt_id)
print(f"Delete response: {delete_prompt_resp}")


# ## Delete the Agent
#
# If you are done with the agent and don't want or need it anymore, you can delete it along with everything associated with it, such as its memories, settings, and history. The Agent isn't just fired, it is dead.
#

# In[ ]:


# Delete the agent using agent ID
delete_agent_resp = agixt.delete_agent(agent_id=test_agent_id)
print(f"Delete agent response: {delete_agent_resp}")


# ### Streaming Chat Completion Test
#
# Test the new streaming functionality that allows real-time streaming of AI responses.
#
# [OpenAI API Reference - Streaming](https://platform.openai.com/docs/api-reference/chat/streaming)

# In[ ]:


import time
import json

# Test streaming chat completion
prompt = "Tell me a short story about a robot learning to paint. Make it creative and engaging."

print("🎬 Starting streaming test...")
print("=" * 60)
print("Response will appear in real-time:")
print("-" * 60)

start_time = time.time()

try:
    # Create streaming request
    stream = openai.chat.completions.create(
        model=agent_name,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=300,
        temperature=0.7,
        user="Streaming Test",
    )

    # Process streaming response
    full_response = ""
    chunk_count = 0

    for chunk in stream:
        chunk_count += 1
        # Handle both standard OpenAI chunks and AGiXT activity.stream chunks
        # AGiXT may send activity.stream chunks without choices field
        if hasattr(chunk, "choices") and chunk.choices:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                print(content, end="", flush=True)

            # Check if streaming is complete
            if chunk.choices[0].finish_reason == "stop":
                break

    end_time = time.time()

    print("\n" + "-" * 60)
    print(f"✅ Streaming completed successfully!")
    print(f"📊 Statistics:")
    print(f"   • Total chunks received: {chunk_count}")
    print(f"   • Total characters: {len(full_response)}")
    print(f"   • Time taken: {end_time - start_time:.2f} seconds")
    if end_time > start_time:
        print(
            f"   • Average chars/second: {len(full_response)/(end_time - start_time):.1f}"
        )
    print("=" * 60)

except Exception as e:
    print(f"❌ Streaming test failed: {str(e)}")
    print(
        "This could indicate that streaming is not properly implemented or the agent is not available."
    )


# ### Vision Test
# The model used for tests does not have vision, but this example is here to show how you would use the endpoint if you had a model that could process images.

# In[ ]:


response = openai.chat.completions.create(
    model=agent_name,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe each stage of this image."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"https://www.visualwatermark.com/images/add-text-to-photos/add-text-to-image-3.webp"
                    },
                },
            ],
        },
    ],
    user="Vision Test",
)
display_content(response.choices[0].message.content)


# ### File Upload Test

# In[ ]:


import base64

# Download csv to hurricanes.csv
csv_url = "https://people.sc.fsu.edu/~jburkardt/data/csv/hurricanes.csv"
response = requests.get(csv_url)
base64_encoded_file = base64.b64encode(response.content).decode("utf-8")
data_url = f"data:application/csv;base64,{base64_encoded_file}"

response = openai.chat.completions.create(
    model=agent_name,
    messages=[
        {
            "role": "user",
            "analyze_user_input": "false",
            "content": [
                {
                    "type": "text",
                    "text": "Which month had the most hurricanes according to the data provided?",
                },
                {
                    "type": "file_url",
                    "file_url": {
                        "url": data_url,
                    },
                },
            ],
        },
    ],
    user="Data Analysis",
)
display_content(response.choices[0].message.content)


# ### Websearch Test

# In[ ]:


# Modify this prompt to generate different outputs
prompt = "What are the latest critical windows vulnerabilities that have recently been patched in the past week?"


response = openai.chat.completions.create(
    model=agent_name,
    messages=[
        {
            "role": "user",
            "websearch": "true",
            "websearch_depth": "2",
            "content": prompt,
        }
    ],
    stream=False,
    user="Windows Vulnerabilities",
)
display_content(response.choices[0].message.content)


# ============================================
# DUAL-ROLE TEST RUNNER
# ============================================
# This section runs comprehensive tests for both company_admin and user roles
# to validate scope-based access controls.

# In[ ]:


print("\n" + "=" * 80)
print("STARTING DUAL-ROLE SCOPE VALIDATION TESTS")
print("=" * 80)
print("\nThis test suite validates that scopes are properly enforced for both:")
print("  - company_admin (role_id=2): Full management access")
print("  - user (role_id=3): Limited read/execute access")
print("=" * 80 + "\n")


# Define test functions that will be run for both roles
def test_user_operations():
    """Test basic user operations (should work for all roles)"""
    sdk = ctx.current_user.sdk

    # Get user details
    user = sdk.get_user()
    assert user is not None, "Failed to get user details"
    print(f"   Got user: {user.get('email', 'N/A')}")

    # Update user name
    update = sdk.update_user(first_name="Test", last_name="Updated")
    assert update is not None, "Failed to update user"
    print(f"   Updated user name")

    return True


def test_get_providers():
    """Test getting providers (should work for all roles)"""
    sdk = ctx.current_user.sdk

    providers = sdk.get_providers()
    assert providers is not None, "Failed to get providers"
    print(
        f"   Got {len(providers) if isinstance(providers, list) else 'N/A'} providers"
    )

    return True


def test_get_agents():
    """Test getting agents list (should work for all roles with agents:read)"""
    sdk = ctx.current_user.sdk

    agents = sdk.get_agents()
    assert agents is not None, "Failed to get agents"
    print(f"   Got {len(agents)} agents")

    return agents


def test_create_agent():
    """Test creating an agent (admin only - requires agents:write)"""
    sdk = ctx.current_user.sdk
    role = ctx.current_user.role_name
    agent_name = f"test_agent_{role}_{random_string}"

    response = sdk.add_agent(
        agent_name=agent_name,
        settings={
            "mode": "prompt",
            "prompt_category": "Default",
            "prompt_name": "Think About It",
            "persona": "",
        },
    )

    agent_id = response.get("id") or response.get("agent_id")
    assert agent_id, f"Failed to create agent, response: {response}"

    # Store the agent info in the user context
    ctx.current_user.agent_id = agent_id
    ctx.current_user.agent_name = agent_name

    print(f"   Created agent: {agent_name} (id: {agent_id})")
    return agent_id


def test_rename_agent():
    """Test renaming an agent (admin only - requires agents:write)"""
    sdk = ctx.current_user.sdk
    agent_id = ctx.current_user.agent_id

    if not agent_id:
        raise Exception("No agent to rename - create_agent must run first")

    new_name = f"renamed_{ctx.current_user.agent_name}"
    response = sdk.rename_agent(agent_id=agent_id, new_name=new_name)

    ctx.current_user.agent_name = new_name
    print(f"   Renamed agent to: {new_name}")
    return response


def test_update_agent_settings():
    """Test updating agent settings (admin only - requires agents:write)"""
    sdk = ctx.current_user.sdk
    agent_id = ctx.current_user.agent_id

    if not agent_id:
        raise Exception("No agent to update - create_agent must run first")

    config = sdk.get_agentconfig(agent_id=agent_id)
    settings = config.get("settings", {})
    settings["AI_TEMPERATURE"] = 0.8

    response = sdk.update_agent_settings(agent_id=agent_id, settings=settings)
    print(f"   Updated agent settings")
    return response


def test_get_agent_config():
    """Test getting agent config (should work with agents:read)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available to get config")

    config = sdk.get_agentconfig(agent_id=agent_id)
    assert config is not None, "Failed to get agent config"
    print(
        f"   Got agent config with keys: {list(config.keys()) if isinstance(config, dict) else 'N/A'}"
    )
    return config


def test_create_conversation():
    """Test creating a conversation (should work for all roles with conversations:write)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available for conversation")

    conv_name = f"test_conv_{ctx.current_user.role_name}_{random_string}"
    response = sdk.new_conversation(agent_id=agent_id, conversation_name=conv_name)

    conv_id = response.get("id")
    assert conv_id, f"Failed to create conversation, response: {response}"

    print(f"   Created conversation: {conv_name} (id: {conv_id})")
    return conv_id


def test_get_conversations():
    """Test getting conversations (should work for all roles with conversations:read)"""
    sdk = ctx.current_user.sdk

    conversations = sdk.get_conversations()
    assert conversations is not None, "Failed to get conversations"
    print(f"   Got {len(conversations)} conversations")
    return conversations


def test_create_chain():
    """Test creating a chain (admin only - requires chains:write)"""
    sdk = ctx.current_user.sdk
    chain_name = f"test_chain_{ctx.current_user.role_name}_{random_string}"

    response = sdk.add_chain(chain_name=chain_name)

    chain_id = response.get("id")
    assert chain_id, f"Failed to create chain, response: {response}"

    print(f"   Created chain: {chain_name} (id: {chain_id})")
    return chain_id


def test_get_chains():
    """Test getting chains (should work for all roles with chains:read)"""
    sdk = ctx.current_user.sdk

    chains = sdk.get_chains()
    assert chains is not None, "Failed to get chains"
    print(f"   Got {len(chains)} chains")
    return chains


def test_create_prompt():
    """Test creating a prompt (admin only - requires prompts:write)"""
    sdk = ctx.current_user.sdk
    prompt_name = f"test_prompt_{ctx.current_user.role_name}_{random_string}"

    response = sdk.add_prompt(
        prompt_name=prompt_name,
        prompt="This is a test prompt about {subject}",
        prompt_category="Default",
    )

    prompt_id = response.get("id")
    assert prompt_id, f"Failed to create prompt, response: {response}"

    print(f"   Created prompt: {prompt_name} (id: {prompt_id})")
    return prompt_id


def test_get_prompts():
    """Test getting prompts (should work for all roles with prompts:read)"""
    sdk = ctx.current_user.sdk

    prompts = sdk.get_prompts(prompt_category="Default")
    assert prompts is not None, "Failed to get prompts"
    print(f"   Got {len(prompts)} prompts in Default category")
    return prompts


def test_create_webhook():
    """Test creating an outgoing webhook (admin only - requires webhooks:write)"""
    sdk = ctx.current_user.sdk

    webhook_data = {
        "name": f"test_webhook_{ctx.current_user.role_name}_{random_string}",
        "description": "Test webhook for role validation",
        "target_url": "https://httpbin.org/post",
        "event_types": ["agent.created", "agent.deleted"],
        "active": True,
        "headers": {"Content-Type": "application/json"},
        "secret": "test-secret",
    }

    response = requests.post(
        f"{ctx.base_uri}/api/webhooks/outgoing",
        json=webhook_data,
        headers=sdk.headers,
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to create webhook: {response.status_code} - {response.text}"
        )

    webhook = response.json()
    print(f"   Created webhook: {webhook.get('name')} (id: {webhook.get('id')})")
    return webhook


def test_get_webhooks():
    """Test getting webhooks (should work for all roles with webhooks:read)"""
    sdk = ctx.current_user.sdk

    response = requests.get(
        f"{ctx.base_uri}/api/webhooks/outgoing",
        headers=sdk.headers,
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to get webhooks: {response.status_code} - {response.text}"
        )

    webhooks = response.json()
    print(f"   Got {len(webhooks)} webhooks")
    return webhooks


def test_delete_agent():
    """Test deleting an agent (admin only - requires agents:delete)"""
    sdk = ctx.current_user.sdk
    agent_id = ctx.current_user.agent_id

    if not agent_id:
        raise Exception("No agent to delete - create_agent must run first")

    response = sdk.delete_agent(agent_id=agent_id)

    ctx.current_user.agent_id = None
    ctx.current_user.agent_name = None

    print(f"   Deleted agent")
    return response


def test_invite_user():
    """Test inviting a user (admin only - requires users:write)"""
    sdk = ctx.current_user.sdk

    # Generate a random email for the invitation
    invite_email = f"invite_test_{random_string}_{ctx.current_user.role_name}@test.com"

    invitation_data = {
        "email": invite_email,
        "company_id": ctx.current_user.company_id,
        "role_id": 3,  # Invite as regular user
    }

    response = requests.post(
        f"{ctx.base_uri}/v1/invitations",
        json=invitation_data,
        headers=sdk.headers,
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to create invitation: {response.status_code} - {response.text}"
        )

    invitation = response.json()
    print(f"   Created invitation for: {invite_email}")
    return invitation


def test_execute_command():
    """Test executing an agent command (should work for all roles with extensions:execute)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available to execute command")

    try:
        response = sdk.execute_command(
            agent_id=agent_id,
            command_name="Write to File",
            command_args={
                "filename": f"test_{ctx.current_user.role_name}.txt",
                "text": "Test content",
            },
            conversation_id="",
        )
        print(f"   Executed command successfully")
        return response
    except Exception as e:
        # This command might not be enabled, which is okay
        if "not found" in str(e).lower() or "disabled" in str(e).lower():
            print(f"   Command not available (expected for some setups)")
            return None
        raise


def test_learn_text():
    """Test learning text (should work for all roles with memories:write)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available for learning")

    response = sdk.learn_text(
        agent_id=agent_id,
        user_input=f"What is the test for {ctx.current_user.role_name}?",
        text=f"This is test content learned by {ctx.current_user.role_name} role.",
        collection_number="0",
    )

    print(f"   Learned text successfully")
    return response


def test_get_memories():
    """Test getting agent memories (should work for all roles with memories:read)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available for getting memories")

    memories = sdk.get_agent_memories(
        agent_id=agent_id,
        user_input="test",
        limit=5,
        min_relevance_score=0.0,
        collection_number="0",
    )

    print(f"   Got {len(memories)} memories")
    return memories


def test_wipe_memories():
    """Test wiping agent memories (admin only - requires memories:delete or full control)"""
    sdk = ctx.current_user.sdk

    # Use admin's agent if regular user doesn't have one
    agent_id = ctx.current_user.agent_id or ctx.admin_user.agent_id

    if not agent_id:
        raise Exception("No agent available for wiping memories")

    response = sdk.wipe_agent_memories(agent_id=agent_id, collection_number="0")

    print(f"   Wiped agent memories")
    return response


# In[ ]:


# Run all tests for each role
def run_all_role_tests():
    """Run comprehensive tests for both admin and user roles"""

    # List of tests with their expected behavior for user role
    # (test_func, test_name, expected_to_fail_for_user)
    tests = [
        # Basic operations - should work for all roles
        (test_user_operations, "user_operations", False),
        (test_get_providers, "get_providers", False),
        (test_get_agents, "get_agents", False),
        (test_get_conversations, "get_conversations", False),
        (test_get_chains, "get_chains", False),
        (test_get_prompts, "get_prompts", False),
        # Agent operations
        (test_create_agent, "create_agent", True),  # Requires agents:write
        (test_get_agent_config, "get_agent_config", False),  # Requires agents:read
        (test_rename_agent, "rename_agent", True),  # Requires agents:write
        (
            test_update_agent_settings,
            "update_agent_settings",
            True,
        ),  # Requires agents:write
        # Conversation operations
        (
            test_create_conversation,
            "create_conversation",
            False,
        ),  # conversations:write is allowed
        # Chain operations
        (test_create_chain, "create_chain", True),  # Requires chains:write
        # Prompt operations
        (test_create_prompt, "create_prompt", True),  # Requires prompts:write
        # Webhook operations
        (test_create_webhook, "create_webhook", True),  # Requires webhooks:write
        (
            test_get_webhooks,
            "get_webhooks",
            True,
        ),  # Requires webhooks:read (user role doesn't have this)
        # User management
        (test_invite_user, "invite_user", True),  # Requires users:write
        # Extension/Command operations
        (
            test_execute_command,
            "execute_command",
            False,
        ),  # extensions:execute is allowed
        # Memory operations
        (test_learn_text, "learn_text", False),  # memories:write is allowed
        (test_get_memories, "get_memories", False),  # memories:read is allowed
        (
            test_wipe_memories,
            "wipe_memories",
            True,
        ),  # Requires memories:delete (not in user role)
        # Cleanup - run last
        (test_delete_agent, "delete_agent", True),  # Requires agents:delete
    ]

    # Test users to iterate through
    test_users = [ctx.admin_user]
    if ctx.regular_user:
        test_users.append(ctx.regular_user)
    else:
        print("⚠️ Regular user not available, only testing admin role")

    for user in test_users:
        ctx.set_current_user(user)

        # Update global references for backward compatibility
        global agixt, test_email
        agixt = user.sdk
        test_email = user.email

        # Update openai client
        openai.api_key = user.sdk.headers["Authorization"]

        print(f"\n📋 Running tests for {user.role_name} ({user.email})")
        print("-" * 60)

        for test_func, test_name, expected_to_fail_for_user in tests:
            run_test(test_name, test_func, expected_to_fail_for_user)

    # Print summary and return failure count
    return ctx.print_summary()


# Execute the dual-role test suite
test_failures = run_all_role_tests()


# In[ ]:


# ============================================
# CLEANUP
# ============================================

print("\n" + "=" * 60)
print("CLEANUP: Removing test resources")
print("=" * 60)

# Clean up any remaining test resources
for user in [ctx.admin_user, ctx.regular_user]:
    if user is None:
        continue

    # Delete any remaining agents created during tests
    if user.agent_id:
        try:
            user.sdk.delete_agent(agent_id=user.agent_id)
            print(f"✅ Deleted test agent for {user.role_name}")
        except Exception as e:
            print(f"⚠️ Could not delete agent for {user.role_name}: {e}")

# Clean up test webhooks
try:
    response = requests.get(
        f"{ctx.base_uri}/api/webhooks/outgoing",
        headers=ctx.admin_user.sdk.headers,
    )
    if response.status_code == 200:
        webhooks = response.json()
        for webhook in webhooks:
            if random_string in webhook.get("name", ""):
                requests.delete(
                    f"{ctx.base_uri}/api/webhooks/outgoing/{webhook['id']}",
                    headers=ctx.admin_user.sdk.headers,
                )
                print(f"✅ Deleted test webhook: {webhook['name']}")
except Exception as e:
    print(f"⚠️ Could not clean up webhooks: {e}")

print("\n✅ Cleanup complete")
print("=" * 60)

# Exit with appropriate code based on test results
import sys

if test_failures > 0:
    print(f"\n❌ Exiting with code 1 due to {test_failures} test failure(s)")
    sys.exit(1)
else:
    print("\n✅ All tests passed!")
    sys.exit(0)
