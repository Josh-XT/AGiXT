# Google SSO Module Documentation

This module allows you to implement Google Single Sign-On (SSO) and send emails using the Gmail API.

## Setup Instructions

### Prerequisites

Ensure you have the following prerequisites before proceeding:

1. Python environment with necessary dependencies.
2. Google Cloud project with the required APIs enabled.

### Step-by-Step Guide

#### 1. Enable Required APIs

To use this module, you need to enable two APIs in your Google Cloud project:

- **People API:** This API is required to fetch user information such as names and email addresses. Enable it [here](https://console.cloud.google.com/marketplace/product/google/people.googleapis.com).
- **Gmail API:** This API is needed to send emails using Gmail. Enable it [here](https://console.cloud.google.com/marketplace/product/google/gmail.googleapis.com).

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
    - Save the details.

3. **Create OAuth 2.0 Client ID:**
    - Go to **APIs & Services > Credentials**.
    - Click on **Create Credentials** and choose **OAuth 2.0 Client ID**.
    - Configure the application type. For web applications, you need to specify the **Authorized redirect URIs**.
    - Save the credentials and note down the **Client ID** and **Client Secret**.

#### 3. Set Environment Variables

Add the obtained credentials to your environment variables. Create a `.env` file in your project root directory with the following content:

```dotenv
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

Replace `your_google_client_id` and `your_google_client_secret` with the values you obtained in the previous step.

### Required Scopes

The following OAuth 2.0 scopes are required for the module to function correctly:

- `https://www.googleapis.com/auth/userinfo.profile`
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/gmail.send`

Ensure these scopes are specified when requesting user consent.
