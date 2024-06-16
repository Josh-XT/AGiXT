# Formstack

## Required Environment Variables

To use the FormstackSSO class and its methods, you need to set up the following environment variables in your `.env` file:

- `FORMSTACK_CLIENT_ID`: Your Formstack OAuth client ID
- `FORMSTACK_CLIENT_SECRET`: Your Formstack OAuth client secret

You can get these credentials by following these steps:

1. **Create a Formstack Application**:
    - Log in to your Formstack account.
    - Navigate to the "Account" section and select "API" from the sidebar menu.
    - Click on "Add Application" to create a new app.
    - Fill in the necessary details such as the app name and description.
    - Make sure to note down the generated `Client ID` and `Client Secret` as you will need them to set up the environment variables.

2. **Add Environment Variables**:
    - Open your `.env` file.
    - Add the following lines, replacing the placeholder values with your actual Formstack credentials:

    ```plaintext
    FORMSTACK_CLIENT_ID=your_formstack_client_id
    FORMSTACK_CLIENT_SECRET=your_formstack_client_secret
    ```

## Required APIs

Ensure that the necessary APIs are enabled in your Formstack account:

- **User API**: This API allows you to access user information such as first name, last name, and email address.
- **Form API**: This API allows you to manage forms, including sending form submissions.

## Required Scopes for Formstack OAuth

When setting up OAuth for Formstack, make sure you request the following scopes:

- `formstack:read`: Allows you to read data from Formstack, such as user information.
- `formstack:write`: Allows you to write data to Formstack, such as submitting form data.
