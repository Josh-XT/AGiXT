# ORCID

## Required Environment Variables

To set up ORCID Single Sign-On (SSO), you will need the following environment variables:

- `ORCID_CLIENT_ID`: ORCID OAuth client ID
- `ORCID_CLIENT_SECRET`: ORCID OAuth client secret

## How to Acquire ORCID Client ID and Secret

1. **Register your application with ORCID**: If you haven't already, you need to register your application with ORCID. Visit the [ORCID Developer Tools](https://orcid.org/content/register-client-application).

2. **Fill out the registration form**: Provide necessary details about your application. After the registration is complete, you will receive your `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET`.

3. **Add environment variables**: Once you have your `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET`, add them to your `.env` file as follows:

    ```plaintext
    ORCID_CLIENT_ID=your_orcid_client_id
    ORCID_CLIENT_SECRET=your_orcid_client_secret
    ```

## Required Scopes for ORCID SSO

The following scopes are required for ORCID SSO:

- `/authenticate`: This scope allows the application to read public profile information.
- `/activities/update` (optional): This scope allows the application to update ORCID activities.
