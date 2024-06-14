# GitHub Single Sign-On Implementation

This documentation details how to implement GitHub Single Sign-On (SSO) in your application using the provided `GitHubSSO` class and related functions.

## Required Environment Variables

To use the `GitHubSSO` class, you need to have the following environment variables set:

- `GITHUB_CLIENT_ID`: GitHub OAuth client ID
- `GITHUB_CLIENT_SECRET`: GitHub OAuth client secret

## Required Scopes for GitHub OAuth

Ensure your GitHub OAuth application requests the following scopes to access the necessary user information:

- `user:email`
- `read:user`

## How to Acquire GitHub OAuth Client ID and Client Secret

1. **Register a new OAuth application on GitHub:**
   - Go to GitHub's developer settings: [GitHub Developer Settings](https://github.com/settings/developers)
   - Click on `New OAuth App`.
   - Fill in the required fields:
     - **Application name**: Your application�s name.
     - **Homepage URL**: The URL to your application's homepage.
     - **Authorization callback URL**: The redirect URI where users will be sent after authorization. This should match the `redirect_uri` parameter in your authorization request.
   - Click `Register application`.

2. **Get the client credentials:**
   - After registering, you will see your new application listed on the OAuth Apps page.
   - Click on the application to see its details.
   - Copy the `Client ID` and `Client Secret` to use as environment variables in your application.

3. **Set Environment Variables:**
   - Add the `Client ID` and `Client Secret` to your environment variables. This can be done in your `.env` file like so:

     ```env
     GITHUB_CLIENT_ID=your_client_id
     GITHUB_CLIENT_SECRET=your_client_secret
     ```

   - Replace `your_client_id` and `your_client_secret` with the actual values you copied from GitHub.
