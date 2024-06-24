# Salesforce Single Sign-On (SSO)

## Overview

This module allows you to integrate Salesforce SSO into your application. By setting up the required environment variables and following the steps below, you can leverage Salesforce's OAuth capabilities for secure authentication and user information retrieval.

## Required Environment Variables

To integrate Salesforce SSO, you need to obtain the following environment variables:

- `SALESFORCE_CLIENT_ID`: Salesforce OAuth client ID
- `SALESFORCE_CLIENT_SECRET`: Salesforce OAuth client secret

### Steps to Acquire the Required Environment Variables

1. **Create a Connected App in Salesforce**:
    - Log in to your Salesforce account.
    - Navigate to `Setup` by clicking on the gear icon in the top-right corner.
    - In the Quick Find box, type `App Manager` and select it from the dropdown.
    - Click the `New Connected App` button.
    - Fill in the required fields:
        - **Connected App Name**: A unique name for your app.
        - **API Name**: This will auto-populate based on your app name.
        - **Contact Email**: Your email address.
    - In the **OAuth Settings** section:
        - Check the `Enable OAuth Settings` checkbox.
        - Enter the callback URL (e.g., `http://localhost:8000/callback`).
        - Select the following OAuth Scopes:
            - `Full access (full)`
            - `Perform requests on your behalf at any time (refresh_token, offline_access)`
            - `Access your basic information (id, profile, email, address, phone)`
    - Click the `Save` button.

2. **Retrieve Client ID and Client Secret**:
    - After saving, navigate back to `App Manager`.
    - Find your newly created app in the list and click on its name.
    - Under `API (Enable OAuth Settings)`, you'll find the `Consumer Key` (Client ID) and `Consumer Secret` (Client Secret).

3. **Add Environment Variables**:
    - Create a `.env` file in the root directory of your project if it doesn't already exist.
    - Add the following lines to the `.env` file, replacing the placeholders with your actual Consumer Key and Consumer Secret:

        ```env
        SALESFORCE_CLIENT_ID=your_salesforce_client_id
        SALESFORCE_CLIENT_SECRET=your_salesforce_client_secret
        ```

## Required Salesforce OAuth Scopes

Ensure your Salesforce Connected App has the following OAuth scopes enabled:

- `refresh_token`
- `full`
- `email`
