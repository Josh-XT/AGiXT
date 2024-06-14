# VK SSO

## Required Environment Variables

- `VK_CLIENT_ID`: VK OAuth client ID
- `VK_CLIENT_SECRET`: VK OAuth client secret

## Required APIs

Ensure that you have the necessary VK APIs enabled by following these instructions. Once confirmed, add the `VK_CLIENT_ID` and `VK_CLIENT_SECRET` environment variables to your `.env` file.

1. **VK API Access Setup:**
   - Visit VK's [Developers Page](https://vk.com/dev) and create a new application if you haven't done so already.
   - Note down the Application ID (this will be your VK Client ID) and secure your Application Secret (this will be your VK Client Secret).
   - Configure your application to use VK API.

2. **Get the VK Client ID and Client Secret:**
   - After setting up your VK application, go to the application settings.
   - From the application settings, retrieve the **Application ID** which will serve as `VK_CLIENT_ID`.
   - Retrieve the **Secure Key** which will serve as `VK_CLIENT_SECRET`.

Add these values to your `.env` file in the following format:

```env
VK_CLIENT_ID=your_vk_client_id
VK_CLIENT_SECRET=your_vk_client_secret
```

## Required Scopes for VK SSO

To authenticate users via VK SSO, you need the following scope:

- `email`

Make sure your VK application requests this scope during the OAuth authorization process.
