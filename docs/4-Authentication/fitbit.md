````markdown
# Fitbit Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Fitbit OAuth2, allowing users to authenticate through their Fitbit accounts and access health and fitness data including activity, sleep, heart rate, and nutrition information.

## Required Environment Variables

To use the Fitbit SSO integration, you need to set up the following environment variables:

- `FITBIT_CLIENT_ID`: Fitbit OAuth client ID
- `FITBIT_CLIENT_SECRET`: Fitbit OAuth client secret

## Setting Up Fitbit SSO

### Step 1: Create a Fitbit Developer Account

1. Go to [Fitbit Developer](https://dev.fitbit.com/).
2. Sign in with your Fitbit account or create one.
3. Accept the terms of service.

### Step 2: Register an Application

1. Navigate to **Manage** > **Register an App**.
2. Fill in the required information:
   - **Application Name**: Your application's name
   - **Description**: Brief description of your application
   - **Application Website**: Your application's website URL
   - **Organization**: Your organization name
   - **Organization Website**: Your organization's website
   - **Terms of Service URL**: Your terms of service URL
   - **Privacy Policy URL**: Your privacy policy URL
   - **OAuth 2.0 Application Type**: Select "Server" for web applications
3. Set the **Redirect URI**. This should match your `APP_URI` environment variable plus `/user/close/fitbit` (e.g., `http://localhost:3437/user/close/fitbit`).
4. Select the appropriate **Default Access Type** (Read-Only or Read & Write).
5. Click **Register**.

### Step 3: Get Client Credentials

1. After registration, you'll see your **OAuth 2.0 Client ID**.
2. Click **Manage** next to your app to view the **Client Secret**.
3. Store these values securely.

### Step 4: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
FITBIT_CLIENT_ID=your_client_id
FITBIT_CLIENT_SECRET=your_client_secret
```

## Required Scopes for Fitbit OAuth

The Fitbit integration requests the following scopes:

- `activity`: Activity logs and exercise data
- `heartrate`: Heart rate data and resting heart rate
- `location`: GPS and location data from exercises
- `nutrition`: Food logging and water intake
- `profile`: User profile information
- `settings`: User account settings
- `sleep`: Sleep logs and sleep stages
- `social`: Friends and leaderboard
- `weight`: Weight and body fat logs

## PKCE Requirement

Fitbit OAuth2 requires **PKCE (Proof Key for Code Exchange)** for enhanced security. This is handled automatically by AGiXT.

## Features

Once authenticated, the Fitbit extension provides:

- Activity tracking and step counts
- Heart rate monitoring and zones
- Sleep tracking and analysis
- Weight and body composition logs
- Nutrition and food logging
- Exercise and workout data
- Badges and achievements
- Device information
- Intraday data (with special approval)

## Rate Limits

Fitbit API has rate limits:

- **150 requests per hour** per user for most endpoints
- Some endpoints have lower limits

The extension handles rate limiting automatically with appropriate retry logic.
````
