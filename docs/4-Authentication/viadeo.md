# Viadeo

## Required environment variables

- `VIADEO_CLIENT_ID`: Viadeo OAuth client ID
- `VIADEO_CLIENT_SECRET`: Viadeo OAuth client secret

## Required APIs

Ensure you have the required APIs enabled, then add the `VIADEO_CLIENT_ID` and `VIADEO_CLIENT_SECRET` environment variables to your `.env` file.

To acquire the `VIADEO_CLIENT_ID` and `VIADEO_CLIENT_SECRET`, follow these steps:

1. **Creating an App on Viadeo:**
   - Navigate to the [Viadeo Developer Portal](https://developer.viadeo.com/).
   - Sign in with your Viadeo account.
   - Create a new application and provide the necessary details.
   - Upon creation, you will be issued a `Client ID` and `Client Secret`.

2. **Setting Up Environment Variables:**
   - After obtaining the `Client ID` and `Client Secret`, add these values to your `.env` file:

     ```plaintext
     VIADEO_CLIENT_ID=your_client_id_here
     VIADEO_CLIENT_SECRET=your_client_secret_here
     ```

### Required Scopes for Viadeo OAuth

- `basic` (to access user profile)
- `email` (to access user email)
