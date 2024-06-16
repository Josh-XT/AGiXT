# Documentation for Deutsche Telekom SSO

## Overview

The provided script integrates the Deutsche Telekom Single Sign-On (SSO) service. It allows users to authenticate with their Deutsche Telekom credentials and access their profile and email services.

## Requirements

To successfully use the Deutsche Telekom SSO integration, you need to set up the following environment, APIs, and scopes.

### Required Environment Variables

- `DEUTSCHE_TELKOM_CLIENT_ID`: Deutsche Telekom OAuth client ID
- `DEUTSCHE_TELKOM_CLIENT_SECRET`: Deutsche Telekom OAuth client secret

### Required APIs

Ensure you have access to the following API endpoint for Deutsche Telekom:

- `https://www.deutschetelekom.com/ldap-sso`

### Required Scopes

The following OAuth scopes are required for Deutsche Telekom SSO:

- `t-online-profile`: Access to profile data
- `t-online-email`: Access to email services

## Setup Instructions

### 1. Registering Your Application

Before using the Deutsche Telekom SSO service, you need to register your application to obtain the `CLIENT_ID` and `CLIENT_SECRET`.

#### Steps to Register

1. Navigate to the Deutsche Telekom Developer Portal.
2. Log in with your Deutsche Telekom account.
3. Register a new application to get the OAuth credentials.
4. Note down the `Client ID` and `Client Secret` provided by Deutsche Telekom after registering your application.

### 2. Setting Up Environment Variables

Once you have the `Client ID` and `Client Secret`, set up the following environment variables in your system:

```sh
export DEUTSCHE_TELKOM_CLIENT_ID=your_client_id_here
export DEUTSCHE_TELKOM_CLIENT_SECRET=your_client_secret_here
```

Where:

- `DEUTSCHE_TELKOM_CLIENT_ID` is the Client ID you obtained from the Deutsche Telekom Developer Portal.
- `DEUTSCHE_TELKOM_CLIENT_SECRET` is the Client Secret provided by Deutsche Telekom.

> Ensure that you replace `your_client_id_here`, `your_client_secret_here`, and `your_redirect_uri_here` with the actual values.

### 3. Required Scopes

Make sure the Deutsche Telekom application is configured to request the following OAuth scopes:

- `t-online-profile`
- `t-online-email`
