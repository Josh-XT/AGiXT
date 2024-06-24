# Twitch

The integration for Twitch Single Sign-On (SSO) requires setting up environment variables and acquiring special identifiers and keys from the Twitch Developer Console. Below you'll find detailed instructions to guide you through the process.

## Required Environment Variables

Ensure the following environment variables are added to your `.env` file:

- `TWITCH_CLIENT_ID`: Your Twitch OAuth client ID
- `TWITCH_CLIENT_SECRET`: Your Twitch OAuth client secret

## Required Scope for Twitch OAuth

To successfully use Twitch SSO, the following OAuth scope must be enabled:

- `user:read:email`

## Instructions to Acquire Required Keys

1. **Create a Twitch Developer Account**
   - Navigate to [Twitch Developer Console](https://dev.twitch.tv/).
   - If you don't already have a developer account, you'll need to create one.

2. **Register Your Application**
   - Log in to the Twitch Developer Console.
   - Click on the "Your Console" tab.
   - Click on "Register Your Application".
   - Fill out the required details, including:
     - **Name**: Name your application.
     - **OAuth Redirect URLs**: Add the URLs that Twitch should redirect to after OAuth authentication.
     - **Category**: Select the category that best describes your application.

3. **Retrieve Your Client ID and Client Secret**
   - After registering, your application will be assigned a **Client ID** and a **Client Secret**.
   - Copy the Client ID to `TWITCH_CLIENT_ID` and the Client Secret to `TWITCH_CLIENT_SECRET` in your `.env` file.

## Summary

Your `.env` file should look something like this:

```dotenv
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
```

Replace `your_twitch_client_id` and `your_twitch_client_secret` with the actual values obtained from the Twitch Developer Console.
