# Keycloak Single Sign-On (SSO) Integration

This script facilitates Single Sign-On (SSO) integration with Keycloak by enabling seamless user authentication and retrieval of user information using OAuth 2.0.

## Required Environment Variables

Before running the `keycloak.py` script, ensure you have the following environment variables set up:

- `KEYCLOAK_CLIENT_ID`: Keycloak OAuth client ID
- `KEYCLOAK_CLIENT_SECRET`: Keycloak OAuth client secret
- `KEYCLOAK_REALM`: Name of the Keycloak realm
- `KEYCLOAK_SERVER_URL`: Base URL of the Keycloak server

These variables can typically be added to your `.env` file.

## Required Scopes for Keycloak SSO

- `openid`
- `email`
- `profile`
