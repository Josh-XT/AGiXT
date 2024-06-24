# Pixiv SSO

This documentation will guide you through setting up Pixiv Single Sign-On (SSO) in your application using the provided `pixiv.py` script. The integration leverages Pixiv's OAuth for user authentication.

## Required Environment Variables

To use Pixiv SSO, you need to set up the following environment variables in your `.env` file:

- `PIXIV_CLIENT_ID`: Your Pixiv OAuth client ID.
- `PIXIV_CLIENT_SECRET`: Your Pixiv OAuth client secret.

## Required APIs

Before setting up your environment variables, ensure you have the necessary Pixiv APIs enabled. Your application will need the following scopes to perform authentication through Pixiv OAuth:

- `pixiv.scope.profile.read`

## How To Acquire Keys

Follow these steps to get your `PIXIV_CLIENT_ID` and `PIXIV_CLIENT_SECRET`:

1. **Create a Pixiv OAuth Application**:
   - Go to the Pixiv developer site and log in with your Pixiv account.
   - Navigate to the section where you can manage your OAuth applications.
   - Create a new application. You will be asked to provide details such as the name and description of your application. Ensure you also specify the required scopes (`pixiv.scope.profile.read`).

2. **Get Client ID and Client Secret**:
   - Once the application is created, Pixiv will provide you with a `client_id` and `client_secret`. These will be your `PIXIV_CLIENT_ID` and `PIXIV_CLIENT_SECRET`.

3. **Add Environment Variables**:
   - Open or create a `.env` file in the root of your project directory.
   - Add the following lines to your `.env` file:

     ```env
     PIXIV_CLIENT_ID=your_pixiv_client_id_here
     PIXIV_CLIENT_SECRET=your_pixiv_client_secret_here
     ```
