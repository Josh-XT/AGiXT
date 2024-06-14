# Sina Weibo Single Sign-On (SSO) Integration

## Overview

This module enables Single Sign-On (SSO) integration with Sina Weibo through OAuth 2.0. This guide provides the necessary steps and details to set up the integration, including acquiring the required keys, setting up environment variables, and implementing the code provided.

## Required Environment Variables

In order to use the Sina Weibo SSO integration, you need to set several environment variables. These variables are used in the OAuth authentication process to communicate with the Weibo API.

Below is a list of the required environment variables:

- `WEIBO_CLIENT_ID`: Weibo OAuth client ID
- `WEIBO_CLIENT_SECRET`: Weibo OAuth client secret

## Required APIs and Scopes

Before proceeding, ensure you have the necessary APIs enabled and permissions configured. The required scopes for Weibo OAuth are:

- `email`
- `statuses_update`

## Steps to Acquire Keys and Set Up Environment

### Step 1: Register Your Application with Weibo

1. Log in to the [Weibo Open Platform](https://open.weibo.com/).
2. Navigate to "My Apps" and click on "Create App".
3. Fill in the required details about your application, such as name, description, and redirect URL.
4. Once your application is created, you will receive a `CLIENT_ID` and `CLIENT_SECRET`.

### Step 2: Set Up Your Environment Variables

Once you have your `CLIENT_ID` and `CLIENT_SECRET`, you'll need to add them to your environment as follows:

1. Create a `.env` file in the root directory of your project.
2. Add the following lines to your `.env` file:

```env
WEIBO_CLIENT_ID=your_client_id
WEIBO_CLIENT_SECRET=your_client_secret
```

Replace `your_client_id`, `your_client_secret`, and `your_redirect_uri` with your actual Weibo OAuth credentials and your application's redirect URL.
