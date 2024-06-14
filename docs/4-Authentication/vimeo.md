# Vimeo

## Required Environment Variables

To use Vimeo's OAuth system, you need to set up the following environment variables in your `.env` file:

- `VIMEO_CLIENT_ID`: Vimeo OAuth client ID
- `VIMEO_CLIENT_SECRET`: Vimeo OAuth client secret

## Required APIs

Ensure you have the necessary APIs enabled in Vimeo's developer platform. Follow these steps to obtain your `VIMEO_CLIENT_ID` and `VIMEO_CLIENT_SECRET`:

1. **Create a Vimeo Developer Account**: If you don't have one, you'll need to create a Vimeo developer account at [Vimeo Developer](https://developer.vimeo.com/).
2. **Create an App**: Go to your [My Apps](https://developer.vimeo.com/apps) page and create a new app. You will be given a `Client ID` and `Client Secret` which you need to copy and save.
3. **Set Up Scopes**: Ensure that your app has the following scopes enabled:
    - `public`: Access public videos and account details.
    - `private`: Access private videos.
    - `video_files`: Access video files.

4. **Add Environment Variables**: Copy your `VIMEO_CLIENT_ID` and `VIMEO_CLIENT_SECRET` into your `.env` file.

## Required Scopes for Vimeo OAuth

To ensure that your application can access the necessary Vimeo resources, the following scopes must be enabled:

- `public`
- `private`
- `video_files`
