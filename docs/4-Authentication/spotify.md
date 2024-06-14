# Spotify SSO Integration Documentation

This document outlines the steps required to integrate Spotify Single Sign-On (SSO) into your application, including how to set up the necessary environment variables and acquire the necessary API keys.

## Required Environment Variables

To use Spotify SSO, you need to set the following environment variables:

1. `SPOTIFY_CLIENT_ID`: Your Spotify OAuth client ID.
2. `SPOTIFY_CLIENT_SECRET`: Your Spotify OAuth client secret.

Ensure you have set these variables in your `.env` file.

## Steps to Acquire Spotify Client ID and Client Secret

1. **Create a Spotify Developer Account**

   If you don't have a Spotify Developer account, create one by registering at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

2. **Create an App**

   Once you are logged in to the Spotify Developer Dashboard, create a new application:
   - Go to **Dashboard**.
   - Click on the **Create an App** button.
   - Fill out the **App Name** and **App Description** fields.
   - Check the **I understand and accept the Spotify Developer Terms of Service**.
   - Click **Create**.

3. **Retrieve Your Client ID and Client Secret**

   After creating the app, you will be redirected to your app's dashboard:
   - Find the **Client ID** and **Client Secret** on this page.
   - Add these values to your `.env` file as shown below:

     ```env
     SPOTIFY_CLIENT_ID=your-client-id
     SPOTIFY_CLIENT_SECRET=your-client-secret
     ```

## Required APIs and Scopes for Spotify SSO

You need to enable the necessary scopes to allow your application to access user data and functionalities:

- `user-read-email`: Allows reading user's email.
- `user-read-private`: Allows reading user's subscription details.
- `playlist-read-private`: Allows reading user's private playlists.
