````markdown
# Amazon Alexa Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Amazon's Login with Amazon (LWA) OAuth, specifically for Alexa Skills and smart home integrations. This extends the base Amazon SSO with Alexa-specific capabilities.

## Required Environment Variables

To use the Alexa SSO integration, you need to set up the following environment variables:

- `ALEXA_CLIENT_ID`: Amazon OAuth client ID (from Alexa Developer Console)
- `ALEXA_CLIENT_SECRET`: Amazon OAuth client secret

## Setting Up Alexa SSO

### Step 1: Create an Alexa Skill

1. Go to the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click **Create Skill**.
3. Choose your skill type and model.
4. Complete the skill setup.

### Step 2: Configure Account Linking

1. In your skill's settings, navigate to **Account Linking**.
2. Enable account linking.
3. Set the **Authorization URI** for your OAuth provider.
4. Set the **Access Token URI**.
5. Add your **Client ID** and **Client Secret**.
6. Configure the redirect URLs provided by Amazon.

### Step 3: Configure Login with Amazon

1. Go to [Login with Amazon Console](https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html).
2. Create a new security profile or use an existing one.
3. Under **Web Settings**, add your allowed return URLs.
4. Note your **Client ID** and **Client Secret**.

### Step 4: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
ALEXA_CLIENT_ID=your_client_id
ALEXA_CLIENT_SECRET=your_client_secret
```

## Required Scopes for Alexa OAuth

The Alexa integration may request the following scopes depending on features:

- `profile`: Basic profile information
- `profile:user_id`: Amazon user ID
- `alexa::skills:account_linking`: Account linking for skills
- `alexa::household:read`: Read household information
- `alexa::devices:all:address:full`: Full device address

## Features

Once authenticated, the Alexa extension provides:

- Smart home device control
- Skill invocation
- Voice command processing
- Routine management
- Notification sending
- Device discovery
- Household management

## Smart Home Integration

For smart home skills:

1. Implement the Smart Home Skill API
2. Handle discovery, control, and state report directives
3. Configure device capabilities

## Security Considerations

- Store tokens securely
- Implement token refresh for long-lived access
- Validate all incoming requests from Alexa
- Use HTTPS for all endpoints
````
