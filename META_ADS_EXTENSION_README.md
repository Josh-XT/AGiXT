# Meta Ads Extension for AGiXT

## Overview

The Meta Ads extension provides comprehensive marketing automation capabilities for Facebook and Instagram advertising through the Meta Marketing API. This extension enables AI agents to manage advertising campaigns, analyze performance metrics, create custom audiences, and automate various marketing tasks.

## Features

### Campaign Management
- Create, read, update, and delete advertising campaigns
- Set campaign budgets and scheduling
- Pause and resume campaigns
- Get campaign performance insights

### Ad Set Management  
- Create and configure ad sets with targeting options
- Manage budgets and optimization goals
- Update targeting parameters
- Track ad set performance metrics

### Ad Management
- Create ads with custom creatives
- Update ad status and settings
- Monitor individual ad performance
- A/B test different ad variations

### Audience Management
- Create custom audiences from customer data
- Upload audience data (emails, phone numbers, etc.)
- Generate lookalike audiences
- Manage audience targeting

### Creative Management
- Create and manage ad creatives
- Upload images and videos
- Configure ad formats and placements
- Test creative performance

### Analytics and Insights
- Campaign performance metrics
- Ad set and ad level analytics  
- Conversion tracking and attribution
- Custom date range reporting

### Targeting Options
- Interest-based targeting
- Behavioral targeting
- Demographic targeting
- Geographic targeting
- Custom and lookalike audiences

## Installation

### Prerequisites
1. Meta Developer Account with advertising permissions
2. Meta Business Manager account
3. Meta app with Marketing API access

### Required Environment Variables
Set these environment variables in your AGiXT configuration:

```bash
# Meta App Credentials
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret
META_BUSINESS_ID=your_business_manager_id

# AGiXT Configuration  
APP_URI=your_agixt_base_url
```

### Required Python Packages
The extension uses standard libraries and requests, which should already be available in AGiXT.

## Configuration

