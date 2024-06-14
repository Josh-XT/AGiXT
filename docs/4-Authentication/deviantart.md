# DeviantArt SSO Integration Guide

This guide will help you set up and integrate deviantART Single Sign-On (SSO) using OAuth2 in your application. Please follow the steps carefully to ensure seamless integration.

## Required Environment Variables

To start using deviantART SSO, you need to set up the following environment variables in your environment. You can add these variables to your `.env` file:

- `DEVIANTART_CLIENT_ID`: deviantART OAuth client ID
- `DEVIANTART_CLIENT_SECRET`: deviantART OAuth client secret

## How to Acquire deviantART Client ID and Client Secret

1. **Register your Application**:
   - Log in to your deviantART account.
   - Navigate to the [deviantART OAuth2 Application Registration page](https://www.deviantart.com/settings/applications).
   - Click on "Register a new application" to create a new application.
   - Fill out the necessary details such as application name, description, and set the redirect URI (e.g., `http://localhost:8000/callback` for local testing).

2. **Retrieve Client ID and Client Secret**:
   - After successfully registering your application, you will be provided with a `Client ID` and `Client Secret`.
   - Store these credentials in a safe place.
   - Add them to your `.env` file as follows:

     ```env
     DEVIANTART_CLIENT_ID=your_client_id
     DEVIANTART_CLIENT_SECRET=your_client_secret
     ```

### Required OAuth Scopes for deviantART

The following OAuth scopes are required for deviantART SSO to work properly:

- `user`
- `browse`
- `stash`
- `send_message`

These scopes allow the application to access user information, browse deviantART content, access stash, and send messages on behalf of the user.
