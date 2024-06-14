# Strava

## Required environment variables

To use the Strava SSO and activity creation functionality, you need to set the following environment variables in your `.env` file:

- `STRAVA_CLIENT_ID`: Strava OAuth client ID
- `STRAVA_CLIENT_SECRET`: Strava OAuth client secret

## How to Acquire Strava Client ID and Client Secret

1. **Create a Strava Developer Account**:
   - If you don�t already have a Strava account, you need to sign up for one at [Strava](https://www.strava.com/).

2. **Register Your Application**:
   - Go to [Strava Developers](https://developers.strava.com/).
   - Sign in with your Strava account if needed.
   - Navigate to the �Create & Manage Your App� section.
   - Click on "Create New App."
   - Fill in the required details such as Application Name, Category, Club, Website, Authorization Callback Domain, and Scope.
   - After creating the app, you will be provided with a `Client ID` and `Client Secret`.

3. **Set Environment Variables**:
   - Add the `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` to your `.env` file:

     ```dotenv
     STRAVA_CLIENT_ID=your_strava_client_id
     STRAVA_CLIENT_SECRET=your_strava_client_secret
     ```

## Required scopes for Strava OAuth

When setting up OAuth for your Strava application, ensure that the following scopes are enabled:

- `read`
- `activity:write`
