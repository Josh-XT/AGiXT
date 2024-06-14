# Intel Cloud Services

The `intel_cloud_services.py` script allows for the integration with Intel's OAuth services for Single Sign-On (SSO) and email sending capabilities through their API.

## Required Environment Variables

To use the Intel Cloud Services, you need to set up the following environment variables:

- `INTEL_CLIENT_ID`: Intel OAuth client ID
- `INTEL_CLIENT_SECRET`: Intel OAuth client secret

## How to Obtain the Required Environment Variables

### Step 1: Create an Intel Developer Account

1. Go to the [Intel Developer Zone](https://developer.intel.com).
2. Register for an account if you don't have one.
3. Log in to your Intel Developer account.

### Step 2: Create an Application

1. Navigate to the [Intel APIs](https://developer.intel.com/apis).
2. Create a new application and obtain its Client ID and Client Secret.
   - **Client ID**: This will be your `INTEL_CLIENT_ID`.
   - **Client Secret**: This will be your `INTEL_CLIENT_SECRET`.

### Step 3: Enable Required APIs

Make sure the following APIs are enabled for your application:

- User Info API
- Mail Send API

## Required Scopes for Intel SSO

The following scopes must be added to your OAuth application settings:

- `https://api.intel.com/userinfo.read`
- `https://api.intel.com/mail.send`

## Setting Up Your .env File

Add the acquired `INTEL_CLIENT_ID` and `INTEL_CLIENT_SECRET` to your `.env` file:

```plaintext
INTEL_CLIENT_ID=your_client_id_here
INTEL_CLIENT_SECRET=your_client_secret_here
```
