import os
import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth


class x(Extensions):
    """
    The X (Twitter) extension provides comprehensive integration with X (formerly Twitter) platform.
    This extension allows AI agents to:
    - Read tweets from the user's timeline
    - Post tweets and reply to tweets
    - Like and retweet content
    - Search tweets by keywords or hashtags
    - Manage follows and followers
    - Send and read direct messages

    The extension requires the user to be authenticated with X through OAuth.
    AI agents should use this when they need to interact with a user's X account
    for tasks like posting updates, engaging with content, or monitoring trends.
    """

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("X_ACCESS_TOKEN", None)
        self.x_client_id = getenv("X_CLIENT_ID")
        self.x_client_secret = getenv("X_CLIENT_SECRET")
        self.auth = None

        if self.x_client_id and self.x_client_secret:
            self.commands = {
                "X - Get Home Timeline": self.get_home_timeline,
                "X - Get User Timeline": self.get_user_timeline,
                "X - Post Tweet": self.post_tweet,
                "X - Reply to Tweet": self.reply_to_tweet,
                "X - Like Tweet": self.like_tweet,
                "X - Retweet": self.retweet,
                "X - Search Tweets": self.search_tweets,
                "X - Get Tweet Details": self.get_tweet_details,
                "X - Get User Details": self.get_user_details,
                "X - Follow User": self.follow_user,
                "X - Unfollow User": self.unfollow_user,
                "X - Get Followers": self.get_followers,
                "X - Get Following": self.get_following,
                "X - Send Direct Message": self.send_direct_message,
                "X - Get Direct Messages": self.get_direct_messages,
                "X - Get Trending Topics": self.get_trending_topics,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                    self.timezone = self.auth.get_timezone()
                except Exception as e:
                    logging.error(f"Error initializing X client: {str(e)}")

        self.media_dir = kwargs.get("conversation_directory", "./WORKSPACE/media")
        os.makedirs(self.media_dir, exist_ok=True)

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If the user endpoint fails, raises an exception indicating the user is not found.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="x")

        logging.info(f"Verifying user with token: {self.access_token}")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://api.x.com/2/users/me", headers=headers)
        logging.info(f"User verification response: {response.text}")

        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the token is valid "
                "with the correct scopes, and the user is properly signed in."
            )

    async def get_home_timeline(self, max_results=20):
        """
        Retrieves tweets from the user's home timeline.

        Args:
            max_results (int): Maximum number of tweets to retrieve

        Returns:
            list: List of tweet dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            params = {
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
                "expansions": "author_id,referenced_tweets.id",
                "user.fields": "name,username,profile_image_url",
            }

            response = requests.get(
                "https://api.x.com/2/timelines/home", headers=headers, params=params
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch home timeline: {response.text}")

            data = response.json()
            tweets = []
            users = {
                user["id"]: user for user in data.get("includes", {}).get("users", [])
            }

            for tweet in data.get("data", []):
                author = users.get(tweet["author_id"], {})
                tweets.append(
                    {
                        "id": tweet["id"],
                        "text": tweet["text"],
                        "created_at": tweet["created_at"],
                        "author_name": author.get("name", ""),
                        "author_username": author.get("username", ""),
                        "author_profile_image": author.get("profile_image_url", ""),
                        "likes": tweet["public_metrics"]["like_count"],
                        "retweets": tweet["public_metrics"]["retweet_count"],
                        "replies": tweet["public_metrics"]["reply_count"],
                        "quote_count": tweet["public_metrics"]["quote_count"],
                        "hashtags": [
                            tag["tag"]
                            for tag in tweet.get("entities", {}).get("hashtags", [])
                        ],
                        "is_reply": any(
                            ref["type"] == "replied_to"
                            for ref in tweet.get("referenced_tweets", [])
                        ),
                        "is_retweet": any(
                            ref["type"] == "retweeted"
                            for ref in tweet.get("referenced_tweets", [])
                        ),
                    }
                )

            return tweets

        except Exception as e:
            logging.error(f"Error retrieving home timeline: {str(e)}")
            return []

    async def get_user_timeline(self, username=None, user_id=None, max_results=20):
        """
        Retrieves tweets from a specific user's timeline.

        Args:
            username (str): Twitter username (without @)
            user_id (str): Twitter user ID (alternative to username)
            max_results (int): Maximum number of tweets to retrieve

        Returns:
            list: List of tweet dictionaries
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # First get the user ID if only username is provided
            if not user_id and username:
                user_response = requests.get(
                    f"https://api.x.com/2/users/by/username/{username}", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(f"Failed to find user: {user_response.text}")
                user_id = user_response.json()["data"]["id"]
            elif not user_id and not username:
                # Get authenticated user's ID
                user_response = requests.get(
                    "https://api.x.com/2/users/me", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(
                        f"Failed to get authenticated user: {user_response.text}"
                    )
                user_id = user_response.json()["data"]["id"]

            params = {
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
                "expansions": "author_id,referenced_tweets.id",
                "user.fields": "name,username,profile_image_url",
                "exclude": "retweets,replies",
            }

            response = requests.get(
                f"https://api.x.com/2/users/{user_id}/tweets",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch user timeline: {response.text}")

            data = response.json()
            tweets = []
            users = {
                user["id"]: user for user in data.get("includes", {}).get("users", [])
            }

            for tweet in data.get("data", []):
                author = users.get(tweet["author_id"], {})
                tweets.append(
                    {
                        "id": tweet["id"],
                        "text": tweet["text"],
                        "created_at": tweet["created_at"],
                        "author_name": author.get("name", ""),
                        "author_username": author.get("username", ""),
                        "author_profile_image": author.get("profile_image_url", ""),
                        "likes": tweet["public_metrics"]["like_count"],
                        "retweets": tweet["public_metrics"]["retweet_count"],
                        "replies": tweet["public_metrics"]["reply_count"],
                        "quote_count": tweet["public_metrics"]["quote_count"],
                        "hashtags": [
                            tag["tag"]
                            for tag in tweet.get("entities", {}).get("hashtags", [])
                        ],
                    }
                )

            return tweets

        except Exception as e:
            logging.error(f"Error retrieving user timeline: {str(e)}")
            return []

    async def post_tweet(self, text, media_paths=None, reply_to_id=None):
        """
        Posts a new tweet or replies to an existing tweet.

        Args:
            text (str): Tweet content
            media_paths (list): Optional list of paths to media files to attach
            reply_to_id (str): Optional ID of tweet to reply to

        Returns:
            dict: Response containing success status and tweet details
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            tweet_data = {"text": text}

            # Handle reply
            if reply_to_id:
                tweet_data["reply"] = {"in_reply_to_tweet_id": reply_to_id}

            # Handle media uploads
            if media_paths:
                media_ids = []
                for media_path in media_paths:
                    if os.path.exists(media_path):
                        # Upload media
                        media_headers = {
                            "Authorization": f"Bearer {self.access_token}",
                            "Content-Type": "multipart/form-data",
                        }
                        with open(media_path, "rb") as file:
                            media_response = requests.post(
                                "https://upload.x.com/1.1/media/upload.json",
                                headers=media_headers,
                                files={"media": file},
                            )
                            if media_response.status_code != 200:
                                raise Exception(
                                    f"Failed to upload media: {media_response.text}"
                                )
                            media_ids.append(media_response.json()["media_id_string"])

                if media_ids:
                    tweet_data["media"] = {"media_ids": media_ids}

            response = requests.post(
                "https://api.x.com/2/tweets", headers=headers, json=tweet_data
            )

            if response.status_code == 201:
                tweet_data = response.json()["data"]
                return {
                    "success": True,
                    "message": "Tweet posted successfully",
                    "tweet_id": tweet_data["id"],
                    "text": tweet_data.get("text", ""),
                }
            else:
                raise Exception(f"Failed to post tweet: {response.text}")

        except Exception as e:
            logging.error(f"Error posting tweet: {str(e)}")
            return {"success": False, "message": f"Failed to post tweet: {str(e)}"}

    async def reply_to_tweet(self, tweet_id, text, media_paths=None):
        """
        Replies to an existing tweet.

        Args:
            tweet_id (str): ID of the tweet to reply to
            text (str): Reply content
            media_paths (list): Optional list of paths to media files to attach

        Returns:
            dict: Response containing success status and tweet details
        """
        return await self.post_tweet(text, media_paths, reply_to_id=tweet_id)

    async def like_tweet(self, tweet_id):
        """
        Likes a specific tweet.

        Args:
            tweet_id (str): ID of the tweet to like

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get user ID
            user_response = requests.get(
                "https://api.x.com/2/users/me", headers=headers
            )
            if user_response.status_code != 200:
                raise Exception(f"Failed to get user ID: {user_response.text}")

            user_id = user_response.json()["data"]["id"]

            response = requests.post(
                f"https://api.x.com/2/users/{user_id}/likes",
                headers=headers,
                json={"tweet_id": tweet_id},
            )

            if response.status_code == 200:
                return {"success": True, "message": "Tweet liked successfully"}
            else:
                raise Exception(f"Failed to like tweet: {response.text}")

        except Exception as e:
            logging.error(f"Error liking tweet: {str(e)}")
            return {"success": False, "message": f"Failed to like tweet: {str(e)}"}

    async def retweet(self, tweet_id):
        """
        Retweets a specific tweet.

        Args:
            tweet_id (str): ID of the tweet to retweet

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get user ID
            user_response = requests.get(
                "https://api.x.com/2/users/me", headers=headers
            )
            if user_response.status_code != 200:
                raise Exception(f"Failed to get user ID: {user_response.text}")

            user_id = user_response.json()["data"]["id"]

            response = requests.post(
                f"https://api.x.com/2/users/{user_id}/retweets",
                headers=headers,
                json={"tweet_id": tweet_id},
            )

            if response.status_code == 200:
                return {"success": True, "message": "Tweet retweeted successfully"}
            else:
                raise Exception(f"Failed to retweet: {response.text}")

        except Exception as e:
            logging.error(f"Error retweeting: {str(e)}")
            return {"success": False, "message": f"Failed to retweet: {str(e)}"}

    async def search_tweets(self, query, max_results=20, recent_only=True):
        """
        Searches for tweets matching a query.

        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            recent_only (bool): Whether to return only recent tweets

        Returns:
            list: List of tweet dictionaries matching the query
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            params = {
                "query": query,
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
                "expansions": "author_id",
                "user.fields": "name,username,profile_image_url",
            }

            search_url = (
                "https://api.x.com/2/tweets/search/recent"
                if recent_only
                else "https://api.x.com/2/tweets/search/all"
            )

            response = requests.get(search_url, headers=headers, params=params)

            if response.status_code != 200:
                raise Exception(f"Failed to search tweets: {response.text}")

            data = response.json()
            tweets = []
            users = {
                user["id"]: user for user in data.get("includes", {}).get("users", [])
            }

            for tweet in data.get("data", []):
                author = users.get(tweet["author_id"], {})
                tweets.append(
                    {
                        "id": tweet["id"],
                        "text": tweet["text"],
                        "created_at": tweet["created_at"],
                        "author_name": author.get("name", ""),
                        "author_username": author.get("username", ""),
                        "author_profile_image": author.get("profile_image_url", ""),
                        "likes": tweet["public_metrics"]["like_count"],
                        "retweets": tweet["public_metrics"]["retweet_count"],
                        "replies": tweet["public_metrics"]["reply_count"],
                        "quote_count": tweet["public_metrics"]["quote_count"],
                        "hashtags": [
                            tag["tag"]
                            for tag in tweet.get("entities", {}).get("hashtags", [])
                        ],
                    }
                )

            return tweets

        except Exception as e:
            logging.error(f"Error searching tweets: {str(e)}")
            return []

    async def get_tweet_details(self, tweet_id):
        """
        Gets detailed information about a specific tweet.

        Args:
            tweet_id (str): ID of the tweet to retrieve

        Returns:
            dict: Tweet details including engagement metrics
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            params = {
                "tweet.fields": "created_at,public_metrics,entities,referenced_tweets,attachments,context_annotations",
                "expansions": "author_id,referenced_tweets.id,attachments.media_keys",
                "user.fields": "name,username,profile_image_url,description",
                "media.fields": "type,url,preview_image_url,duration_ms",
            }

            response = requests.get(
                f"https://api.x.com/2/tweets/{tweet_id}", headers=headers, params=params
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get tweet details: {response.text}")

            data = response.json()
            tweet = data["data"]
            users = {
                user["id"]: user for user in data.get("includes", {}).get("users", [])
            }
            author = users.get(tweet["author_id"], {})

            # Get referenced tweets
            referenced_tweets = {}
            if "referenced_tweets" in tweet:
                for ref in tweet["referenced_tweets"]:
                    for included_tweet in data.get("includes", {}).get("tweets", []):
                        if included_tweet["id"] == ref["id"]:
                            ref_author = users.get(included_tweet["author_id"], {})
                            referenced_tweets[ref["type"]] = {
                                "id": included_tweet["id"],
                                "text": included_tweet["text"],
                                "author_name": ref_author.get("name", ""),
                                "author_username": ref_author.get("username", ""),
                            }

            # Get media
            media = []
            if "media" in data.get("includes", {}):
                for m in data["includes"]["media"]:
                    media_item = {
                        "type": m["type"],
                        "url": m.get("url", m.get("preview_image_url", "")),
                    }
                    if "duration_ms" in m:
                        media_item["duration"] = (
                            m["duration_ms"] / 1000
                        )  # Convert to seconds
                    media.append(media_item)

            return {
                "id": tweet["id"],
                "text": tweet["text"],
                "created_at": tweet["created_at"],
                "author": {
                    "id": author.get("id", ""),
                    "name": author.get("name", ""),
                    "username": author.get("username", ""),
                    "profile_image": author.get("profile_image_url", ""),
                    "description": author.get("description", ""),
                },
                "metrics": {
                    "likes": tweet["public_metrics"]["like_count"],
                    "retweets": tweet["public_metrics"]["retweet_count"],
                    "replies": tweet["public_metrics"]["reply_count"],
                    "quote_count": tweet["public_metrics"]["quote_count"],
                },
                "hashtags": [
                    tag["tag"] for tag in tweet.get("entities", {}).get("hashtags", [])
                ],
                "mentions": [
                    mention["username"]
                    for mention in tweet.get("entities", {}).get("mentions", [])
                ],
                "urls": [
                    url["expanded_url"]
                    for url in tweet.get("entities", {}).get("urls", [])
                ],
                "referenced_tweets": referenced_tweets,
                "media": media,
                "context_annotations": tweet.get("context_annotations", []),
            }

        except Exception as e:
            logging.error(f"Error getting tweet details: {str(e)}")
            return {}

    async def get_user_details(self, username=None, user_id=None):
        """
        Gets detailed information about a specific user.

        Args:
            username (str): X username (without @)
            user_id (str): X user ID (alternative to username)

        Returns:
            dict: User profile details
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            if not user_id and not username:
                endpoint = "https://api.x.com/2/users/me"
            elif username:
                endpoint = f"https://api.x.com/2/users/by/username/{username}"
            else:
                endpoint = f"https://api.x.com/2/users/{user_id}"

            params = {
                "user.fields": "created_at,description,entities,id,location,name,pinned_tweet_id,profile_image_url,protected,public_metrics,url,username,verified,withheld"
            }

            response = requests.get(endpoint, headers=headers, params=params)

            if response.status_code != 200:
                raise Exception(f"Failed to get user details: {response.text}")

            user = response.json()["data"]

            return {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
                "description": user.get("description", ""),
                "location": user.get("location", ""),
                "profile_image": user.get("profile_image_url", ""),
                "verified": user.get("verified", False),
                "protected": user.get("protected", False),
                "created_at": user["created_at"],
                "metrics": {
                    "followers_count": user["public_metrics"]["followers_count"],
                    "following_count": user["public_metrics"]["following_count"],
                    "tweet_count": user["public_metrics"]["tweet_count"],
                    "listed_count": user["public_metrics"]["listed_count"],
                },
                "url": user.get("url", ""),
                "pinned_tweet_id": user.get("pinned_tweet_id", ""),
            }

        except Exception as e:
            logging.error(f"Error getting user details: {str(e)}")
            return {}

    async def follow_user(self, username=None, user_id=None):
        """
        Follows a user on X.

        Args:
            username (str): X username to follow (without @)
            user_id (str): X user ID to follow (alternative to username)

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get current user ID
            me_response = requests.get("https://api.x.com/2/users/me", headers=headers)
            if me_response.status_code != 200:
                raise Exception(f"Failed to get user ID: {me_response.text}")

            current_user_id = me_response.json()["data"]["id"]

            # Get target user ID if username is provided
            if not user_id and username:
                user_response = requests.get(
                    f"https://api.x.com/2/users/by/username/{username}", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(f"Failed to find user: {user_response.text}")
                user_id = user_response.json()["data"]["id"]

            if not user_id:
                raise Exception("Either username or user_id must be provided")

            response = requests.post(
                f"https://api.x.com/2/users/{current_user_id}/following",
                headers=headers,
                json={"target_user_id": user_id},
            )

            if response.status_code == 200:
                return {"success": True, "message": f"Successfully followed user"}
            else:
                raise Exception(f"Failed to follow user: {response.text}")

        except Exception as e:
            logging.error(f"Error following user: {str(e)}")
            return {"success": False, "message": f"Failed to follow user: {str(e)}"}

    async def unfollow_user(self, username=None, user_id=None):
        """
        Unfollows a user on X.

        Args:
            username (str): X username to unfollow (without @)
            user_id (str): X user ID to unfollow (alternative to username)

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get current user ID
            me_response = requests.get("https://api.x.com/2/users/me", headers=headers)
            if me_response.status_code != 200:
                raise Exception(f"Failed to get user ID: {me_response.text}")

            current_user_id = me_response.json()["data"]["id"]

            # Get target user ID if username is provided
            if not user_id and username:
                user_response = requests.get(
                    f"https://api.x.com/2/users/by/username/{username}", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(f"Failed to find user: {user_response.text}")
                user_id = user_response.json()["data"]["id"]

            if not user_id:
                raise Exception("Either username or user_id must be provided")

            response = requests.delete(
                f"https://api.x.com/2/users/{current_user_id}/following/{user_id}",
                headers=headers,
            )

            if response.status_code == 200:
                return {"success": True, "message": f"Successfully unfollowed user"}
            else:
                raise Exception(f"Failed to unfollow user: {response.text}")

        except Exception as e:
            logging.error(f"Error unfollowing user: {str(e)}")
            return {"success": False, "message": f"Failed to unfollow user: {str(e)}"}

    async def get_followers(self, username=None, user_id=None, max_results=20):
        """
        Gets a list of followers for a user.

        Args:
            username (str): X username (without @)
            user_id (str): X user ID (alternative to username)
            max_results (int): Maximum number of followers to retrieve

        Returns:
            list: List of follower user objects
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get user ID if only username is provided
            if not user_id and username:
                user_response = requests.get(
                    f"https://api.x.com/2/users/by/username/{username}", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(f"Failed to find user: {user_response.text}")
                user_id = user_response.json()["data"]["id"]
            elif not user_id and not username:
                # Get authenticated user's ID
                user_response = requests.get(
                    "https://api.x.com/2/users/me", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(
                        f"Failed to get authenticated user: {user_response.text}"
                    )
                user_id = user_response.json()["data"]["id"]

            params = {
                "max_results": max_results,
                "user.fields": "id,name,username,profile_image_url,description,public_metrics",
            }

            response = requests.get(
                f"https://api.x.com/2/users/{user_id}/followers",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch followers: {response.text}")

            followers = []
            for user in response.json()["data"]:
                followers.append(
                    {
                        "id": user["id"],
                        "name": user["name"],
                        "username": user["username"],
                        "profile_image": user.get("profile_image_url", ""),
                        "description": user.get("description", ""),
                        "followers_count": user["public_metrics"]["followers_count"],
                        "following_count": user["public_metrics"]["following_count"],
                    }
                )

            return followers

        except Exception as e:
            logging.error(f"Error getting followers: {str(e)}")
            return []

    async def get_following(self, username=None, user_id=None, max_results=20):
        """
        Gets a list of users that a specified user is following.

        Args:
            username (str): X username (without @)
            user_id (str): X user ID (alternative to username)
            max_results (int): Maximum number of users to retrieve

        Returns:
            list: List of user objects the specified user is following
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get user ID if only username is provided
            if not user_id and username:
                user_response = requests.get(
                    f"https://api.x.com/2/users/by/username/{username}", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(f"Failed to find user: {user_response.text}")
                user_id = user_response.json()["data"]["id"]
            elif not user_id and not username:
                # Get authenticated user's ID
                user_response = requests.get(
                    "https://api.x.com/2/users/me", headers=headers
                )
                if user_response.status_code != 200:
                    raise Exception(
                        f"Failed to get authenticated user: {user_response.text}"
                    )
                user_id = user_response.json()["data"]["id"]

            params = {
                "max_results": max_results,
                "user.fields": "id,name,username,profile_image_url,description,public_metrics",
            }

            response = requests.get(
                f"https://api.x.com/2/users/{user_id}/following",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch following: {response.text}")

            following = []
            for user in response.json()["data"]:
                following.append(
                    {
                        "id": user["id"],
                        "name": user["name"],
                        "username": user["username"],
                        "profile_image": user.get("profile_image_url", ""),
                        "description": user.get("description", ""),
                        "followers_count": user["public_metrics"]["followers_count"],
                        "following_count": user["public_metrics"]["following_count"],
                    }
                )

            return following

        except Exception as e:
            logging.error(f"Error getting following: {str(e)}")
            return []

    async def send_direct_message(self, recipient_id, text, media_paths=None):
        """
        Sends a direct message to a user.

        Args:
            recipient_id (str): ID of the user to send the message to
            text (str): Message content
            media_paths (list): Optional list of paths to media files to attach

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Get current user ID
            me_response = requests.get("https://api.x.com/2/users/me", headers=headers)
            if me_response.status_code != 200:
                raise Exception(f"Failed to get user ID: {me_response.text}")

            sender_id = me_response.json()["data"]["id"]

            message_data = {
                "event": {
                    "type": "message_create",
                    "message_create": {
                        "target": {"recipient_id": recipient_id},
                        "message_data": {"text": text},
                    },
                }
            }

            # Handle media attachments
            if media_paths:
                media_ids = []
                for media_path in media_paths:
                    if os.path.exists(media_path):
                        # Upload media
                        media_headers = {
                            "Authorization": f"Bearer {self.access_token}",
                            "Content-Type": "multipart/form-data",
                        }
                        with open(media_path, "rb") as file:
                            media_response = requests.post(
                                "https://upload.x.com/1.1/media/upload.json",
                                headers=media_headers,
                                files={"media": file},
                            )
                            if media_response.status_code != 200:
                                raise Exception(
                                    f"Failed to upload media: {media_response.text}"
                                )
                            media_ids.append(media_response.json()["media_id_string"])

                if media_ids:
                    message_data["event"]["message_create"]["message_data"][
                        "attachment"
                    ] = {
                        "type": "media",
                        "media": {
                            "id": media_ids[0]
                        },  # DMs support one media attachment at a time
                    }

            response = requests.post(
                "https://api.x.com/1.1/direct_messages/events/new.json",
                headers=headers,
                json=message_data,
            )

            if response.status_code == 200:
                return {"success": True, "message": "Direct message sent successfully"}
            else:
                raise Exception(f"Failed to send direct message: {response.text}")

        except Exception as e:
            logging.error(f"Error sending direct message: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to send direct message: {str(e)}",
            }

    async def get_direct_messages(self, max_results=20):
        """
        Retrieves direct messages for the authenticated user.

        Args:
            max_results (int): Maximum number of messages to retrieve

        Returns:
            list: List of direct message objects
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            params = {"count": max_results}

            response = requests.get(
                "https://api.x.com/1.1/direct_messages/events/list.json",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch direct messages: {response.text}")

            data = response.json()
            messages = []

            # Get user information for sender and recipient
            user_cache = {}

            for event in data.get("events", []):
                if event["type"] == "message_create":
                    message_data = event["message_create"]
                    sender_id = message_data["sender_id"]
                    recipient_id = message_data["target"]["recipient_id"]

                    # Get sender info if not in cache
                    if sender_id not in user_cache:
                        sender_response = requests.get(
                            f"https://api.x.com/2/users/{sender_id}",
                            headers=headers,
                            params={"user.fields": "name,username,profile_image_url"},
                        )
                        if sender_response.status_code == 200:
                            user_cache[sender_id] = sender_response.json()["data"]

                    # Get recipient info if not in cache
                    if recipient_id not in user_cache:
                        recipient_response = requests.get(
                            f"https://api.x.com/2/users/{recipient_id}",
                            headers=headers,
                            params={"user.fields": "name,username,profile_image_url"},
                        )
                        if recipient_response.status_code == 200:
                            user_cache[recipient_id] = recipient_response.json()["data"]

                    sender = user_cache.get(
                        sender_id,
                        {"username": f"user_{sender_id}", "name": "Unknown User"},
                    )
                    recipient = user_cache.get(
                        recipient_id,
                        {"username": f"user_{recipient_id}", "name": "Unknown User"},
                    )

                    # Build message object
                    message_obj = {
                        "id": event["id"],
                        "created_at": event["created_timestamp"],
                        "sender_id": sender_id,
                        "sender_username": sender.get("username", ""),
                        "sender_name": sender.get("name", ""),
                        "recipient_id": recipient_id,
                        "recipient_username": recipient.get("username", ""),
                        "recipient_name": recipient.get("name", ""),
                        "text": message_data["message_data"]["text"],
                    }

                    # Add media if present
                    if "attachment" in message_data["message_data"]:
                        attachment = message_data["message_data"]["attachment"]
                        if attachment["type"] == "media":
                            message_obj["media_id"] = attachment["media"]["id"]

                    messages.append(message_obj)

            return messages

        except Exception as e:
            logging.error(f"Error retrieving direct messages: {str(e)}")
            return []

    async def get_trending_topics(self, woeid=1, max_results=10):
        """
        Gets trending topics for a specific location.

        Args:
            woeid (int): Where On Earth ID (default: 1 for worldwide)
            max_results (int): Maximum number of trends to retrieve

        Returns:
            list: List of trending topic objects
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(
                f"https://api.x.com/1.1/trends/place.json?id={woeid}", headers=headers
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch trending topics: {response.text}")

            trends = []
            for trend in response.json()[0]["trends"][:max_results]:
                trends.append(
                    {
                        "name": trend["name"],
                        "url": trend["url"],
                        "tweet_volume": trend.get("tweet_volume", 0),
                        "promoted_content": trend.get("promoted_content", False),
                    }
                )

            return trends

        except Exception as e:
            logging.error(f"Error getting trending topics: {str(e)}")
            return []
