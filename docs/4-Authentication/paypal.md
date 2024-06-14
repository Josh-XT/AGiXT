# PayPal SSO Documentation

## Overview

This document provides information on how to configure and use the PayPal SSO (Single Sign-On) implemented in `./sso/paypal.py`. The PayPal SSO allows you to authenticate users with their PayPal accounts and perform actions such as retrieving user info and sending payments.

## Required Environment Variables

To use the PayPal SSO, you must set up the following environment variables:

- `PAYPAL_CLIENT_ID`: PayPal OAuth client ID.
- `PAYPAL_CLIENT_SECRET`: PayPal OAuth client secret.

Ensure you add these environment variables to your `.env` file.

### Steps to Acquire PayPal Client ID and Secret

1. **Log in to PayPal Developer Dashboard:**

   Go to the [PayPal Developer Dashboard](https://developer.paypal.com/).

2. **Create a New App:**

   - Navigate to **My Apps & Credentials**.
   - Click on **Create App** under the **REST API apps** section.
   - Provide an **App Name** and select a sandbox business account.
   - Click **Create App**.

3. **Get Client ID and Secret:**

   - Once the app is created, you�ll find your **Client ID** and **Secret** on the app�s page.
   - Copy the **Client ID** and **Secret** and add them to your `.env` file as follows:

     ```plaintext
     PAYPAL_CLIENT_ID=YOUR_CLIENT_ID
     PAYPAL_CLIENT_SECRET=YOUR_CLIENT_SECRET
     ```

## Configuration of Redirect URI

Make sure your `redirect_uri` is correctly set up in the PayPal Developer Dashboard:

- Go to your app settings.
- Add the `redirect_uri` to the **Return URL** section under the **App settings**.

## Required APIs

Ensure that you have the PayPal REST API enabled and the appropriate client credentials.

## Required Scopes for PayPal OAuth

To authenticate users and retrieve their information, you will need the following OAuth scopes:

- `email`
- `openid`
