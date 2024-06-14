# WeChat

WeChat SSO allows users to log in to your application using their WeChat account. This is implemented in the `wechat.py` file, which handles the OAuth flow, token management, and fetching user information.

## Required Environment Variables

To use WeChat SSO, you need to add the following environment variables to your environment or `.env` file:

- `WECHAT_CLIENT_ID`: WeChat OAuth client ID.
- `WECHAT_CLIENT_SECRET`: WeChat OAuth client secret.

## Acquiring WeChat Client ID and Client Secret

1. **Register Your Application:**
   - Visit the [WeChat Open Platform](https://open.weixin.qq.com/) and sign in with your WeChat account.
   - Navigate to the "Manage Center" and click on "Create Application".
   - Fill out the required information about your application.

2. **Get Your Credentials:**
   - Once your application is created, navigate to the "Basic Configuration" section.
   - Copy the `AppID` and `AppSecret`. These correspond to `WECHAT_CLIENT_ID` and `WECHAT_CLIENT_SECRET` respectively.

3. **Add Redirect URI:**
   - In the same section, add the authorization callback URL, which is the `redirect_uri` you will use for WeChat OAuth.

4. **Set Environment Variables:**
   - Add the `WECHAT_CLIENT_ID` and `WECHAT_CLIENT_SECRET` to your environment or `.env` file:

     ```text
     WECHAT_CLIENT_ID=your_client_id
     WECHAT_CLIENT_SECRET=your_client_secret
     ```

## Required Scopes for WeChat SSO

- `snsapi_userinfo`: This scope allows your application to fetch the user's profile information.
