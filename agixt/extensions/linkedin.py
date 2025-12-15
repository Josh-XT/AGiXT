import os
import logging
import requests
import base64
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException


"""
Required environment variables:

- LINKEDIN_CLIENT_ID: LinkedIn OAuth client ID
- LINKEDIN_CLIENT_SECRET: LinkedIn OAuth client secret

Required APIs

Create a LinkedIn App at https://www.linkedin.com/developers/apps
Add the following products to your app:
- Sign In with LinkedIn using OpenID Connect
- Share on LinkedIn
- Marketing Developer Platform (for company page access)

Required scopes for LinkedIn OAuth:
- openid (for OpenID Connect sign-in)
- profile (basic profile info)
- email (email address)
- w_member_social (post on behalf of user)
- r_organization_social (read company pages - requires Marketing Developer Platform)
- w_organization_social (post to company pages - requires Marketing Developer Platform)
- r_1st_connections_size (connection count)

Note: LinkedIn restricts certain APIs. Some features require partner program approval:
- Messaging API requires LinkedIn partnership
- Full connections list requires partnership
- Company page posting requires Marketing Developer Platform approval
"""

SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
]
# Additional scopes that require Marketing Developer Platform approval:
# "r_organization_social", "w_organization_social", "r_1st_connections_size"

AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
PKCE_REQUIRED = False


class LinkedInSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = getenv("LINKEDIN_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refresh the access token using the refresh token."""
        response = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logging.error(f"LinkedIn token refresh failed: {response.text}")
            raise Exception(f"LinkedIn token refresh failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            logging.error("No access_token in LinkedIn refresh response")
            raise Exception("No access_token in LinkedIn refresh response")

        return token_data

    def get_user_info(self):
        """Get user profile information using the userinfo endpoint."""
        uri = "https://api.linkedin.com/v2/userinfo"

        if not self.access_token:
            logging.error("No access token available")
            return {}

        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if response.status_code == 401:
            self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        try:
            data = response.json()
            # LinkedIn userinfo endpoint returns OpenID Connect standard claims
            first_name = data.get("given_name", "") or ""
            last_name = data.get("family_name", "") or ""
            email = data.get("email", "")

            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "sub": data.get("sub", ""),  # LinkedIn member ID (URN format)
                "picture": data.get("picture", ""),
            }
        except Exception as e:
            logging.error(f"Error parsing LinkedIn user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from LinkedIn",
            )


def sso(code, redirect_uri=None) -> LinkedInSSO:
    """Exchange authorization code for access token."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )

    response = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": getenv("LINKEDIN_CLIENT_ID"),
            "client_secret": getenv("LINKEDIN_CLIENT_SECRET"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        logging.error(f"Error getting LinkedIn access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token", "Not provided")

    return LinkedInSSO(access_token=access_token, refresh_token=refresh_token)


class linkedin(Extensions):
    """
    The LinkedIn extension provides integration with LinkedIn's platform for professional networking
    and marketing automation. This extension allows AI agents to:

    - Get user profile information
    - Create and publish posts (text, images, articles, documents)
    - Share content with specific visibility settings
    - Manage company page posts (requires Marketing Developer Platform approval)
    - Get post analytics and engagement metrics
    - Search for users and companies (limited by LinkedIn API restrictions)

    The extension requires the user to be authenticated with LinkedIn through OAuth.
    AI agents should use this when they need to interact with a user's LinkedIn account
    for tasks like posting content, sharing updates, or managing professional presence.

    Note: LinkedIn's API is more restrictive than other social platforms. Features like
    messaging, full connections access, and certain analytics require partnership approval.
    """

    CATEGORY = "Social & Communication"
    friendly_name = "LinkedIn"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("LINKEDIN_ACCESS_TOKEN", None)
        self.linkedin_client_id = getenv("LINKEDIN_CLIENT_ID")
        self.linkedin_client_secret = getenv("LINKEDIN_CLIENT_SECRET")
        self.auth = None

        if self.linkedin_client_id and self.linkedin_client_secret:
            self.commands = {
                "LinkedIn - Get My Profile": self.get_my_profile,
                "LinkedIn - Create Text Post": self.create_text_post,
                "LinkedIn - Create Image Post": self.create_image_post,
                "LinkedIn - Create Article Post": self.create_article_post,
                "LinkedIn - Create Document Post": self.create_document_post,
                "LinkedIn - Delete Post": self.delete_post,
                "LinkedIn - Get Post Analytics": self.get_post_analytics,
                "LinkedIn - Get My Posts": self.get_my_posts,
                "LinkedIn - Get User Profile": self.get_user_profile,
                "LinkedIn - Create Company Post": self.create_company_post,
                "LinkedIn - Get Company Pages": self.get_company_pages,
                "LinkedIn - Get Company Page Details": self.get_company_page_details,
                "LinkedIn - Comment on Post": self.comment_on_post,
                "LinkedIn - React to Post": self.react_to_post,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing LinkedIn client: {str(e)}")

        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        If the userinfo endpoint fails, raises an exception indicating the user is not found.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="linkedin")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"User not found or invalid token. Status: {response.status_code}, "
                f"Response: {response.text}. Ensure the token is valid "
                "with the correct scopes, and the user is properly signed in."
            )

    def _get_member_urn(self):
        """Get the authenticated user's LinkedIn URN (member ID)."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)

        if response.status_code != 200:
            raise Exception(f"Failed to get member URN: {response.text}")

        data = response.json()
        # The 'sub' field contains the member URN
        sub = data.get("sub", "")
        if sub:
            return f"urn:li:person:{sub}"
        raise Exception("Could not determine member URN")

    async def get_my_profile(self):
        """
        Gets the authenticated user's LinkedIn profile information.

        Returns:
            dict: User profile details including name, headline, profile picture, etc.
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            # Use userinfo endpoint for basic profile data
            response = requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers=headers,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get profile: {response.text}")

            data = response.json()

            return {
                "id": data.get("sub", ""),
                "first_name": data.get("given_name", ""),
                "last_name": data.get("family_name", ""),
                "email": data.get("email", ""),
                "profile_picture": data.get("picture", ""),
                "locale": data.get("locale", ""),
            }

        except Exception as e:
            logging.error(f"Error getting LinkedIn profile: {str(e)}")
            return {"error": str(e)}

    async def get_user_profile(self, profile_url=None, profile_id=None):
        """
        Gets public profile information for a LinkedIn user.

        Note: LinkedIn restricts access to other users' profiles. This may return limited data
        or require additional API permissions.

        Args:
            profile_url (str): LinkedIn profile URL (e.g., "https://linkedin.com/in/username")
            profile_id (str): LinkedIn member ID

        Returns:
            dict: User profile details (limited by API permissions)
        """
        try:
            self.verify_user()

            # LinkedIn's API for viewing other profiles is restricted
            # Most operations require partnership approval
            return {
                "message": "LinkedIn restricts access to other users' profiles through their API. "
                "To view profile information, please use the LinkedIn website directly. "
                "Full profile access requires LinkedIn Partnership Program approval."
            }

        except Exception as e:
            logging.error(f"Error getting LinkedIn user profile: {str(e)}")
            return {"error": str(e)}

    async def create_text_post(
        self, text, visibility="PUBLIC", feed_distribution="MAIN_FEED"
    ):
        """
        Creates a text-only post on LinkedIn.

        Args:
            text (str): The post content (max 3000 characters)
            visibility (str): Post visibility - "PUBLIC", "CONNECTIONS", or "LOGGED_IN"
            feed_distribution (str): Feed distribution - "MAIN_FEED" or "NONE"

        Returns:
            dict: Response containing success status and post details
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Truncate text if too long
            if len(text) > 3000:
                text = text[:2997] + "..."
                logging.warning("Post text truncated to 3000 characters")

            post_data = {
                "author": member_urn,
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": feed_distribution,
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "commentary": text,
            }

            response = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                json=post_data,
            )

            if response.status_code == 201:
                # Get the post ID from the response header
                post_id = response.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "message": "Post created successfully",
                    "post_id": post_id,
                }
            else:
                raise Exception(f"Failed to create post: {response.text}")

        except Exception as e:
            logging.error(f"Error creating LinkedIn post: {str(e)}")
            return {"success": False, "message": f"Failed to create post: {str(e)}"}

    async def create_image_post(
        self,
        text,
        image_path=None,
        image_url=None,
        image_title="",
        image_description="",
        visibility="PUBLIC",
    ):
        """
        Creates a post with an image on LinkedIn.

        Args:
            text (str): The post content (max 3000 characters)
            image_path (str): Local path to the image file
            image_url (str): URL of the image (alternative to image_path)
            image_title (str): Title/alt text for the image
            image_description (str): Description of the image
            visibility (str): Post visibility - "PUBLIC", "CONNECTIONS", or "LOGGED_IN"

        Returns:
            dict: Response containing success status and post details
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Step 1: Initialize the image upload
            init_data = {
                "initializeUploadRequest": {
                    "owner": member_urn,
                }
            }

            init_response = requests.post(
                "https://api.linkedin.com/rest/images?action=initializeUpload",
                headers=headers,
                json=init_data,
            )

            if init_response.status_code != 200:
                raise Exception(
                    f"Failed to initialize image upload: {init_response.text}"
                )

            upload_data = init_response.json()["value"]
            upload_url = upload_data["uploadUrl"]
            image_urn = upload_data["image"]

            # Step 2: Upload the image
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_data = f.read()
            elif image_url:
                img_response = requests.get(image_url)
                if img_response.status_code != 200:
                    raise Exception(f"Failed to download image from URL: {image_url}")
                image_data = img_response.content
            else:
                raise Exception("Either image_path or image_url must be provided")

            upload_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            upload_response = requests.put(
                upload_url,
                headers=upload_headers,
                data=image_data,
            )

            if upload_response.status_code not in [200, 201]:
                raise Exception(f"Failed to upload image: {upload_response.text}")

            # Step 3: Create the post with the image
            if len(text) > 3000:
                text = text[:2997] + "..."

            post_data = {
                "author": member_urn,
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "commentary": text,
                "content": {
                    "media": {
                        "title": image_title,
                        "id": image_urn,
                    }
                },
            }

            if image_description:
                post_data["content"]["media"]["altText"] = image_description

            response = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                json=post_data,
            )

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "message": "Image post created successfully",
                    "post_id": post_id,
                    "image_urn": image_urn,
                }
            else:
                raise Exception(f"Failed to create image post: {response.text}")

        except Exception as e:
            logging.error(f"Error creating LinkedIn image post: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create image post: {str(e)}",
            }

    async def create_article_post(
        self,
        text,
        article_url,
        article_title="",
        article_description="",
        visibility="PUBLIC",
    ):
        """
        Creates a post sharing an article/link on LinkedIn.

        Args:
            text (str): The post content/commentary (max 3000 characters)
            article_url (str): URL of the article to share
            article_title (str): Title for the article preview
            article_description (str): Description for the article preview
            visibility (str): Post visibility - "PUBLIC", "CONNECTIONS", or "LOGGED_IN"

        Returns:
            dict: Response containing success status and post details
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            if len(text) > 3000:
                text = text[:2997] + "..."

            post_data = {
                "author": member_urn,
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "commentary": text,
                "content": {
                    "article": {
                        "source": article_url,
                    }
                },
            }

            if article_title:
                post_data["content"]["article"]["title"] = article_title
            if article_description:
                post_data["content"]["article"]["description"] = article_description

            response = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                json=post_data,
            )

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "message": "Article post created successfully",
                    "post_id": post_id,
                }
            else:
                raise Exception(f"Failed to create article post: {response.text}")

        except Exception as e:
            logging.error(f"Error creating LinkedIn article post: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create article post: {str(e)}",
            }

    async def create_document_post(
        self,
        text,
        document_path,
        document_title="",
        document_description="",
        visibility="PUBLIC",
    ):
        """
        Creates a post with a document (PDF, PPT, DOC) on LinkedIn.

        Args:
            text (str): The post content (max 3000 characters)
            document_path (str): Local path to the document file
            document_title (str): Title for the document
            document_description (str): Description of the document
            visibility (str): Post visibility - "PUBLIC", "CONNECTIONS", or "LOGGED_IN"

        Returns:
            dict: Response containing success status and post details
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            if not os.path.exists(document_path):
                raise Exception(f"Document file not found: {document_path}")

            # Step 1: Initialize the document upload
            init_data = {
                "initializeUploadRequest": {
                    "owner": member_urn,
                }
            }

            init_response = requests.post(
                "https://api.linkedin.com/rest/documents?action=initializeUpload",
                headers=headers,
                json=init_data,
            )

            if init_response.status_code != 200:
                raise Exception(
                    f"Failed to initialize document upload: {init_response.text}"
                )

            upload_data = init_response.json()["value"]
            upload_url = upload_data["uploadUrl"]
            document_urn = upload_data["document"]

            # Step 2: Upload the document
            with open(document_path, "rb") as f:
                document_data = f.read()

            upload_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }

            upload_response = requests.put(
                upload_url,
                headers=upload_headers,
                data=document_data,
            )

            if upload_response.status_code not in [200, 201]:
                raise Exception(f"Failed to upload document: {upload_response.text}")

            # Step 3: Create the post with the document
            if len(text) > 3000:
                text = text[:2997] + "..."

            post_data = {
                "author": member_urn,
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "commentary": text,
                "content": {
                    "media": {
                        "title": document_title or os.path.basename(document_path),
                        "id": document_urn,
                    }
                },
            }

            if document_description:
                post_data["content"]["media"]["altText"] = document_description

            response = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                json=post_data,
            )

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "message": "Document post created successfully",
                    "post_id": post_id,
                    "document_urn": document_urn,
                }
            else:
                raise Exception(f"Failed to create document post: {response.text}")

        except Exception as e:
            logging.error(f"Error creating LinkedIn document post: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create document post: {str(e)}",
            }

    async def delete_post(self, post_id):
        """
        Deletes a post from LinkedIn.

        Args:
            post_id (str): The ID/URN of the post to delete

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure post_id is properly formatted
            if not post_id.startswith("urn:li:"):
                post_id = f"urn:li:share:{post_id}"

            response = requests.delete(
                f"https://api.linkedin.com/rest/posts/{post_id}",
                headers=headers,
            )

            if response.status_code == 204:
                return {
                    "success": True,
                    "message": "Post deleted successfully",
                }
            else:
                raise Exception(f"Failed to delete post: {response.text}")

        except Exception as e:
            logging.error(f"Error deleting LinkedIn post: {str(e)}")
            return {"success": False, "message": f"Failed to delete post: {str(e)}"}

    async def get_post_analytics(self, post_id):
        """
        Gets analytics/engagement metrics for a specific post.

        Note: Detailed analytics require additional API permissions and may be limited.

        Args:
            post_id (str): The ID/URN of the post

        Returns:
            dict: Post analytics including likes, comments, shares, impressions
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure post_id is properly formatted
            if not post_id.startswith("urn:li:"):
                post_id = f"urn:li:share:{post_id}"

            # Get social actions (likes, comments, etc.)
            response = requests.get(
                f"https://api.linkedin.com/rest/socialActions/{post_id}",
                headers=headers,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get post analytics: {response.text}")

            data = response.json()

            return {
                "post_id": post_id,
                "likes_count": data.get("likesSummary", {}).get("totalLikes", 0),
                "comments_count": data.get("commentsSummary", {}).get(
                    "totalFirstLevelComments", 0
                ),
                "shares_count": (
                    data.get("sharesSummary", {}).get("totalShares", 0)
                    if "sharesSummary" in data
                    else 0
                ),
            }

        except Exception as e:
            logging.error(f"Error getting LinkedIn post analytics: {str(e)}")
            return {"error": str(e)}

    async def get_my_posts(self, max_results=20):
        """
        Gets the authenticated user's recent posts.

        Args:
            max_results (int): Maximum number of posts to retrieve

        Returns:
            list: List of post objects with engagement metrics
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # URL encode the URN for the query parameter
            encoded_urn = requests.utils.quote(member_urn, safe="")

            response = requests.get(
                f"https://api.linkedin.com/rest/posts?author={encoded_urn}&q=author&count={max_results}",
                headers=headers,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get posts: {response.text}")

            data = response.json()
            posts = []

            for post in data.get("elements", []):
                post_obj = {
                    "id": post.get("id", ""),
                    "created_at": post.get("createdAt", ""),
                    "last_modified_at": post.get("lastModifiedAt", ""),
                    "text": post.get("commentary", ""),
                    "visibility": post.get("visibility", ""),
                    "lifecycle_state": post.get("lifecycleState", ""),
                }

                # Add content info if present
                if "content" in post:
                    content = post["content"]
                    if "article" in content:
                        post_obj["content_type"] = "article"
                        post_obj["article_url"] = content["article"].get("source", "")
                    elif "media" in content:
                        post_obj["content_type"] = "media"
                        post_obj["media_id"] = content["media"].get("id", "")
                else:
                    post_obj["content_type"] = "text"

                posts.append(post_obj)

            return posts

        except Exception as e:
            logging.error(f"Error getting LinkedIn posts: {str(e)}")
            return []

    async def get_company_pages(self):
        """
        Gets company pages that the authenticated user administers.

        Note: This requires Marketing Developer Platform approval.

        Returns:
            list: List of company pages the user can manage
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            response = requests.get(
                "https://api.linkedin.com/rest/organizationAcls?q=roleAssignee",
                headers=headers,
            )

            if response.status_code == 403:
                return {
                    "message": "Access to company pages requires Marketing Developer Platform approval. "
                    "Please apply for access at https://www.linkedin.com/developers/apps"
                }

            if response.status_code != 200:
                raise Exception(f"Failed to get company pages: {response.text}")

            data = response.json()
            organizations = []

            for acl in data.get("elements", []):
                org_urn = acl.get("organization", "")
                role = acl.get("role", "")

                # Get organization details
                org_response = requests.get(
                    f"https://api.linkedin.com/rest/organizations/{org_urn}",
                    headers=headers,
                )

                if org_response.status_code == 200:
                    org_data = org_response.json()
                    organizations.append(
                        {
                            "id": org_urn,
                            "name": org_data.get("localizedName", ""),
                            "role": role,
                            "vanity_name": org_data.get("vanityName", ""),
                        }
                    )
                else:
                    organizations.append(
                        {
                            "id": org_urn,
                            "role": role,
                        }
                    )

            return organizations

        except Exception as e:
            logging.error(f"Error getting LinkedIn company pages: {str(e)}")
            return {"error": str(e)}

    async def get_company_page_details(self, organization_id):
        """
        Gets details for a specific company page.

        Note: This requires Marketing Developer Platform approval.

        Args:
            organization_id (str): The organization ID/URN

        Returns:
            dict: Company page details
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure organization_id is properly formatted
            if not organization_id.startswith("urn:li:"):
                organization_id = f"urn:li:organization:{organization_id}"

            response = requests.get(
                f"https://api.linkedin.com/rest/organizations/{organization_id}",
                headers=headers,
            )

            if response.status_code == 403:
                return {
                    "message": "Access to company pages requires Marketing Developer Platform approval."
                }

            if response.status_code != 200:
                raise Exception(f"Failed to get company details: {response.text}")

            data = response.json()

            return {
                "id": data.get("id", ""),
                "name": data.get("localizedName", ""),
                "vanity_name": data.get("vanityName", ""),
                "description": data.get("localizedDescription", ""),
                "website": data.get("localizedWebsite", ""),
                "industry": data.get("industries", []),
                "company_size": data.get("staffCountRange", ""),
                "headquarters": data.get("locations", []),
                "logo_url": (
                    data.get("logoV2", {})
                    .get("original~", {})
                    .get("elements", [{}])[0]
                    .get("identifiers", [{}])[0]
                    .get("identifier", "")
                    if data.get("logoV2")
                    else ""
                ),
            }

        except Exception as e:
            logging.error(f"Error getting LinkedIn company details: {str(e)}")
            return {"error": str(e)}

    async def create_company_post(
        self,
        organization_id,
        text,
        visibility="PUBLIC",
        feed_distribution="MAIN_FEED",
    ):
        """
        Creates a post on a company page.

        Note: This requires Marketing Developer Platform approval and admin access to the company page.

        Args:
            organization_id (str): The organization ID/URN
            text (str): The post content (max 3000 characters)
            visibility (str): Post visibility - "PUBLIC" or "LOGGED_IN"
            feed_distribution (str): Feed distribution - "MAIN_FEED" or "NONE"

        Returns:
            dict: Response containing success status and post details
        """
        try:
            self.verify_user()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure organization_id is properly formatted
            if not organization_id.startswith("urn:li:"):
                organization_id = f"urn:li:organization:{organization_id}"

            if len(text) > 3000:
                text = text[:2997] + "..."

            post_data = {
                "author": organization_id,
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": feed_distribution,
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "commentary": text,
            }

            response = requests.post(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                json=post_data,
            )

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                return {
                    "success": True,
                    "message": "Company post created successfully",
                    "post_id": post_id,
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": "Access denied. Ensure you have admin access to the company page "
                    "and that your app has Marketing Developer Platform approval.",
                }
            else:
                raise Exception(f"Failed to create company post: {response.text}")

        except Exception as e:
            logging.error(f"Error creating LinkedIn company post: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create company post: {str(e)}",
            }

    async def comment_on_post(self, post_id, text):
        """
        Adds a comment to a LinkedIn post.

        Args:
            post_id (str): The ID/URN of the post to comment on
            text (str): The comment text

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure post_id is properly formatted
            if not post_id.startswith("urn:li:"):
                post_id = f"urn:li:share:{post_id}"

            comment_data = {
                "actor": member_urn,
                "message": {
                    "text": text,
                },
            }

            response = requests.post(
                f"https://api.linkedin.com/rest/socialActions/{post_id}/comments",
                headers=headers,
                json=comment_data,
            )

            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "message": "Comment added successfully",
                }
            else:
                raise Exception(f"Failed to add comment: {response.text}")

        except Exception as e:
            logging.error(f"Error commenting on LinkedIn post: {str(e)}")
            return {"success": False, "message": f"Failed to add comment: {str(e)}"}

    async def react_to_post(self, post_id, reaction_type="LIKE"):
        """
        Adds a reaction to a LinkedIn post.

        Args:
            post_id (str): The ID/URN of the post to react to
            reaction_type (str): Type of reaction - "LIKE", "CELEBRATE", "LOVE", "INSIGHTFUL", "FUNNY", "SUPPORT"

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()
            member_urn = self._get_member_urn()

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            }

            # Ensure post_id is properly formatted
            if not post_id.startswith("urn:li:"):
                post_id = f"urn:li:share:{post_id}"

            # Validate reaction type
            valid_reactions = [
                "LIKE",
                "CELEBRATE",
                "LOVE",
                "INSIGHTFUL",
                "FUNNY",
                "SUPPORT",
            ]
            reaction_type = reaction_type.upper()
            if reaction_type not in valid_reactions:
                reaction_type = "LIKE"

            reaction_data = {
                "actor": member_urn,
                "reactionType": reaction_type,
            }

            response = requests.post(
                f"https://api.linkedin.com/rest/socialActions/{post_id}/likes",
                headers=headers,
                json=reaction_data,
            )

            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "message": f"Reacted with {reaction_type} successfully",
                }
            else:
                raise Exception(f"Failed to add reaction: {response.text}")

        except Exception as e:
            logging.error(f"Error reacting to LinkedIn post: {str(e)}")
            return {"success": False, "message": f"Failed to add reaction: {str(e)}"}
