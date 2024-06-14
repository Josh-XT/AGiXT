# FatSecret

## Required environment variables

- `FATSECRET_CLIENT_ID`: FatSecret OAuth client ID
- `FATSECRET_CLIENT_SECRET`: FatSecret OAuth client secret

Ensure that these environment variables are added to your `.env` file.

## Required APIs

To use FatSecret's services, you need to register your application and obtain client credentials by following these steps:

1. Go to the [FatSecret Platform](https://platform.fatsecret.com/api/).
2. Click on "Sign Up" to create an account or log in if you already have one.
3. Once logged in, create a new application to get your `client_id` and `client_secret`.

## Setting up your environment variables

After acquiring your `FATSECRET_CLIENT_ID` and `FATSECRET_CLIENT_SECRET`, add them to your `.env` file like this:

```plaintext
FATSECRET_CLIENT_ID=your_fatsecret_client_id
FATSECRET_CLIENT_SECRET=your_fatsecret_client_secret
```
