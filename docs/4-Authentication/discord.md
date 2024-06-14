# Discord Single Sign-On (SSO)

## Overview

This module allows you to integrate Discord's OAuth2 functionality into your application, enabling Single Sign-On using Discord credentials. This can be useful for authentication and fetching user information such as their Discord username, discriminator, and email.

## Required Environment Variables

To use the Discord SSO functionality, you need to create a Discord application and obtain the necessary credentials. The required environment variables are:

- `DISCORD_CLIENT_ID`: Discord OAuth client ID
- `DISCORD_CLIENT_SECRET`: Discord OAuth client secret

These variables should be added to your `.env` file for ease of use and security.

### How to Obtain DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET

1. **Log in to the Discord Developer Portal:**
   Go to the [Discord Developer Portal](https://discord.com/developers/applications) and log in with your Discord account.

2. **Create a New Application:**
   - Click on the "New Application" button.
   - Provide a name for your application and click "Create".

3. **Set Up OAuth2:**
   - Navigate to the "OAuth2" tab in your application's settings.
   - Under the "OAuth2" section, you will see your `CLIENT_ID` and `CLIENT_SECRET`. Copy these values.

4. **Enable OAuth2 Scopes:**
   - Scroll down to the "OAuth2 URL Generator" section.
   - Select the `email` scope to ensure you have permission to access the user's email.

5. **Add Credentials to Your `.env` File:**

   ```env
   DISCORD_CLIENT_ID=your_client_id_here
   DISCORD_CLIENT_SECRET=your_client_secret_here
   ```

### Required APIs and Scopes

Make sure you have the following scopes set up for your Discord application:

- `email` (Refer to the [Discord OAuth2 Scopes Documentation](https://discord.com/developers/docs/topics/oauth2#shared-resources-oauth2-scopes))
