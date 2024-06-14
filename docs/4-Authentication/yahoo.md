# Yahoo SSO

The `YahooSSO` class and the `yahoo_sso` function facilitate Single Sign-On (SSO) with Yahoo, allowing you to retrieve user information (email, first name, last name) and send emails through Yahoo's mail services. Yahoo SSO requires specific OAuth credentials and certain API permissions to function properly.

## Required Environment Variables

To configure Yahoo SSO, you need to set the following environment variables. Add them to your `.env` file:

- `YAHOO_CLIENT_ID`: Yahoo OAuth client ID
- `YAHOO_CLIENT_SECRET`: Yahoo OAuth client secret

## Acquiring Yahoo OAuth Credentials

1. **Create a Yahoo Developer Account:**
   - Go to the [Yahoo Developer Network](https://developer.yahoo.com).
   - Sign in with your Yahoo account or create a new one.

2. **Create an App and Obtain Client ID and Secret:**
   - Navigate to the [Yahoo Developer Dashboard](https://developer.yahoo.com/apps/).
   - Click on "Create an App".
   - Fill in the required details such as application name, description, and Redirect URI.
   - Select the required permissions: `profile`, `email`, and `mail-w`.
   - After creating the app, you will be provided with the `Client ID` and `Client Secret`. Note these down as you'll need to add them to your environment variables.
  
3. **Add Redirect URI:**
   - Ensure that you have specified a valid Redirect URI in your app settings. This URI is where Yahoo will redirect users after authentication with the authorization code.
   - Example Redirect URI: `https://yourdomain.com/oauth/callback/yahoo`.

## Required APIs and Scopes

Ensure that your Yahoo app has the following scopes enabled:

- `profile`
- `email`
- `mail-w`

These scopes allow your application to view user profiles, retrieve email addresses, and send emails.

## Setting Up Your Environment Variables

Add the following lines to your `.env` file:

```plaintext
YAHOO_CLIENT_ID=your_yahoo_client_id
YAHOO_CLIENT_SECRET=your_yahoo_client_secret
```

Replace `your_yahoo_client_id` and `your_yahoo_client_secret` with the credentials you obtained from the Yahoo Developer Dashboard. Set `MAGIC_LINK_URL` to your application's redirect URI.
