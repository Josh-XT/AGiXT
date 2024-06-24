# OpenAM SSO

## Overview

This module provides Single Sign-On (SSO) functionality using OpenAM's OAuth 2.0 service. It enables users to obtain tokens and user information from OpenAM, and also provides a mechanism for token refresh.

## Required Environment Variables

To use the OpenAM SSO module, you must set the following environment variables:

- `OPENAM_CLIENT_ID`: OpenAM OAuth client ID
- `OPENAM_CLIENT_SECRET`: OpenAM OAuth client secret
- `OPENAM_BASE_URL`: Base URL for the OpenAM server (e.g., `https://openam.example.com`)

## Required Scopes for OpenAM OAuth

The following scopes are required for OpenAM OAuth:

- `profile`
- `email`

## Instructions to Acquire Keys and Set Up Environment Variables

1. **Register the Client with OpenAM:**

   - **Navigate to Admin Console:** Log in to the OpenAM administrative console.
   - **Register the Application:**
     - Go to `Applications` > `Agents` > `OAuth 2.0 / OIDC` > `Clients`.
     - Click `New Client`.
     - Fill in details such as `Client ID`, `Client Secret`, and `Redirect URIs`.
   - **Set Scopes:**
     - Ensure that your client has the required scopes (`profile` and `email`).

2. **Obtain Client ID and Secret:**

   - **Client ID**: Found in the client registration under OpenAM's administrative console.
   - **Client Secret**: Found in the client registration under OpenAM's administrative console.

3. **Set Environment Variables:**

   Add the obtained values to your environment file (`.env`).

   ```env
   OPENAM_CLIENT_ID=<your_openam_client_id>
   OPENAM_CLIENT_SECRET=<your_openam_client_secret>
   OPENAM_BASE_URL=<your_openam_base_url>
   ```
