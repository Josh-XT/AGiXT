# Stack Exchange SSO Guide

This guide provides detailed instructions on how to set up and use Stack Exchange Single Sign-On (SSO) in your application. Please follow each step carefully to ensure successful integration.

## Required Environment Variables

To utilize Stack Exchange SSO, you need to set the following environment variables in your `.env` file:

- `STACKEXCHANGE_CLIENT_ID`: Your Stack Exchange OAuth client ID.
- `STACKEXCHANGE_CLIENT_SECRET`: Your Stack Exchange OAuth client secret.
- `STACKEXCHANGE_KEY`: (Optional) A key for additional API requests (can enhance rate limits).

## Setting Up Stack Exchange OAuth Credentials

1. **Create a Stack Exchange Application:**
   - Go to the [Stack Exchange API Applications](https://stackapps.com/apps/oauth/register) page.
   - Click the "Register Your Application" button.
   - Fill in the required details such as Application Name, Description, Organization Information, etc.
   - Set the OAuth Redirect URL (you will need this URL for redirect_uri).
   - After their review, you will obtain the `Client ID` and `Client Secret` which are needed for the environment variables.

2. **Enable Required Scopes:**
   - The application will need the following scopes to function properly:
     - read_inbox
     - no_expiry
     - private_info
     - write_access

3. **Add the Environment Variables:**
   - Create a `.env` file at the root of your project if it does not exist already.
   - Add the following lines to the file with your corresponding credentials:

     ```env
     STACKEXCHANGE_CLIENT_ID=your_stack_exchange_client_id
     STACKEXCHANGE_CLIENT_SECRET=your_stack_exchange_client_secret
     STACKEXCHANGE_KEY=your_stack_exchange_key
     ```
