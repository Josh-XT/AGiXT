# Dropbox SSO Integration

This document describes how to integrate Dropbox Single Sign-On (SSO) with your application. By following these instructions, you will be able to allow users to authenticate with Dropbox and access their Dropbox account information and files.

## Required Environment Variables

Before you start, you need to obtain the necessary credentials and set up environment variables:

1. **DROPBOX_CLIENT_ID**: Your Dropbox OAuth client ID.
2. **DROPBOX_CLIENT_SECRET**: Your Dropbox OAuth client secret.

### Acquiring Dropbox OAuth Credentials

To obtain the necessary credentials from Dropbox:

1. **Create a Dropbox App**:
    - Visit the [Dropbox App Console](https://www.dropbox.com/developers/apps).
    - Click on "Create App".
    - Choose an API (Scoped access).
    - Select the type of access you need: "Full Dropbox" or "App Folder".
    - Name your app and click "Create App".

2. **Get Your App Credentials**:
   - Navigate to the "Settings" tab of your app in the Dropbox App Console.
   - You will find your `App key` (use this as `DROPBOX_CLIENT_ID`) and `App secret` (use this as `DROPBOX_CLIENT_SECRET`).

3. **Set the Redirect URI**:
   - In the "OAuth 2" section in the settings tab, add your redirect URI (e.g., `https://yourapp.com/auth/dropbox/callback`).

### Required Scopes for Dropbox OAuth

When setting up OAuth access, ensure that you enable the following scopes:

- `account_info.read`: Required to access user account information.
- `files.metadata.read`: Required to read the metadata for files in the user's Dropbox.

### Setting Environment Variables

Add the following environment variables to your `.env` file:

```env
DROPBOX_CLIENT_ID=your_dropbox_client_id
DROPBOX_CLIENT_SECRET=your_dropbox_client_secret
```
