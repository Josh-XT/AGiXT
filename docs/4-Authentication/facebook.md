# Facebook

## Required Environment Variables

To integrate Facebook's OAuth into your application, you need to provide the following environment variables:

- `FACEBOOK_CLIENT_ID`: Facebook OAuth client ID
- `FACEBOOK_CLIENT_SECRET`: Facebook OAuth client secret

These values should be added to your `.env` file for secure and convenient access by your application.

## Steps to Obtain Facebook OAuth Credentials

1. **Create a Facebook App:**
   - Navigate to the [Facebook for Developers](https://developers.facebook.com/apps) page.
   - Click on "Create App" and select an appropriate app type.
   - Once created, go to your app's dashboard.

2. **Get the Client ID and Client Secret:**
   - In your app's dashboard, click on "Settings" and then "Basic."
   - Here, you will find your App ID (Client ID) and App Secret (Client Secret).

3. **Add these values to your .env File:**
   Create a `.env` file in your project root (if it doesn't already exist) and add the following lines:

   ```env
   FACEBOOK_CLIENT_ID=your_facebook_client_id
   FACEBOOK_CLIENT_SECRET=your_facebook_client_secret
   ```

## Required Scopes for Facebook OAuth

To ensure proper integration and to access specific user data, the following scopes must be requested during the OAuth authorization process:

- `public_profile`
- `email`
- `pages_messaging` (for sending messages, if applicable)
