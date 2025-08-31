# Meta Single Sign-On (SSO) Integration

## Overview

This module provides an integration with Meta's Single Sign-On (SSO) to allow your application to authenticate users through their Meta (Facebook) accounts and manage advertising campaigns using Meta's Marketing API.

## Required Environment Variables

To use the Meta SSO integration, you'll need to set up the following environment variables:

- `META_APP_ID`: Meta (Facebook) OAuth app ID
- `META_APP_SECRET`: Meta (Facebook) OAuth app secret
- `META_BUSINESS_ID`: Meta Business Manager account ID

These values can be obtained by registering your application in the Meta for Developers portal.

## Setting Up Meta SSO

### Step 1: Create a Meta App

1. Go to [Meta for Developers](https://developers.facebook.com/).
2. Click **My Apps** in the top navigation.
3. Click **Create App**.
4. Select **Business** as the app type.
5. Fill in your app details:
   - **App Name**: Choose a name for your application
   - **App Contact Email**: Your contact email
   - **Business Account**: Select your business account (create one if needed)
6. Click **Create App**.

### Step 2: Add Marketing API Product

1. In your app dashboard, click **Add Product**.
2. Find **Marketing API** and click **Set Up**.
3. Complete the setup process for Marketing API access.

### Step 3: Configure OAuth Settings

1. Go to **App Settings** > **Basic**.
2. Add your **App Domains** (e.g., `yourdomain.com`).
3. In the **Valid OAuth Redirect URIs** field, add your redirect URI. This should match the `APP_URI` environment variable in your `.env` file plus `/auth/meta` (e.g., `http://localhost:3437/auth/meta`).
4. Save your changes.

### Step 4: Get Business Manager ID

1. Go to [Meta Business Manager](https://business.facebook.com/).
2. Navigate to **Business Settings**.
3. Under **Business Info**, you'll find your **Business Manager ID**.

### Step 5: App Review Process

For production use, you'll need to submit your app for review to access advanced Marketing API features:

1. Go to **App Review** in your app dashboard.
2. Submit your app for review with the required permissions.
3. Provide detailed use case documentation.
4. Wait for approval (can take several days).

### Step 6: Obtain App ID and App Secret

1. In the **App Settings** > **Basic** section, you will find the **App ID**. This is your `META_APP_ID`.
2. The **App Secret** is also listed in the Basic settings. Click **Show** to reveal it. This is your `META_APP_SECRET`.
3. Store these values securely.

### Step 7: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_BUSINESS_ID=your_business_manager_id
```

## Required Scopes for Meta OAuth

The Meta Ads extension requests the following permissions:

- `ads_management`: Create and manage advertising campaigns
- `ads_read`: Read advertising data and insights
- `business_management`: Access business accounts and settings
- `pages_read_engagement`: Read page engagement metrics
- `pages_manage_ads`: Manage page advertising
- `pages_show_list`: List accessible pages
- `read_insights`: Access detailed analytics and insights
- `email`: Basic user profile information

These scopes are automatically requested when users authenticate, allowing your application to manage Meta advertising campaigns, access performance data, and handle audience management.

## Development vs Production

### Development Mode
- Use test ad accounts for development
- No app review required for basic testing
- Limited daily API call quotas
- Test with small budgets only

### Production Mode
- Requires completed app review process
- Access to full Marketing API features
- Higher API rate limits
- Can manage real advertising campaigns with actual budgets

## Security Considerations

- Store app credentials securely and never commit them to version control
- Use HTTPS for all OAuth redirect URIs in production
- Regularly rotate app secrets
- Monitor API usage for unusual activity
- Follow Meta's advertising policies and community standards
- Implement proper access controls for advertising account management

## Testing Your Integration

You can test your Meta SSO integration by:

1. Setting up the environment variables
2. Starting AGiXT with the Meta Ads extension enabled
3. Creating an agent with Meta advertising capabilities
4. Testing OAuth authentication flow through the AGiXT interface
5. Verifying that advertising commands are available and functional

## Troubleshooting

### Common Issues

**Invalid App ID or Secret**
- Double-check your app credentials in Meta for Developers
- Ensure the app is properly configured for your domain
- Verify that the app secret hasn't expired

**Permission Denied Errors**
- Check that your app has been approved for Marketing API access
- Verify that all required scopes are requested
- Ensure the user has proper permissions for the advertising accounts

**Redirect URI Mismatch**
- Verify that your OAuth redirect URI matches exactly what's configured in your Meta app
- Check that the `APP_URI` environment variable is correct
- Ensure the redirect URI uses HTTPS in production

**Business Manager Access Issues**
- Confirm that your app is associated with the correct Business Manager
- Verify that the Business Manager ID is correct
- Check that the user has appropriate roles in Business Manager

For additional support, consult the [Meta Marketing API documentation](https://developers.facebook.com/docs/marketing-api/) or the [Meta Developer Community](https://developers.facebook.com/community/).
