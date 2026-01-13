````markdown
# Garmin Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Garmin Connect OAuth 1.0a, allowing users to authenticate through their Garmin accounts and access fitness and health data from Garmin devices.

## Required Environment Variables

To use the Garmin SSO integration, you need to set up the following environment variables:

- `GARMIN_CLIENT_ID`: Garmin OAuth Consumer Key
- `GARMIN_CLIENT_SECRET`: Garmin OAuth Consumer Secret

## Setting Up Garmin SSO

### Step 1: Apply for Garmin Connect API Access

1. Go to the [Garmin Developer Portal](https://developer.garmin.com/).
2. Create a developer account if you don't have one.
3. Apply for **Health API** or **Connect IQ** access depending on your needs.
4. Note: Garmin API access requires approval and may take time.

### Step 2: Create an Application

1. Once approved, navigate to your developer dashboard.
2. Create a new application.
3. Fill in the required information:
   - **Application Name**: Your application's name
   - **Application Description**: Brief description
   - **Callback URL**: Your redirect URI

### Step 3: Configure OAuth Settings

1. Set your **Callback URL**. This should match your `APP_URI` environment variable plus `/user/close/garmin` (e.g., `http://localhost:3437/user/close/garmin`).
2. Note your **Consumer Key** and **Consumer Secret**.

### Step 4: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
GARMIN_CLIENT_ID=your_consumer_key
GARMIN_CLIENT_SECRET=your_consumer_secret
```

## OAuth 1.0a Note

Garmin Connect uses **OAuth 1.0a**, not OAuth 2.0. Key differences:

- Tokens don't typically expire (but can be revoked)
- No refresh token flow - re-authorization required if token becomes invalid
- Request signing is more complex (handled automatically by AGiXT)
- Requires `requests-oauthlib` package for OAuth 1.0a support

## Features

Once authenticated, the Garmin extension provides:

- Activity summaries and details
- Daily step counts
- Heart rate data
- Sleep tracking
- Stress levels
- Body composition
- Workout data
- Device information
- GPS tracks from activities

## API Access Levels

Garmin offers different API access levels:

- **Health API**: Access to user health and fitness data
- **Connect IQ**: For developing Garmin device apps
- **Wellness API**: Enterprise health solutions

The scopes available depend on your approved access level.

## Important Notes

1. **Token Persistence**: OAuth 1.0a tokens don't expire automatically, but store them securely as re-authorization is required if lost.

2. **Rate Limits**: Garmin API has rate limits. The extension handles these with appropriate retry logic.

3. **Data Availability**: Some data is only available after syncing from Garmin devices.
````
