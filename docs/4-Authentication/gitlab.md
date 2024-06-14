# GitLab SSO Integration

This guide walks you through integrating GitLab single sign-on (SSO) with your application. Using GitLab SSO, you can enable users to authenticate using their GitLab accounts.

## Required Environment Variables

To set up GitLab SSO, two key environment variables need to be configured:

- `GITLAB_CLIENT_ID`: This is the OAuth client ID from your GitLab application.
- `GITLAB_CLIENT_SECRET`: This is the OAuth client secret from your GitLab application.

## Steps to Acquire GitLab Client ID and Client Secret

1. **Create a GitLab OAuth Application:**
   - Go to [GitLab Sign-In](https://gitlab.com/users/sign_in) and log in using your credentials.
   - Go to your GitLab [Profile Settings](https://gitlab.com/profile/applications).
   - Click on `New application`.

2. **Configure the Application:**
   - Enter the `Name` for your application (e.g., "MyAppSSO").
   - Fill in the `Redirect URI` field with the URL to which your application will redirect after successful authentication (e.g., `http://localhost:8000/callback`).
   - Under `Scopes`, select `read_user`, `api`, and `email`.
   - Click on `Save application`.

3. **Retrieve Your Credentials:**
   - After saving, GitLab will provide a `Application ID` (which corresponds to `GITLAB_CLIENT_ID`) and `Secret` (which corresponds to `GITLAB_CLIENT_SECRET`).
   - Set these values in your environment variables or `.env` file:

     ```env
     GITLAB_CLIENT_ID=your_client_id
     GITLAB_CLIENT_SECRET=your_client_secret
     ```

## Required Scopes for GitLab SSO

When creating your OAuth application on GitLab, ensure that you select the following scopes:

- `read_user`: Allows reading the authenticated user�s profile data.
- `api`: Full access to the authenticated user's API.
- `email`: Access to the authenticated user's email address.

These scopes are necessary for retrieving user information such as name and email.
