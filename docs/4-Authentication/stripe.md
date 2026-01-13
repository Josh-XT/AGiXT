````markdown
# Stripe Connect Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Stripe Connect OAuth, allowing users to connect their Stripe accounts for payment processing, subscriptions, and financial operations.

## Required Environment Variables

To use the Stripe SSO integration, you need to set up the following environment variables:

- `STRIPE_CLIENT_ID`: Stripe Connect OAuth client ID
- `STRIPE_CLIENT_SECRET`: Stripe API secret key

## Setting Up Stripe Connect SSO

### Step 1: Create a Stripe Account

1. Go to [Stripe](https://stripe.com/) and create an account if you don't have one.
2. Complete the account verification process.

### Step 2: Enable Stripe Connect

1. Navigate to the [Stripe Dashboard](https://dashboard.stripe.com/).
2. Go to **Settings** > **Connect** > **Settings**.
3. Enable Stripe Connect for your account.

### Step 3: Configure OAuth Settings

1. In Connect settings, find the **OAuth settings** section.
2. Add your **Redirect URI**. This should match your `APP_URI` environment variable plus `/user/close/stripe` (e.g., `http://localhost:3437/user/close/stripe`).
3. Note your **Client ID** from the Connect settings.

### Step 4: Get API Keys

1. Go to **Developers** > **API keys**.
2. Copy your **Secret key** (use test key for development).
3. Store these values securely.

### Step 5: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
STRIPE_CLIENT_ID=your_connect_client_id
STRIPE_CLIENT_SECRET=your_stripe_secret_key
```

## Required Scopes for Stripe OAuth

The Stripe Connect integration requests:

- `read_write`: Full access to connected account

## Connect Account Types

Stripe Connect supports different account types:

- **Standard**: Stripe-hosted onboarding, Stripe handles compliance
- **Express**: Simplified onboarding, some platform control
- **Custom**: Full platform control, requires handling compliance

## Features

Once authenticated, the Stripe extension provides:

- Payment processing
- Subscription management
- Invoice creation
- Customer management
- Refund processing
- Payout management
- Balance inquiries
- Transaction history
- Webhook handling

## Webhook Configuration

For real-time payment events, configure webhooks:

1. Go to **Developers** > **Webhooks**.
2. Add an endpoint for your application.
3. Select the events you want to receive.
4. Copy the **Webhook signing secret** for verification.

## Test Mode vs Live Mode

Stripe provides separate keys for testing:

- Use test keys (`sk_test_...`) during development
- Switch to live keys (`sk_live_...`) for production
- Test card numbers are available for simulating transactions

## Security Notes

- Never expose your secret key in client-side code
- Use webhook signatures to verify event authenticity
- Implement proper error handling for payment failures
- Follow PCI compliance guidelines
````
