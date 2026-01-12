````markdown
# LinkedIn Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using LinkedIn OAuth2, allowing users to authenticate through their LinkedIn accounts and access LinkedIn API features including profile information, connections, and posting capabilities.

## Required Environment Variables

To use the LinkedIn SSO integration, you need to set up the following environment variables:

- `LINKEDIN_CLIENT_ID`: LinkedIn OAuth client ID
- `LINKEDIN_CLIENT_SECRET`: LinkedIn OAuth client secret

## Setting Up LinkedIn SSO

### Step 1: Create a LinkedIn Application

1. Go to [LinkedIn Developers](https://www.linkedin.com/developers/apps).
2. Click **Create App**.
3. Fill in the required information:
   - **App name**: Your application's name
   - **LinkedIn Page**: Associate with a LinkedIn Company Page (required)
   - **Privacy policy URL**: Your privacy policy URL
   - **App logo**: Upload your application logo
4. Click **Create app**.

### Step 2: Add Required Products

In your app dashboard, add the following products:

1. **Sign In with LinkedIn using OpenID Connect** - For basic authentication
2. **Share on LinkedIn** - For posting on behalf of users
3. **Marketing Developer Platform** - For company page access (requires approval)

### Step 3: Configure OAuth Settings

1. Navigate to the **Auth** tab in your app settings.
2. Under **OAuth 2.0 settings**, add your redirect URI. This should match your `APP_URI` environment variable plus `/user/close/linkedin` (e.g., `http://localhost:3437/user/close/linkedin`).
3. Save your changes.

### Step 4: Get Client Credentials

1. In the **Auth** tab, you'll find your **Client ID** and **Client Secret**.
2. Copy these values securely.

### Step 5: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
```

## Required Scopes for LinkedIn OAuth

The LinkedIn integration requests the following scopes:

- `openid`: For OpenID Connect sign-in
- `profile`: Basic profile information
- `email`: Email address access
- `w_member_social`: Post on behalf of user

### Additional Scopes (Requires Marketing Developer Platform Approval)

- `r_organization_social`: Read company pages
- `w_organization_social`: Post to company pages
- `r_1st_connections_size`: Connection count

## Important Notes

LinkedIn restricts certain APIs. Some features require partner program approval:

- **Messaging API**: Requires LinkedIn partnership
- **Full connections list**: Requires partnership
- **Company page posting**: Requires Marketing Developer Platform approval

## Features

Once authenticated, the LinkedIn extension provides:

- User profile information retrieval
- Post creation and sharing
- Company page management (with approval)
- Connection insights
- Profile analytics
````
