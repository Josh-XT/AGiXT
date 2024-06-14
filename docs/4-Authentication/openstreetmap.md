# OpenStreetMap SSO Integration

This guide explains how to integrate OpenStreetMap Single Sign-On (SSO) using OAuth. Follow the steps below to acquire the required keys and set up the necessary environment variables for OpenStreetMap SSO.

## Required Environment Variables

- `OSM_CLIENT_ID`: OpenStreetMap OAuth client ID
- `OSM_CLIENT_SECRET`: OpenStreetMap OAuth client secret

## Steps to Acquire OpenStreetMap OAuth Credentials

1. **Create an OpenStreetMap OAuth Application:**

   - Navigate to the [OpenStreetMap OAuth settings page](https://www.openstreetmap.org/user/{your_username}/oauth_clients).
   - Log in with your OpenStreetMap account if you are not already logged in.
   - Click on "Register your application".
   - Fill out the form with the required information:
     - **Name:** Give your application a name.
     - **Main Application URL:** Provide the URL where your application is hosted.
     - **Callback URL:** Provide the URL where the user will be redirected after authentication.
     - **Support URL:** Provide the URL for support.
   - Click the "Save" button.

2. **Save Your OAuth Credentials:**

   - After registering your application, you will be given a **client ID** and **client secret**. Keep these credentials safe.
   - Add them to your `.env` file as follows:

     ```env
     OSM_CLIENT_ID=your_openstreetmap_client_id
     OSM_CLIENT_SECRET=your_openstreetmap_client_secret
     ```

### Required APIs

Ensure you have the appropriate OAuth configuration in OpenStreetMap and that the `OSM_CLIENT_ID` and `OSM_CLIENT_SECRET` environment variables are properly set in your `.env` file.

### Required Scopes for OpenStreetMap OAuth

The required scope for OpenStreetMap OAuth integration is:

- `read_prefs`