### 1. Meta Developer Setup
1. Visit [Meta for Developers](https://developers.facebook.com/)
2. Create a new app or use existing app
3. Add "Marketing API" product to your app
4. Complete App Review process for advertising permissions
5. Get your App ID and App Secret

### 2. Business Manager Setup
1. Create a Business Manager account at [business.facebook.com](https://business.facebook.com/)
2. Add your ad accounts to Business Manager
3. Get your Business Manager ID from Settings > Business Info

### 3. AGiXT Agent Configuration
When creating an AGiXT agent, configure the Meta Ads extension with:

```json
{
  "META_APP_ID": "your_app_id",
  "META_APP_SECRET": "your_app_secret", 
  "META_BUSINESS_ID": "your_business_id"
}
```

## Usage Examples

### Basic Campaign Creation
```python
# Create a new campaign
result = await agent.execute_command(
    "Meta Ads - Create Campaign",
    {
        "ad_account_id": "act_123456789",
        "name": "Holiday Sale Campaign",
        "objective": "CONVERSIONS",
        "status": "PAUSED"
    }
)
```

### Get Campaign Insights
```python
# Get performance data for a campaign
insights = await agent.execute_command(
    "Meta Ads - Get Campaign Insights", 
    {
        "campaign_id": "campaign_123456789",
        "date_range": "last_30_days",
        "metrics": ["impressions", "clicks", "spend", "conversions"]
    }
)
```

### Create Custom Audience
```python
# Create a custom audience from customer emails
audience = await agent.execute_command(
    "Meta Ads - Create Custom Audience",
    {
        "ad_account_id": "act_123456789", 
        "name": "Customer Email List",
        "subtype": "CUSTOM",
        "description": "Existing customers for remarketing"
    }
)
```

### Upload Audience Data
```python
# Upload customer data to custom audience
upload_result = await agent.execute_command(
    "Meta Ads - Upload Audience Data",
    {
        "audience_id": "audience_123456789",
        "data_list": [
            {"email": "customer1@example.com"},
            {"email": "customer2@example.com"}
        ],
        "data_type": "email"
    }
)
```

## Available Commands

### Account Management
- **Meta Ads - Get Ad Accounts**: Retrieve all accessible ad accounts
- **Meta Ads - Get Pages**: Get Facebook pages for creative management

### Campaign Operations
- **Meta Ads - Create Campaign**: Create new advertising campaign
- **Meta Ads - Get Campaigns**: List campaigns with filtering options
- **Meta Ads - Update Campaign**: Modify campaign settings
- **Meta Ads - Delete Campaign**: Delete campaign
- **Meta Ads - Set Campaign Budget**: Update campaign budget
- **Meta Ads - Pause Campaign**: Pause active campaign
- **Meta Ads - Resume Campaign**: Resume paused campaign

### Ad Set Operations  
- **Meta Ads - Create Ad Set**: Create ad set with targeting
- **Meta Ads - Get Ad Sets**: List ad sets for campaign
- **Meta Ads - Update Ad Set**: Modify ad set configuration

### Ad Operations
- **Meta Ads - Create Ad**: Create individual ad
- **Meta Ads - Get Ads**: List ads for ad set
- **Meta Ads - Update Ad**: Modify ad settings

### Creative Management
- **Meta Ads - Create Ad Creative**: Create ad creative
- **Meta Ads - Get Ad Creatives**: List available creatives

### Audience Management
- **Meta Ads - Create Custom Audience**: Create custom audience
- **Meta Ads - Get Custom Audiences**: List custom audiences
- **Meta Ads - Upload Audience Data**: Add data to custom audience
- **Meta Ads - Create Lookalike Audience**: Generate lookalike audience

### Analytics and Insights
- **Meta Ads - Get Campaign Insights**: Campaign performance metrics
- **Meta Ads - Get Ad Set Insights**: Ad set performance data
- **Meta Ads - Get Ad Insights**: Individual ad performance
- **Meta Ads - Get Conversions**: Conversion tracking data
- **Meta Ads - Create Conversion Event**: Set up conversion tracking

### Targeting
- **Meta Ads - Get Targeting Options**: Browse available targeting options

## Authentication

The extension uses OAuth 2.0 authentication with Meta's Graph API. Users need to:

1. Grant permissions through Meta's OAuth flow
2. Extension automatically manages token refresh
3. Long-lived tokens are obtained for extended sessions

### Required Permissions
- `ads_management`: Create and manage ads
- `ads_read`: Read advertising data
- `business_management`: Access business accounts
- `pages_read_engagement`: Read page engagement
- `pages_manage_ads`: Manage page advertising
- `pages_show_list`: List accessible pages
- `read_insights`: Access analytics data
- `email`: Basic user information

## Error Handling

The extension includes comprehensive error handling:

- **Rate Limiting**: Automatic retry with exponential backoff
- **Token Expiration**: Automatic token refresh
- **API Errors**: Detailed error messages and logging
- **Network Issues**: Retry logic for transient failures

## Best Practices

### Budget Management
- Start with small daily budgets for testing
- Monitor spend regularly to avoid overspending
- Use campaign budget optimization when possible

### Audience Targeting
- Create detailed buyer personas
- Test different audience sizes and targeting options
- Use custom audiences for remarketing
- Generate lookalike audiences from high-value customers

### Creative Testing
- Run A/B tests with multiple ad creatives
- Test different ad formats and placements
- Monitor creative fatigue and refresh regularly
- Use Meta's creative best practices

### Performance Monitoring
- Set up conversion tracking from day one
- Monitor key metrics daily
- Use automated rules for budget adjustments
- Regular performance reporting and optimization

## Troubleshooting

### Common Issues

**Authentication Errors**
- Verify Meta app credentials are correct
- Ensure Business Manager ID is accurate
- Check that required permissions are granted
- Confirm app is approved for Marketing API

**API Rate Limits**
- Extension automatically handles rate limiting
- Consider reducing request frequency for large operations
- Use batch operations when available

**Budget and Billing Issues**
- Ensure ad account has valid payment method
- Check account spending limits
- Verify campaign budgets are set correctly

**Targeting Errors**
- Validate targeting parameters before creating ad sets
- Ensure audience sizes are within acceptable ranges
- Check geographic targeting restrictions

### Debugging

Enable detailed logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check AGiXT logs for detailed error information and API responses.

## Limitations

- Meta Marketing API has daily rate limits
- Some advanced features require app review approval
- Conversion tracking requires Meta Pixel implementation
- Custom audience matching rates vary by data quality
- Real-time reporting may have delays

## Security Considerations

- Store API credentials securely in environment variables
- Use HTTPS for all OAuth redirects
- Regularly rotate access tokens
- Monitor API usage for unusual activity
- Follow Meta's advertising policies and guidelines

## Support and Resources

- [Meta Marketing API Documentation](https://developers.facebook.com/docs/marketing-api/)
- [Meta Business Help Center](https://www.facebook.com/business/help)
- [Meta Developer Community](https://developers.facebook.com/community/)
- [AGiXT Documentation](https://github.com/Josh-XT/AGiXT)

## Contributing

To contribute improvements to this extension:

1. Fork the AGiXT repository
2. Create a feature branch
3. Make your changes following the existing patterns
4. Add tests for new functionality
5. Submit a pull request

## License

This extension is part of AGiXT and follows the same licensing terms. See the main AGiXT repository for license details.
