````markdown
# Discord Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Discord OAuth2, allowing users to authenticate through their Discord accounts and access Discord API features including guilds and user information.

## Required Environment Variables

To use the Discord SSO integration, you need to set up the following environment variables:

- `DISCORD_CLIENT_ID`: Discord OAuth client ID
- `DISCORD_CLIENT_SECRET`: Discord OAuth client secret

## Setting Up Discord SSO

### Step 1: Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**.
3. Enter a name for your application and click **Create**.

### Step 2: Configure OAuth2 Settings

1. In your application's settings, navigate to **OAuth2** in the left sidebar.
2. Under **Redirects**, add your redirect URI. This should match your `APP_URI` environment variable plus `/user/close/discord` (e.g., `http://localhost:3437/user/close/discord`).
3. Save your changes.

### Step 3: Get Client Credentials

1. In the **OAuth2** section, you'll find your **Client ID**.
2. Click **Reset Secret** to generate a new **Client Secret** (store it securely as it won't be shown again).

### Step 4: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
```

## Required Scopes for Discord OAuth

The Discord integration requests the following scopes:

- `identify`: Access user's basic info (username, avatar, discriminator)
- `email`: Access user's email address
- `guilds`: Access list of guilds (servers) the user is in

These scopes allow your application to authenticate users and access their Discord profile information.

## Features

Once authenticated, the Discord extension provides:

- User profile information retrieval
- Guild (server) listing
- Channel access within guilds
- Message sending capabilities
- Server management (if bot permissions are configured)
````
