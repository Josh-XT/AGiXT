# Xero SSO Integration Documentation

## Overview

This document describes how to integrate Xero Single Sign-On (SSO) using the provided `xero.py` script. The script leverages Xero's OAuth 2.0 for authentication and retrieving user information.

## Prerequisites

1. **Create a Xero App**:

   To start using Xero's SSO, you need to create an app in the Xero Developer portal:
   - Go to the [Xero Developer Portal](https://developer.xero.com/myapps).
   - Sign in with your Xero account.
   - Click on "New App" and fill in the necessary details.
     - Application name: Provide a name for your application.
     - Integration: Select the type of integration (e.g., Web application).
     - OAuth 2.0 redirect URI: Provide your application's redirect URL.
   - Once the app is created, you will get the `CLIENT_ID` and `CLIENT_SECRET`. These are necessary for the OAuth flow.

2. **Environment Variables**:

   The keys fetched from the Xero Developer Portal need to be saved as environment variables in your project.

   - `XERO_CLIENT_ID`: Xero OAuth client ID
   - `XERO_CLIENT_SECRET`: Xero OAuth client secret

   Add these to your `.env` file:

   ```plaintext
   XERO_CLIENT_ID=your_client_id_here
   XERO_CLIENT_SECRET=your_client_secret_here
   ```

## Required Scopes

When setting up OAuth access for Xero, ensure that you enable the following scopes:

- `offline_access`: Allows your application to access Xero data when the user is not present.
- `openid`: Provides basic user information.
- `profile`: Access to the user's profile information.
- `email`: Access to the user's email address.
