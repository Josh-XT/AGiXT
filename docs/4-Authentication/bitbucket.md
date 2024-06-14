# Bitbucket SSO Integration

The `BitbucketSSO` class facilitates Single Sign-On (SSO) via Bitbucket. This integration enables your application to authenticate users with their Bitbucket accounts, providing an easy way for users to log in without creating a new account on your platform.

## Required Environment Variables

To set up Bitbucket SSO, you need to obtain and set the following environment variables:

- `BITBUCKET_CLIENT_ID`: Bitbucket OAuth client ID
- `BITBUCKET_CLIENT_SECRET`: Bitbucket OAuth client secret

## Step-by-Step Guide

### 1. Register Your Application on Bitbucket

1. Visit the Bitbucket developer portal: [Bitbucket OAuth Settings](https://bitbucket.org/account/settings/app-passwords/).
2. Log in with your Bitbucket account.
3. Navigate to "OAuth" under "Access Management."
4. Click on "Add consumer."
5. Fill in the required details:
    - **Name**: A name for your application.
    - **Description**: A brief description of what the application does.
    - **Callback URL**: The URL to which Bitbucket will send users after they authorize.
6. Select the necessary scopes for your application. For Bitbucket SSO, you need at least:
    - `account`
    - `email`
7. Save the consumer to get the Client ID and Client Secret.

### 2. Set Environment Variables

Add the obtained credentials to your `.env` file:

```env
BITBUCKET_CLIENT_ID=your_bitbucket_client_id
BITBUCKET_CLIENT_SECRET=your_bitbucket_client_secret
```

### 3. Required Scopes for Bitbucket SSO

Ensure that you request the following scopes when redirecting users for authentication:

- `account`
- `email`
