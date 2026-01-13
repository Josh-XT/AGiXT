````markdown
# Tesla Single Sign-On (SSO) Integration

## Overview

This module provides Single Sign-On (SSO) functionality using Tesla OAuth2, allowing users to authenticate through their Tesla accounts and access the Tesla Fleet API for vehicle control and monitoring.

## Required Environment Variables

To use the Tesla SSO integration, you need to set up the following environment variables:

- `TESLA_CLIENT_ID`: Tesla OAuth client ID
- `TESLA_CLIENT_SECRET`: Tesla OAuth client secret
- `TESLA_AUDIENCE`: Fleet API base URL (default: `https://fleet-api.prd.na.vn.cloud.tesla.com`)

## Setting Up Tesla SSO

### Step 1: Register as a Tesla Developer

1. Go to the [Tesla Developer Portal](https://developer.tesla.com/).
2. Sign in with your Tesla account.
3. Apply for API access (requires approval from Tesla).

### Step 2: Create an Application

1. Once approved, create a new application in the Developer Portal.
2. Configure your application details:
   - **Application Name**: Your application's name
   - **Description**: Brief description of your application
   - **Allowed Origins**: Your application's domain

### Step 3: Configure OAuth Settings

1. Set your **Redirect URI**. This should match your `APP_URI` environment variable plus `/user/close/tesla` (e.g., `http://localhost:3437/user/close/tesla`).
2. Select the appropriate scopes for your application.

### Step 4: Get Client Credentials

1. In your application settings, find your **Client ID** and **Client Secret**.
2. Store these values securely.

### Step 5: Add Environment Variables

Add the following environment variables to your `.env` file:

```sh
TESLA_CLIENT_ID=your_client_id
TESLA_CLIENT_SECRET=your_client_secret
TESLA_AUDIENCE=https://fleet-api.prd.na.vn.cloud.tesla.com
```

## Required Scopes for Tesla OAuth

The Tesla integration requests the following scopes:

- `openid`: OpenID Connect authentication
- `offline_access`: Refresh tokens for long-lived access
- `user_data`: Access user profile information
- `vehicle_device_data`: Read vehicle data and status
- `vehicle_cmds`: Send commands to vehicles
- `vehicle_charging_cmds`: Control charging operations
- `vehicle_location`: Access vehicle location data

## Fleet API Regions

Tesla operates different Fleet API endpoints for different regions. Set `TESLA_AUDIENCE` to the appropriate region:

- **North America**: `https://fleet-api.prd.na.vn.cloud.tesla.com`
- **Europe**: `https://fleet-api.prd.eu.vn.cloud.tesla.com`
- **China**: `https://fleet-api.prd.cn.vn.cloud.tesla.cn`

## Features

Once authenticated, the Tesla extension provides:

- Vehicle listing and status
- Climate control (heating, cooling, seat heaters)
- Charging management (start/stop charging, set limits)
- Door and trunk control
- Horn and lights activation
- Location tracking
- Drive state monitoring
- Software update status
- Powerwall integration (if applicable)

## Security Note

Tesla API access controls real vehicles. Ensure proper security measures:

- Store credentials securely
- Use HTTPS for all communications
- Implement proper access controls in your application
- Monitor API usage for unauthorized access
````
