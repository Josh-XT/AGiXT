# Withings SSO Integration

This document provides detailed instructions on how to configure and use Withings Single Sign-On (SSO) for authenticating users and accessing user data using OAuth.

## Required Environment Variables

To set up Withings SSO, you need the following environment variables. Ensure you add these to your `.env` file.

- `WITHINGS_CLIENT_ID`: Withings OAuth client ID
- `WITHINGS_CLIENT_SECRET`: Withings OAuth client secret

### Steps to Acquire Withings Client ID and Secret

1. **Register your application with Withings**:
   - Visit the [Withings Developer Portal](https://developer.withings.com/).
   - Log in or sign up if you don't already have an account.
   - Create a new application under your account.
   - Fill in the required details such as application name, description, and redirect URIs.

2. **Generate the Client ID and Secret**:
   - Once your application is created, navigate to the application details page.
   - You will find the `Client ID` and `Client Secret` here. Copy these values to your `.env` file.

```plaintext
WITHINGS_CLIENT_ID=your_withings_client_id
WITHINGS_CLIENT_SECRET=your_withings_client_secret
```

## Required Scopes for Withings SSO

When configuring the Withings SSO, make sure to request the following scopes. These scopes ensure that your application has the necessary permissions to access user information and metrics.

- `user.info`: Access basic user information.
- `user.metrics`: Access user's health metrics.
- `user.activity`: Access user's activity data.
