# Battle.net SSO Integration

This guide will help you set up Battle.net single sign-on (SSO) integration using OAuth2. Follow the instructions to acquire the necessary keys and configure your environment variables.

## Required Environment Variables

Before you begin, make sure to add the following environment variables to your `.env` file:

- `BATTLENET_CLIENT_ID`: Battle.net OAuth client ID
- `BATTLENET_CLIENT_SECRET`: Battle.net OAuth client secret

### Obtaining Battle.net Client ID and Client Secret

To get your Battle.net Client ID and Client Secret, follow these steps:

1. **Create a Battle.net Developer Account:**
   - Go to the [Battle.net Developer Portal](https://develop.battle.net/access/).
   - Sign in using your Battle.net account credentials.

2. **Create an Application:**
   - Navigate to the "Create Client" section and fill out the required details about your application.
   - After creating the application, you will be provided with a `Client ID` and `Client Secret`.

3. **Enable APIs:**
   - Ensure that the necessary APIs are enabled for your Battle.net application. This generally includes the OAuth2 authentication API.

4. **Add Redirect URI:**
   - Configure the redirect URI to match the URL where you want to receive the authorization code.

### Required Scopes for Battle.net OAuth

Ensure you request the following scopes when setting up your SSO integration:

- `openid`
- `email`

These scopes will grant your application access to basic Battle.net profile information and the user's email address.

### Environment Variables Configuration

After you have your `Client ID` and `Client Secret`, add them to your `.env` file like so:

```env
BATTLENET_CLIENT_ID=your_battlenet_client_id
BATTLENET_CLIENT_SECRET=your_battlenet_client_secret
```
