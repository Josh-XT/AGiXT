import tweepy
from Config import Config
from Commands import Commands

CFG = Config()


class twitter(Commands):
    def __init__(self):
        if CFG.TW_CONSUMER_KEY and CFG.TW_ACCESS_TOKEN:
            self.commands = {"Send Tweet": self.send_tweet}

    def send_tweet(tweet_text):
        # Authenticate to Twitter
        auth = tweepy.OAuthHandler(CFG.TW_CONSUMER_KEY, CFG.TW_CONSUMER_SECRET)
        auth.set_access_token(CFG.TW_ACCESS_TOKEN, CFG.TW_ACCESS_TOKEN_SECRET)

        # Create API object
        api = tweepy.API(auth)

        # Send tweet
        try:
            api.update_status(tweet_text)
            print("Tweet sent successfully!")
        except tweepy.TweepyException as e:
            print("Error sending tweet: {}".format(e.reason))
