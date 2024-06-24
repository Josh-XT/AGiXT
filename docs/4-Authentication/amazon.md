# Amazon SSO

## Overview

This module provides Single Sign-On (SSO) functionality using AWS Cognito, allowing users to authenticate and fetch user information. Additionally, it includes the functionality to send emails using Amazon SES (Simple Email Service).

## Required Environment Variables

To use the Amazon SSO module, you need to set up the following environment variables. These credentials can be acquired from the AWS Management Console.

```plaintext
AWS_CLIENT_ID: AWS Cognito OAuth client ID
AWS_CLIENT_SECRET: AWS Cognito OAuth client secret
AWS_USER_POOL_ID: AWS Cognito User Pool ID
AWS_REGION: AWS Cognito Region
```

### Step-by-Step Guide to Acquire the Required Keys

1. **AWS Client ID and Client Secret**:
    - Navigate to the [Amazon Cognito Console](https://console.aws.amazon.com/cognito/home).
    - Click on **Manage User Pools** and select the user pool you have set up for your application.
    - Navigate to the **App integration** section.
    - Under **App clients and analytics**, find your app client or create one by clicking **Add an app client**.
    - Save the **App client id** and **App client secret** as they will be your `AWS_CLIENT_ID` and `AWS_CLIENT_SECRET`.

2. **AWS User Pool ID**:
    - In the Cognito User Pool you've set up, the **User Pool ID** is displayed at the top of the **General settings** section in the details page of your user pool. Assign this value to `AWS_USER_POOL_ID`.

3. **AWS Region**:
    - The region in which your Cognito User Pool is located, such as `us-west-2`. Assign this value to `AWS_REGION`.

## Required Scopes for AWS OAuth

Include the following scopes in your OAuth configuration to get relevant user information and send emails:

- openid
- email
- profile
