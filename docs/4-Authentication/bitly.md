# Bitly Integration

The Bitly integration allows you to shorten URLs and manage Bitly tokens using the Bitly API.

## Required Environment Variables

- `BITLY_CLIENT_ID`: Bitly OAuth client ID
- `BITLY_CLIENT_SECRET`: Bitly OAuth client secret
- `BITLY_ACCESS_TOKEN`: Bitly access token (you can obtain it via OAuth or from the Bitly account settings)

## Required Scopes for Bitly OAuth

- `bitly:read`
- `bitly:write`

## How to Acquire Required Keys and Tokens

1. **Create a Bitly Account**:
   - Sign up for a Bitly account at <https://bitly.com/>.

2. **Create an OAuth App**:
   - Navigate to <https://app.bitly.com/settings/integrations/>.
   - Click on "Registered OAuth Apps" and then "Add a New App".
   - Fill in the required information to create a new app. The "App Name" and "App Description" can be anything, but for "Redirect URIs," you'll need to specify the URIs that Bitly will redirect to after authentication.
   - After creating the app, you will receive a `Client ID` and `Client Secret`.

3. **Generate an Access Token**:
   - You can generate an access token from your Bitly account settings.
   - Go to <https://app.bitly.com/settings/api/>, and click on "Generic Access Token" to create a new token.

4. **Set up Environment Variables**:
   - Add the following environment variables to your `.env` file:

     ```plaintext
     BITLY_CLIENT_ID=your_bitly_client_id
     BITLY_CLIENT_SECRET=your_bitly_client_secret
     BITLY_ACCESS_TOKEN=your_bitly_access_token
     ```
