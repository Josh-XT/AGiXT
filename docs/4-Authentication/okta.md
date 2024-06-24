# Okta SSO Setup and Usage

This section provides detailed documentation on setting up and using Okta Single Sign-On (SSO) in your project. By following these steps, you will be able to authenticate users using Okta and retrieve their user information.

## Required Environment Variables

Before you begin, ensure you have the following environment variables set up in your `.env` file:

- `OKTA_CLIENT_ID`: Okta OAuth client ID
- `OKTA_CLIENT_SECRET`: Okta OAuth client secret
- `OKTA_DOMAIN`: Okta domain (e.g., dev-123456.okta.com)

## Required OAuth Scopes

Ensure that your Okta OAuth application has the following scopes enabled:

- `openid`
- `profile`
- `email`

## Setting Up

### Step 1: Creating an Okta Application

1. Log in to your Okta Developer account at [developer.okta.com](https://developer.okta.com/).
2. From the dashboard, navigate to **Applications** -> **Applications**.
3. Click on **Create App Integration**.
4. Select **OAuth 2.0 / OIDC**, then click **Next**.
5. Choose **Web Application** and configure the following settings:
    - **Sign-in redirect URIs**: Add the callback URI of your application (e.g., `http://localhost:8000/callback`)
    - **Sign-out redirect URIs**: Optionally, add a sign-out URI.
6. Click **Save**.

### Step 2: Retrieving Your Okta Client ID and Client Secret

1. After saving the application, you will be redirected to the application settings page.
2. Scroll down to the **Client Credentials** section.
3. Copy the **Client ID** and **Client Secret** and add them to your `.env` file:

    ```plaintext
    OKTA_CLIENT_ID=your_client_id
    OKTA_CLIENT_SECRET=your_client_secret
    ```

### Step 3: Configuring Your Okta Domain

1. In the Okta dashboard, navigate to **Settings** -> **Customizations** -> **Domain**.
2. Copy your Okta domain (e.g., `dev-123456.okta.com`) and add it to your `.env` file:

    ```plaintext
    OKTA_DOMAIN=your_okta_domain
    ```
