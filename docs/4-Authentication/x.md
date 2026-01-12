````markdown
# X (Twitter) Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using X (formerly Twitter) OAuth2, allowing users to authenticate through their X accounts and access X API features including tweets, direct messages, and user interactions.

## Required Environment Variables

To use the X SSO integration, you need to set up the following environment variables:

- `X_CLIENT_ID`: X OAuth client ID
- `X_CLIENT_SECRET`: X OAuth client secret

## Setting Up X SSO

### Step 1: Create an X Developer Account

1. Go to the [X Developer Portal](https://developer.twitter.com/en/portal/dashboard).
2. Sign up for a developer account if you don't have one.
3. Complete the application process (may require approval).

### Step 2: Create a Project and App

1. In the Developer Portal, create a new **Project**.
2. Within the project, create a new **App**.
3. Select the appropriate access level for your use case.

### Step 3: Configure OAuth 2.0 Settings

1. Navigate to your app's settings.
2. Under **User authentication settings**, click **Set up**.
3. Enable **OAuth 2.0**.
4. Set **Type of App** to "Web App" or appropriate type.
5. Add your **Callback URI / Redirect URL**. This should match your `APP_URI` environment variable plus `/user/close/x` (e.g., `http://localhost:3437/user/close/x`).
6. Add a **Website URL** for your application.
7. Save your settings.

### Step 4: Get Client Credentials

1. In your app's **Keys and tokens** section, find your **OAuth 2.0 Client ID and Client Secret**.
2. Generate or regenerate secrets if needed.
3. Store these values securely.

### Step 5: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
X_CLIENT_ID=your_client_id
X_CLIENT_SECRET=your_client_secret
```

## Required Scopes for X OAuth

The X integration requests the following scopes:

- `tweet.read`: Read tweets
- `tweet.write`: Create and delete tweets
- `users.read`: Read user profile information
- `users.email`: Access user email (if available)
- `offline.access`: Refresh tokens for long-lived access
- `like.read`: Read liked tweets
- `like.write`: Like and unlike tweets
- `follows.read`: Read following/followers lists
- `follows.write`: Follow and unfollow users
- `dm.read`: Read direct messages
- `dm.write`: Send direct messages

## PKCE Requirement

X OAuth2 requires **PKCE (Proof Key for Code Exchange)** for enhanced security. This is handled automatically by AGiXT.

## Features

Once authenticated, the X extension provides:

- Tweet creation and management
- Timeline reading
- Direct message sending and reading
- Like and retweet functionality
- Following/follower management
- User profile access
````
