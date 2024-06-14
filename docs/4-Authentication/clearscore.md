# ClearScore Single Sign-On (SSO) Integration Documentation

This document details how to integrate ClearScore SSO into your application. It includes setup steps, environment variable configurations, and API requirements.

## Required Environment Variables

To use ClearScore SSO, you need to configure the following environment variables in your `.env` file:

- `CLEAR_SCORE_CLIENT_ID`: ClearScore OAuth client ID
- `CLEAR_SCORE_CLIENT_SECRET`: ClearScore OAuth client secret

## Acquiring ClearScore OAuth Credentials

1. **Register Your Application**: Visit the ClearScore API developer portal and register your application.
2. **Obtain Client Credentials**: After registration, you will receive a `Client ID` and `Client Secret`.
3. **Set Environment Variables**: Add the `CLEAR_SCORE_CLIENT_ID` and `CLEAR_SCORE_CLIENT_SECRET` values to your `.env` file in the following format:

```plaintext
CLEAR_SCORE_CLIENT_ID=your_clear_score_client_id
CLEAR_SCORE_CLIENT_SECRET=your_clear_score_client_secret
```

## Required APIs

To interact with ClearScore's OAuth and email sending capabilities, ensure your application requests the following scopes:

- `user.info.read`
- `email.send`

## Scope Descriptions

- **`user.info.read`**: Allows reading of user profile information.
- **`email.send`**: Allows sending emails on behalf of the user.
