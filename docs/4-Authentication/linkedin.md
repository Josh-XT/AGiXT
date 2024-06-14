# LinkedIn SSO Integration

## Overview

This document provides a guide for setting up LinkedIn Single Sign-On (SSO) integration in your application. Follow the steps below to configure the LinkedIn OAuth client and obtain the necessary keys and permissions.

## Required Environment Variables

To integrate LinkedIn SSO, you need to set the following environment variables in your `.env` file:

- `LINKEDIN_CLIENT_ID`: LinkedIn OAuth client ID
- `LINKEDIN_CLIENT_SECRET`: LinkedIn OAuth client secret

## Steps to Acquire LinkedIn OAuth Credentials

Follow these steps to obtain the required LinkedIn OAuth credentials:

1. **Create a LinkedIn Application**
    - Navigate to [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
    - Log in with your LinkedIn account.
    - Click on "Create App" and fill in the required details.
    - After the app is created, you will be redirected to the app's dashboard.

2. **Obtain Client ID and Client Secret**
    - In the app's dashboard, locate `Client ID` and `Client Secret` under the "Auth" tab.
    - Copy these values and add them to your `.env` file as `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`.

3. **Set Up Redirect URI**
    - Ensure you set up the correct Redirect URI. This URI should match the one used in your application. You can set this URI in the app's "Auth" tab.

## Required APIs and Scopes

To enable LinkedIn SSO, you must ensure that your application has access to the following APIs and scopes:

### Required APIs

- No additional APIs are needed other than LinkedIn's default OAuth APIs.

### Required Scopes for LinkedIn OAuth

- `r_liteprofile`: Grants access to retrieve the user's profile.
- `r_emailaddress`: Grants access to retrieve the user's email address.
- `w_member_social`: Grants access to post and share content on LinkedIn.

Ensure that these scopes are requested during the OAuth authorization process.

## Setting Environment Variables

Add the obtained credentials and required environment variables to your `.env` file:

```env
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
```
