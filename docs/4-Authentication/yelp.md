# Yelp SSO Integration

The Yelp SSO integration allows users to authenticate and retrieve user information through Yelp's OAuth system. This section provides a detailed guide on how to configure and use the Yelp SSO in your application.

## Required Environment Variables

This integration requires the following environment variables:

- `YELP_CLIENT_ID`: Yelp OAuth client ID
- `YELP_CLIENT_SECRET`: Yelp OAuth client secret

To set these variables, ensure they are included in your application's environment configuration file (e.g., `.env`):

```plaintext
YELP_CLIENT_ID=your_client_id_here
YELP_CLIENT_SECRET=your_client_secret_here
```

## Acquiring Client ID and Client Secret

To obtain the `YELP_CLIENT_ID` and `YELP_CLIENT_SECRET`, follow these steps:

1. **Register Your App:**
    - Go to the [Yelp Developer Portal](https://www.yelp.com/developers/v3/get_started).
    - Log in or create a Yelp account.
    - Navigate to the "Create App" section.
    - Fill out the required details to register your application.

2. **Retrieve Credentials:**
    - Once your application is registered, you will be provided with a `CLIENT_ID` and `CLIENT_SECRET`.

## Required Scopes

Ensure your application requests the necessary scopes for Yelp OAuth:

- `business`

These scopes allow the application to access specific user information and perform operations permitted by Yelp's API.
