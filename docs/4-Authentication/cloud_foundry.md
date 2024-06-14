# Cloud Foundry Single Sign-On (SSO) Integration

This document describes how to set up and use Cloud Foundry SSO in your application. Follow the steps below to configure the integration, acquire the necessary keys, and set up your environment.

## Required Environment Variables

- `CF_CLIENT_ID`: Cloud Foundry OAuth client ID
- `CF_CLIENT_SECRET`: Cloud Foundry OAuth client secret

## Required APIs and Scopes

You need to enable the following APIs and ensure the appropriate scopes are configured.

- **Cloud Foundry API (CF API)**
- **User Info API**

### Steps to Acquire Required Keys

1. **Log in to your Cloud Foundry Account:**  
   Go to your Cloud Foundry provider�s management console and log in using your credentials.

2. **Register an Application:**  
   Navigate to the OAuth Applications section. Create a new OAuth application.

3. **Obtain Client ID and Client Secret:**  
   Once the application is created, you will receive a `CLIENT_ID` and `CLIENT_SECRET`. Make a note of these values as you will need to set them as environment variables.

4. **Set up Redirect URIs:**  
   Specify the redirect URIs required for your application. These should point to the appropriate endpoints in your application handling OAuth redirects.

5. **Enable CF OAuth and User Info API:**  
   Ensure that the Cloud Foundry OAuth and User Info APIs are enabled for your account or organization. This often involves checking specific settings in the Cloud Foundry management console.

## Required Scopes for Cloud Foundry SSO

Ensure that the following OAuth scopes are included in your application's authorization request:

- `openid`
- `profile`
- `email`

## Setting Up Environment Variables

After acquiring the necessary credentials, set up your environment variables. Add the following lines to your application's `.env` file:

```env
CF_CLIENT_ID=YOUR_CLOUD_FOUNDRY_CLIENT_ID
CF_CLIENT_SECRET=YOUR_CLOUD_FOUNDRY_CLIENT_SECRET
```

Replace `YOUR_CLOUD_FOUNDRY_CLIENT_ID`, `YOUR_CLOUD_FOUNDRY_CLIENT_SECRET`, and `YOUR_APPLICATION_REDIRECT_URI` with the actual values you obtained during the setup process.
