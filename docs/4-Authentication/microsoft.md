# Microsoft Single Sign-On (SSO) Integration

## Overview

This module provides an integration with Microsoft's Single Sign-On (SSO) to allow your application to authenticate users through their Microsoft accounts and send emails using Microsoft's Graph API.

## Required Environment Variables

To use the Microsoft SSO integration, you'll need to set up the following environment variables:

- `MICROSOFT_CLIENT_ID`: Microsoft OAuth client ID
- `MICROSOFT_CLIENT_SECRET`: Microsoft OAuth client secret

These values can be obtained by registering your application in the Microsoft Azure portal.

## Setting Up Microsoft SSO

### Step 1: Register Your Application

1. Go to the [Azure portal](https://portal.azure.com/).
2. Select **Azure Active Directory**.
3. In the left-hand navigation pane, select **App registrations**.
4. Select **New registration**.
5. Enter a name for your application.
6. Under **Redirect URI**, enter a redirect URI where the authentication response can be sent. This should match the `APP_URI` environment variable in your `.env` file.
7. Click **Register**.

### Step 2: Configure API Permissions

1. Go to the **API permissions** section of your app's registration page.
2. Click on **Add a permission**.
3. Select **Microsoft Graph**.
4. Choose **Delegated permissions** and add the following permissions:
   - `User.Read`
   - `Mail.Send`
   - `Calendars.ReadWrite.Shared`

### Step 3: Obtain Client ID and Client Secret

1. In the **Overview** section of your app registration, you will find the **Application (client) ID**. This is your `MICROSOFT_CLIENT_ID`.
2. Go to the **Certificates & secrets** section.
3. Under **Client secrets**, click on **New client secret**.
4. Add a description and choose an expiry period. Click on **Add**.
5. Copy the value of the client secret. This is your `MICROSOFT_CLIENT_SECRET`. Be sure to store it securely.

### Step 4: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
```

## Required Scopes for Microsoft OAuth

- `https://graph.microsoft.com/User.Read`
- `https://graph.microsoft.com/Mail.Send`
- `https://graph.microsoft.com/Calendars.ReadWrite.Shared`

These scopes are requested when obtaining access tokens, allowing your application to read user profile information, send emails on behalf of the user, and access shared calendars.
