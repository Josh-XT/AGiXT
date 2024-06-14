# Reddit SSO Integration

This module allows you to integrate Reddit Single Sign-On (SSO) into your application. By using this module, you can authenticate via Reddit, retrieve user information, and even submit posts to a subreddit on behalf of a user. The code leverages the Reddit OAuth2.0 for authentication and authorization.

## Required Environment Variables

Before you begin, you'll need to set up the following environment variables in your `.env` file:

- `REDDIT_CLIENT_ID`: Your Reddit application's client ID.
- `REDDIT_CLIENT_SECRET`: Your Reddit application's client secret.

## Required APIs

Make sure you have a Reddit OAuth application set up. You can create one by following these steps:

1. Go to [Reddit Apps](https://www.reddit.com/prefs/apps).
2. Scroll down to "Developed Applications" and click on `Create App`.
3. Fill in the application name, and choose `script` as the type.
4. Set the `redirect_uri` to a valid URL where you will receive the authorization code (e.g., `http://localhost:8000/reddit_callback`).
5. Note down the `client ID` and `client secret` from the created application.
6. Add the `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to your `.env` file.

## Required Scopes for Reddit OAuth

Ensure that your Reddit OAuth application requests the following scopes:

- `identity`: Access to the user�s Reddit identity.
- `submit`: Ability to submit and edit content.
- `read`: Ability to read private messages and save content.
