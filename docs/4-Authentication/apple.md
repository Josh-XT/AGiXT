# Apple

Apple Sign-In (SSO) allows you to use Apple's secure authentication service for user login and data retrieval. Setting up Apple SSO involves creating the required OAuth credentials and configuring your environment variables.

## Required Environment Variables

Before you begin, ensure you have the following environment variables set up in your `.env` file:

- `APPLE_CLIENT_ID`: Your Apple OAuth client ID
- `APPLE_CLIENT_SECRET`: Your Apple OAuth client secret

## Acquiring Apple OAuth Client ID and Client Secret

1. **Create an Apple Developer Account**: If you don't have an Apple Developer account, you will need to [register](https://developer.apple.com/programs/).

2. **Create an App ID**:
    - Go to [Apple Developer Portal](https://developer.apple.com/account/ios/identifier/bundle).
    - Under **Certificates, Identifiers & Profiles**, select **Identifiers**.
    - Click the "+" button to create a new App ID.
    - Register your App ID and ensure it has the appropriate capabilities for Sign-In with Apple.

3. **Configure Sign-In with Apple**:
    - After creating the App ID, configure it to use Sign-In with Apple.
    - Navigate to the **Keys** section in the [Apple Developer Portal](https://developer.apple.com/account/resources/authkeys/list).
    - Click the "+" button to create a new key.
    - Select the Sign In with Apple capability.
    - Download the key after generating it and keep it secure.

4. **Create a Service ID**:
    - Go to **Certificates, Identifiers & Profiles** > **Identifiers** > **Service IDs**.
    - Click the "+" button to create a new Service ID.
    - Enable **Sign-In with Apple** for this Service ID.

5. **Configure Redirect URI**:
    - Under the Sign-In with Apple configuration for your Service ID, add a redirect URI that matches the one used in your OAuth flow.

6. **Generate Apple Client Secret**:
    - The `APPLE_CLIENT_SECRET` is a JWT generated using your Apple private key and other details.
    - Use libraries such as `PyJWT` to generate this JWT.

    ```python
    import jwt
    import time
    from uuid import uuid4

    PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...your private key...\n-----END PRIVATE KEY-----\n"

    def generate_client_secret():
        headers = {
            "kid": "YOUR_KEY_ID",
            "alg": "ES256",
        }
        claims = {
            "iss": "YOUR_TEAM_ID",
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400*180,
            "aud": "https://appleid.apple.com",
            "sub": "YOUR_SERVICE_ID",
        }
        client_secret = jwt.encode(claims, PRIVATE_KEY, headers=headers, algorithm="ES256")
        return client_secret

    APPLE_CLIENT_SECRET = generate_client_secret()
    ```

### Setting Up the Environment Variables

Once you have the `APPLE_CLIENT_ID` and `APPLE_CLIENT_SECRET`, add them to your `.env` file:

```env
APPLE_CLIENT_ID=your_apple_client_id
APPLE_CLIENT_SECRET=your_apple_client_secret
```

### Required Scopes for Apple SSO

The required scopes for Apple SSO include:

- `name`: To get the user's name.
- `email`: To get the user's email address.

### Additional Notes

- This implementation uses placeholder values for `first_name`, `last_name`, and `email` which should be replaced with actual logic to capture user information during the initial token exchange.
- The `send_email` function is not implemented because Apple OAuth does not support sending emails directly via API.
- Ensure all sensitive information such as private keys and client secrets are securely stored and managed.
