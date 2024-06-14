# Imgur SSO Integration Documentation

This documentation provides details on setting up and using the Imgur Single Sign-On (SSO) integration. The Imgur SSO integration allows users to authenticate and interact with Imgur's API for actions like uploading images and retrieving user information.

## Required Environment Variables

To use the Imgur SSO functionality, you'll need to set the following environment variables:

- `IMGUR_CLIENT_ID`: Imgur OAuth client ID
- `IMGUR_CLIENT_SECRET`: Imgur OAuth client secret

## Steps to Acquire Required Keys

1. **Create an Imgur Application:**
   - Go to the [Imgur API Applications page](https://api.imgur.com/oauth2/addclient).
   - Log in with your Imgur account.
   - Fill out the required fields to register a new application. You'll need to provide:
     - **Application Name**: Choose a name for your application.
     - **Authorization Type**: Select `OAuth 2 authorization with a callback URL`.
     - **Authorization callback URL**: Enter the URL where you want users to be redirected after authorization (e.g., `http://localhost:3000/callback`).
   - After submitting the form, you will receive the `Client ID` and `Client Secret`. These values are required for environment variables.

2. **Set Environment Variables:**
   - Add the obtained `Client ID` and `Client Secret` to your environment configuration file (e.g., `.env` file).

     ```plaintext
     IMGUR_CLIENT_ID=your_imgur_client_id
     IMGUR_CLIENT_SECRET=your_imgur_client_secret
     ```

## Required Scopes for Imgur SSO

To enable the required functionalities, ensure that your application requests the following scopes when users authenticate:

- `read`: Allows reading user data and images.
- `write`: Allows uploading images and other write operations.
