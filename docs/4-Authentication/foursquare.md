# Foursquare SSO Integration

The following documentation will guide you through the steps necessary to set up and use Foursquare Single Sign-On (SSO) in your application.

## Required Environment Variables

Before you start, you need to have the following environment variables set in your `.env` file:

- `FOURSQUARE_CLIENT_ID`: Your Foursquare OAuth client ID.
- `FOURSQUARE_CLIENT_SECRET`: Your Foursquare OAuth client secret.

## Steps to Acquire Foursquare OAuth Credentials

To obtain the `FOURSQUARE_CLIENT_ID` and `FOURSQUARE_CLIENT_SECRET`, follow these steps:

1. **Create a Foursquare Developer Account:**
   - Go to the [Foursquare Developer Portal](https://developer.foursquare.com/).
   - Sign up or log in to your Foursquare account.

2. **Create a New App:**
   - Once logged in, go to the "My Apps" section.
   - Click on "Create a New App".
   - Fill in the required details about your application.
   - After filling in the details, submit the form to create the app.

3. **Retrieve Your Credentials:**
   - After creating the app, you will be taken to your app's details page.
   - Your `Client ID` and `Client Secret` will be displayed on this page. These are the values you need to add to your `.env` file.

## Required APIs

The basic Foursquare API does not require any specific scopes for accessing basic user information. Foursquare uses a userless access approach for its APIs.

## How to Set Up Foursquare SSO

Add the `FOURSQUARE_CLIENT_ID` and `FOURSQUARE_CLIENT_SECRET` environment variables to your `.env` file:

```env
FOURSQUARE_CLIENT_ID=your-client-id
FOURSQUARE_CLIENT_SECRET=your-client-secret
```
