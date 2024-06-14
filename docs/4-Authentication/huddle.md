# Huddle SSO

This module facilitates Single Sign-On (SSO) with Huddle and provides functionalities to retrieve user information and send emails via Huddle's API.

## Required Environment Variables

To utilize the Huddle SSO functionalities in this module, you need to set up the following environment variables in your `.env` file:

- `HUDDLE_CLIENT_ID`: Huddle OAuth client ID
- `HUDDLE_CLIENT_SECRET`: Huddle OAuth client secret

### How to Acquire the Required Keys

1. **Create a Huddle App:**
   - Visit the Huddle Developer Portal [Huddle Dev Portal](https://www.huddle.com/developers/).
   - Log in with your Huddle account.
   - Navigate to the 'Apps' section and create a new application.
   - Fill in the necessary details, including redirect URI and scopes.
   - Upon creation, you will be provided with a `Client ID` and a `Client Secret`.

2. **Add Keys to `.env` File:**
   - Open your `.env` file in the root of your project.
   - Add the following lines:

     ```env
     HUDDLE_CLIENT_ID=your_client_id_here
     HUDDLE_CLIENT_SECRET=your_client_secret_here
     ```

## Required APIs

Ensure you have the necessary Huddle APIs enabled:

- Make sure your created application in the Huddle Developer Portal has permissions for the required scopes listed below.

## Required Scopes for Huddle OAuth

Generate access tokens with the following scopes:

- `user_info`
- `send_email`
