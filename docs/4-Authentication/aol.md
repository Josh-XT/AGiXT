# AOL SSO Integration Documentation

This documentation guides you through setting up Single Sign-On (SSO) integration with AOL using OAuth. The OAuth tokens allow you to fetch user information and send emails on behalf of the user. Please note that the endpoints and scopes used in this example are hypothetical and may not reflect the actual endpoints provided by AOL.

## Required Environment Variables

To use AOL SSO, you need to provide specific environment variables. These are necessary for the OAuth client to function correctly.

- `AOL_CLIENT_ID`: Your AOL OAuth client ID.
- `AOL_CLIENT_SECRET`: Your AOL OAuth client secret.

Ensure these variables are set in your environment.

## Steps to Set Up AOL SSO Integration

1. **Acquire OAuth Client ID and Secret**

    - Visit the AOL Developer website and log in to your account.
    - Navigate to the OAuth section and create a new OAuth application.
    - Note down the `AOL_CLIENT_ID` and `AOL_CLIENT_SECRET` provided by AOL.
    - Make sure to enable the following scopes for your application:
        - `https://api.aol.com/userinfo.profile`
        - `https://api.aol.com/userinfo.email`
        - `https://api.aol.com/mail.send`

2. **Set the Environment Variables**

    Add the acquired client ID and secret to your environment. This could be done by adding them to a `.env` file in the root of your project:

    ```plaintext
    AOL_CLIENT_ID=your_aol_client_id_here
    AOL_CLIENT_SECRET=your_aol_client_secret_here
    ```
