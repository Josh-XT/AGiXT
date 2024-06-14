# Xing

The provided module allows for Single Sign-On (SSO) with Xing and includes the functionality to retrieve user information as well as send emails. Follow the steps below to set up and use the Xing SSO module.

## Required Environment Variables

To use the Xing SSO module, you need to set up two environment variables:

- `XING_CLIENT_ID`: Your Xing OAuth client ID
- `XING_CLIENT_SECRET`: Your Xing OAuth client secret

## Acquiring Environment Variables

1. **Xing OAuth Client ID and Client Secret**:
    - You will first need to create an application on [Xing Developer Portal](https://dev.xing.com/). Here�s how:
      1. Sign up or log into the [Xing Developer Portal](https://dev.xing.com/).
      2. Create a new application (you might have to complete some verification steps).
      3. Once your application is created, you will get access to the client ID and client secret.

2. **Setting Up Environment Variables**:
    - Add the `XING_CLIENT_ID` and `XING_CLIENT_SECRET` to your `.env` file:

      ```env
      XING_CLIENT_ID=your_xing_oauth_client_id
      XING_CLIENT_SECRET=your_xing_oauth_client_secret
      ```

## Required APIs

Ensure you have the following APIs enabled:

- [Xing API](https://dev.xing.com/)

## Required Scopes for Xing SSO

These are the API scopes required for Xing SSO:

- `https://api.xing.com/v1/users/me`
- `https://api.xing.com/v1/authorize`
