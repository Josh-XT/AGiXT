# Yammer Integration

This module provides Single Sign-On (SSO) and messaging capabilities using Yammer's OAuth 2.0. It allows a user to authenticate via Yammer, acquire an access token, retrieve user information, and send messages to Yammer groups.

## Prerequisites

Before you can use this module, you need to set up a few things on Yammer and obtain the necessary credentials. Here is a step-by-step guide to help you:

## Step-by-Step Guide

1. **Creating a Yammer App:**
    - Go to the [Yammer Developer Site](https://www.yammer.com/client_applications)
    - Click on "Register New App".
    - Fill out the form with the required details such as:
        - **App Name**
        - **Organization**
        - **Support Email**
    - In the "Redirect URL" field, enter the URL where users will be redirected after authentication (usually your application's URL).

2. **Obtaining the Client ID and Client Secret:**
    - After creating your app, you will be taken to the app details page.
    - Here, you will find your **Client ID** and **Client Secret**.

3. **Environment Configuration:**
    - Create a `.env` file in your project root directory if you don't already have one.
    - Add the following environment variables to your `.env` file:

      ```plaintext
      YAMMER_CLIENT_ID=your_yammer_client_id
      YAMMER_CLIENT_SECRET=your_yammer_client_secret
      ```

## Required APIs

Make sure to enable the following Yammer API scopes:

- `messages:email`
- `messages:post`
  
These scopes can be configured when registering your app on the Yammer developer site.
