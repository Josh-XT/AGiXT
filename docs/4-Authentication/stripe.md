# Stripe

## Required Environment Variables

To use Stripe SSO, ensure that the following environment variables are set:

- `STRIPE_CLIENT_ID`: Your Stripe OAuth client ID.
- `STRIPE_CLIENT_SECRET`: Your Stripe OAuth client secret.

## Required Scopes for Stripe SSO

Make sure you have the required scope for Stripe SSO:

- `read_write`

## How to Acquire Required Keys

1. **Create a Stripe Account**: If you don't have a Stripe account, sign up at [Stripe](https://stripe.com/).
2. **Create a New Project**: Once logged in, navigate to your dashboard and create a new project.
3. **Get Your Client ID and Secret**: Go to "Developers" > "API keys". Here you will find your client ID and secret:
   - **Client ID**: This is your OAuth client ID used for authentication.
   - **Client Secret**: This is your OAuth client secret that should be kept secure.

## Setting Up Environment Variables

Once you have your client ID and secret, add them to your environment variables. If you�re using a `.env` file, it should look like this:

```env
STRIPE_CLIENT_ID=your_stripe_client_id
STRIPE_CLIENT_SECRET=your_stripe_client_secret
```
