# Google SSO Module Documentation

This module allows you to implement Google Single Sign-On (SSO) and interact with various Google services including Gmail, Calendar, Google Ads, Google Analytics, and Google Tag Manager.

## Setup Instructions

### Prerequisites

Ensure you have the following prerequisites before proceeding:

1. Python environment with necessary dependencies.
2. Google Cloud project with the required APIs enabled.

### Step-by-Step Guide

#### 1. Enable Required APIs

To use this module, you need to enable the following APIs in your Google Cloud project:

##### Core APIs
- **People API:** Required to fetch user information such as names and email addresses. Enable it [here](https://console.cloud.google.com/marketplace/product/google/people.googleapis.com).
- **Gmail API:** Needed to send, read, and manage emails using Gmail. Enable it [here](https://console.cloud.google.com/marketplace/product/google/gmail.googleapis.com).
- **Calendar API:** Required for calendar management. Enable it [here](https://console.cloud.google.com/marketplace/product/google/calendar-json.googleapis.com).

##### Marketing APIs
- **Google Ads API:** Required for managing Google Ads campaigns, ad groups, and performance metrics. Enable it [here](https://console.cloud.google.com/marketplace/product/google/googleads.googleapis.com).
- **Google Analytics Data API:** Needed for GA4 reporting and analytics. Enable it [here](https://console.cloud.google.com/marketplace/product/google/analyticsdata.googleapis.com).
- **Google Analytics Admin API:** Required for managing GA4 properties and configurations. Enable it [here](https://console.cloud.google.com/marketplace/product/google/analyticsadmin.googleapis.com).
- **Tag Manager API:** Needed for managing Google Tag Manager containers, tags, triggers, and variables. Enable it [here](https://console.cloud.google.com/marketplace/product/google/tagmanager.googleapis.com).

#### 2. Obtain OAuth 2.0 Credentials

Follow these steps to get your OAuth 2.0 credentials:

1. **Create a Google Cloud Project:**
    - Go to the [Google Cloud Console](https://console.cloud.google.com/).
    - Click on the project dropdown and select **New Project**.
    - Enter the project name and other required information and click **Create**.

2. **Configure OAuth Consent Screen:**
    - In the [Google Cloud Console](https://console.cloud.google.com/), navigate to **APIs & Services > OAuth consent screen**.
    - Select **External** for user type if you are making it publicly accessible.
    - Fill in the required fields like App name, User support email, Authorized domains, etc.
    - Add the required scopes (see below).
    - Save the details.

3. **Create OAuth 2.0 Client ID:**
    - Go to **APIs & Services > Credentials**.
    - Click on **Create Credentials** and choose **OAuth 2.0 Client ID**.
    - Configure the application type. For web applications, you need to specify the **Authorized redirect URIs**.
    - Save the credentials and note down the **Client ID** and **Client Secret**.

#### 3. Set Environment Variables

Add the obtained credentials to your environment variables. Create a `.env` file in your project root directory with the following content:

```dotenv
# Required
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Optional - for Google Ads
GOOGLE_ADS_CUSTOMER_ID=your_google_ads_customer_id
```

Replace the placeholder values with your actual credentials.

### Required Scopes

The following OAuth 2.0 scopes are required for the module to function correctly:

#### Core Scopes
- `https://www.googleapis.com/auth/userinfo.profile` - User profile information
- `https://www.googleapis.com/auth/userinfo.email` - User email address
- `https://www.googleapis.com/auth/calendar.events.owned` - Calendar events management
- `https://www.googleapis.com/auth/contacts.readonly` - Read contact information
- `https://www.googleapis.com/auth/gmail.modify` - Full Gmail access

#### Marketing Scopes
- `https://www.googleapis.com/auth/adwords` - Google Ads management
- `https://www.googleapis.com/auth/analytics.readonly` - Google Analytics data read access
- `https://www.googleapis.com/auth/analytics.edit` - Google Analytics configuration
- `https://www.googleapis.com/auth/tagmanager.edit.containers` - Google Tag Manager container management
- `https://www.googleapis.com/auth/tagmanager.publish` - Google Tag Manager publishing
- `https://www.googleapis.com/auth/content` - Google Merchant Center (optional)

Ensure these scopes are specified when requesting user consent.

## Additional Setup for Marketing Features

### Google Ads Setup

1. **Create a Google Ads Manager Account:**
   - Visit [Google Ads](https://ads.google.com) and create a manager account if you don't have one.
   - Note your Customer ID (displayed at the top of the Google Ads interface).

2. **Link Google Ads to Google Cloud Project:**
   - In Google Cloud Console, go to **APIs & Services > Credentials**.
   - Ensure your OAuth 2.0 client has access to Google Ads API.

### Google Analytics Setup

1. **Create GA4 Properties:**
   - Visit [Google Analytics](https://analytics.google.com).
   - Create or select your GA4 properties.
   - Note the Property ID (found in Property Settings).

2. **Enable Data API Access:**
   - Ensure the Google Analytics Data API is enabled in your Cloud project.
   - The user authenticating must have appropriate permissions in GA4.

### Google Tag Manager Setup

1. **Create GTM Container:**
   - Visit [Google Tag Manager](https://tagmanager.google.com).
   - Create containers for your websites/apps.
   - Note the Container ID and Account ID.

2. **Set Permissions:**
   - Ensure the authenticating user has publish permissions in GTM.

## Available Functions

The Google extension now provides comprehensive marketing capabilities:

### Google Ads Functions
- Get/Create/Update campaigns
- Manage ad groups and ads
- Track performance metrics
- Manage keywords and audiences

### Google Analytics Functions
- Get GA4 properties
- Generate reports and real-time data
- Manage audiences and custom dimensions

### Google Tag Manager Functions
- Manage containers
- Create/update tags, triggers, and variables
- Publish container versions

## Troubleshooting

### Common Issues

1. **Insufficient Permissions:**
   - Ensure all required APIs are enabled.
   - Verify the user has appropriate access to the services.

2. **Scope Errors:**
   - Make sure all required scopes are included in your OAuth consent screen.
   - Users may need to re-authenticate if new scopes are added.

3. **API Quotas:**
   - Monitor your API usage in Google Cloud Console.
   - Request quota increases if needed.

### Support

For additional help:
- Check the [Google Cloud Documentation](https://cloud.google.com/docs)
- Review [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/start)
- Consult [Google Analytics API Documentation](https://developers.google.com/analytics/devguides/reporting/data/v1)
- See [Tag Manager API Documentation](https://developers.google.com/tag-manager/api/v2)
