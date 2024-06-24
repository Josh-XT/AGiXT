# NetIQ

## Required Environment Variables

To integrate NetIQ single sign-on (SSO) in your application, you need to set the following environment variables:

- `NETIQ_CLIENT_ID`: NetIQ OAuth client ID
- `NETIQ_CLIENT_SECRET`: NetIQ OAuth client secret

## Steps to Acquire NetIQ Client ID and Client Secret

1. **Log in to your NetIQ Admin Console**:
   - Access the NetIQ admin console through your provided administrative URL.

2. **Register a New OAUTH Application**:
   - Navigate to the `OAuth` section within the admin console.
   - Add a new application by providing all the necessary details such as application name, redirect URIs, etc.

3. **Obtain `Client ID` and `Client Secret`**:
   - After successfully registering your application, NetIQ will provide you with a `Client ID` and `Client Secret`.

4. **Set Environment Variables**:
   - Add `NETIQ_CLIENT_ID` and `NETIQ_CLIENT_SECRET` to your .env file:

     ```dotenv
     NETIQ_CLIENT_ID=your-netiq-client-id
     NETIQ_CLIENT_SECRET=your-netiq-client-secret
     ```

## Required APIs

Ensure that the required APIs are enabled in your NetIQ settings. Usually, this can be found in the API Management section of the admin console.

## Required Scopes for NetIQ OAuth

Make sure to include the following scopes for your NetIQ OAuth authorization:

- `profile`
- `email`
- `openid`
- `user.info`
