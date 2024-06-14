# Fitbit

## Required environment variables

- `FITBIT_CLIENT_ID`: Fitbit OAuth client ID
- `FITBIT_CLIENT_SECRET`: Fitbit OAuth client secret

## Required APIs

Before using the Fitbit SSO, you need to confirm that you have the necessary APIs enabled and have acquired the required environment variables (FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET). Follow the steps below to do this:

1. **Create a Fitbit Developer Account**:
   - Go to the Fitbit dev portal: [Fitbit Developer](https://dev.fitbit.com/)
   - Create an account or log in if you already have one.

2. **Register Your Application**:
   - Navigate to the "Manage my Apps" section.
   - Click on "Register a New Application".
   - Fill out the application details.
   - Set the OAuth 2.0 Application Type to "Personal" or "Server".

3. **Obtain Client ID and Client Secret**:
   - After registering your application, Fitbit will provide you with a **Client ID** and **Client Secret**.

4. **Set Up Environment Variables**:
   - Create or update your `.env` file with the following:

     ```env
     FITBIT_CLIENT_ID=your_fitbit_client_id
     FITBIT_CLIENT_SECRET=your_fitbit_client_secret
     ```

## Required Scopes for Fitbit OAuth

When configuring OAuth for Fitbit, you need to request the appropriate permissions (scopes). Below are the required scopes:

- `activity`
- `heartrate`
- `location`
- `nutrition`
- `profile`
- `settings`
- `sleep`
- `social`
- `weight`
