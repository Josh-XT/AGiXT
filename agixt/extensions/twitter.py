try:
    import tweepy
except ImportError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "tweepy"])
    import tweepy
from Extensions import Extensions
import logging


class twitter(Extensions):
    def __init__(
        self,
        TW_CONSUMER_KEY: str = "",
        TW_CONSUMER_SECRET: str = "",
        TW_ACCESS_TOKEN: str = "",
        TW_ACCESS_TOKEN_SECRET: str = "",
        **kwargs
    ):
        self.TW_CONSUMER_KEY = TW_CONSUMER_KEY
        self.TW_CONSUMER_SECRET = TW_CONSUMER_SECRET
        self.TW_ACCESS_TOKEN = TW_ACCESS_TOKEN
        self.TW_ACCESS_TOKEN_SECRET = TW_ACCESS_TOKEN_SECRET
        if self.TW_CONSUMER_KEY and self.TW_ACCESS_TOKEN:
            self.commands = {"Send Tweet": self.send_tweet}

    async def send_tweet(self, tweet_text):
        # Authenticate to Twitter
        auth = tweepy.OAuthHandler(self.TW_CONSUMER_KEY, self.TW_CONSUMER_SECRET)
        auth.set_access_token(self.TW_ACCESS_TOKEN, self.TW_ACCESS_TOKEN_SECRET)

        # Create API object
        api = tweepy.API(auth)

        # Send tweet
        try:
            api.update_status(tweet_text)
            logging.info("Tweet sent successfully!")
        except tweepy.TweepyException as e:
            logging.info("Error sending tweet: {}".format(e.reason))
