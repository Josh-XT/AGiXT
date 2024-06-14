# Autodesk Single Sign-On (SSO) using OAuth

The `AutodeskSSO` class provides a way to authenticate Autodesk users and retrieve their profile information from Autodesk's API. This guide describes how to configure and use the Autodesk SSO mechanism in your application.

## Required Environment Variables

To use Autodesk SSO in your project, you need to set up the Autodesk OAuth client credentials:

- `AUTODESK_CLIENT_ID`: This is the client ID obtained from Autodesk when you create an OAuth application.
- `AUTODESK_CLIENT_SECRET`: This is the client secret obtained from Autodesk.

## Steps to Obtain the Autodesk Client ID and Secret

1. **Register your application**:
    - Go to the [Autodesk Developer Portal](https://forge.autodesk.com).
    - Sign in with your Autodesk account.
    - Navigate to **My Apps**.
    - Click **Create App**.
    - Fill out the form with the necessary details and submit.
    - Once the application is created, you will receive the `Client ID` and `Client Secret`.

2. **Add Environment Variables**:
    - Create or update your `.env` file to include:

    ```env
    AUTODESK_CLIENT_ID=your_client_id_here
    AUTODESK_CLIENT_SECRET=your_client_secret_here
    ```

### Required APIs

Ensure you have the following APIs enabled in your Autodesk Developer account:

1. Click the links below to confirm you have enabled the APIs required for Autodesk's OAuth process:
    - [Data Management API](https://forge.autodesk.com/en/docs/data/v2/developers_guide/overview/)
    - [User Profile API](https://forge.autodesk.com/en/docs/oauth/v2/developers_guide/scopes/)

### Required Scopes for Autodesk OAuth

When setting up OAuth, the following scopes should be included:

- `data:read`
- `data:write`
- `bucket:read`
- `bucket:create`
