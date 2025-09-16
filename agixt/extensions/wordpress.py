import logging
import json
from datetime import datetime
from typing import List, Dict, Optional, Union
from Extensions import Extensions

try:
    import requests
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from requests.auth import HTTPBasicAuth
except ImportError:
    from requests.auth import HTTPBasicAuth

try:
    import base64
except ImportError:
    import base64


class wordpress(Extensions):
    """
    The WordPress extension for AGiXT enables you to interact with WordPress websites through the WordPress REST API.
    This extension provides comprehensive functionality for managing posts, pages, users, media, categories, tags, and comments.
    """

    CATEGORY = "Productivity"

    def __init__(
        self,
        WORDPRESS_SITE_URL: str = "",
        WORDPRESS_USERNAME: str = "",
        WORDPRESS_APPLICATION_PASSWORD: str = "",
        **kwargs,
    ):
        """
        Initialize WordPress extension.

        Args:
            WORDPRESS_SITE_URL (str): Base URL of the WordPress site (e.g., https://example.com)
            WORDPRESS_USERNAME (str): WordPress username for authentication
            WORDPRESS_APPLICATION_PASSWORD (str): WordPress application password (not regular password)
        """
        self.site_url = WORDPRESS_SITE_URL.rstrip("/")
        self.username = WORDPRESS_USERNAME
        self.app_password = WORDPRESS_APPLICATION_PASSWORD
        self.api_base = f"{self.site_url}/wp-json/wp/v2"

        # Setup authentication
        self.auth = (
            HTTPBasicAuth(self.username, self.app_password)
            if self.username and self.app_password
            else None
        )

        # Setup session with common headers
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        if self.auth:
            self.session.auth = self.auth

        self.commands = {
            # Posts Management
            "Create WordPress Post": self.create_post,
            "Update WordPress Post": self.update_post,
            "Get WordPress Post": self.get_post,
            "List WordPress Posts": self.list_posts,
            "Delete WordPress Post": self.delete_post,
            "Publish WordPress Post": self.publish_post,
            "Schedule WordPress Post": self.schedule_post,
            # Pages Management
            "Create WordPress Page": self.create_page,
            "Update WordPress Page": self.update_page,
            "Get WordPress Page": self.get_page,
            "List WordPress Pages": self.list_pages,
            "Delete WordPress Page": self.delete_page,
            # Media Management
            "Upload WordPress Media": self.upload_media,
            "Get WordPress Media": self.get_media,
            "List WordPress Media": self.list_media,
            "Delete WordPress Media": self.delete_media,
            # Categories and Tags
            "Create WordPress Category": self.create_category,
            "List WordPress Categories": self.list_categories,
            "Create WordPress Tag": self.create_tag,
            "List WordPress Tags": self.list_tags,
            # Comments Management
            "Get WordPress Comments": self.get_comments,
            "Moderate WordPress Comment": self.moderate_comment,
            "Reply to WordPress Comment": self.reply_to_comment,
            # Users Management
            "List WordPress Users": self.list_users,
            "Get WordPress User": self.get_user,
            "Create WordPress User": self.create_user,
            # Site Information
            "Get WordPress Site Info": self.get_site_info,
            "Get WordPress Site Statistics": self.get_site_statistics,
            # SEO and Analytics
            "Analyze WordPress Post SEO": self.analyze_post_seo,
            "Get WordPress Site Health": self.get_site_health,
            # Content Management
            "Search WordPress Content": self.search_content,
            "Bulk Update WordPress Posts": self.bulk_update_posts,
        }

    def _make_request(
        self, method: str, endpoint: str, data: dict = None, params: dict = None
    ) -> dict:
        """
        Make authenticated request to WordPress API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (relative to wp-json/wp/v2)
            data: Request payload for POST/PUT requests
            params: Query parameters

        Returns:
            dict: API response data
        """
        url = f"{self.api_base}/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, params=params)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Handle empty responses
            if response.status_code == 204 or not response.text:
                return {"success": True}

            return response.json()

        except requests.exceptions.RequestException as e:
            logging.error(f"WordPress API request failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    return {
                        "error": error_data.get("message", str(e)),
                        "code": error_data.get("code", e.response.status_code),
                    }
                except:
                    return {"error": str(e), "status_code": e.response.status_code}
            return {"error": str(e)}

    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        excerpt: str = "",
        categories: List[str] = None,
        tags: List[str] = None,
        featured_media: int = None,
    ) -> str:
        """
        Create a new WordPress post.

        Args:
            title (str): Post title
            content (str): Post content (HTML allowed)
            status (str): Post status (draft, publish, private, future)
            excerpt (str): Post excerpt
            categories (List[str]): List of category names
            tags (List[str]): List of tag names
            featured_media (int): Featured image media ID

        Returns:
            str: JSON string with post creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        post_data = {
            "title": title,
            "content": content,
            "status": status,
            "excerpt": excerpt,
        }

        if featured_media:
            post_data["featured_media"] = featured_media

        # Handle categories
        if categories:
            category_ids = []
            for cat_name in categories:
                cat_response = await self.create_category(cat_name)
                cat_data = json.loads(cat_response)
                if not cat_data.get("error"):
                    category_ids.append(cat_data.get("id"))
            if category_ids:
                post_data["categories"] = category_ids

        # Handle tags
        if tags:
            tag_ids = []
            for tag_name in tags:
                tag_response = await self.create_tag(tag_name)
                tag_data = json.loads(tag_response)
                if not tag_data.get("error"):
                    tag_ids.append(tag_data.get("id"))
            if tag_ids:
                post_data["tags"] = tag_ids

        result = self._make_request("POST", "posts", data=post_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "post_id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "status": result.get("status"),
                "link": result.get("link"),
                "date": result.get("date"),
            }
        )

    async def update_post(
        self,
        post_id: int,
        title: str = None,
        content: str = None,
        status: str = None,
        excerpt: str = None,
    ) -> str:
        """
        Update an existing WordPress post.

        Args:
            post_id (int): Post ID to update
            title (str): New post title (optional)
            content (str): New post content (optional)
            status (str): New post status (optional)
            excerpt (str): New post excerpt (optional)

        Returns:
            str: JSON string with update result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        update_data = {}
        if title is not None:
            update_data["title"] = title
        if content is not None:
            update_data["content"] = content
        if status is not None:
            update_data["status"] = status
        if excerpt is not None:
            update_data["excerpt"] = excerpt

        if not update_data:
            return json.dumps({"error": "No update data provided"})

        result = self._make_request("PUT", f"posts/{post_id}", data=update_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "post_id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "status": result.get("status"),
                "modified": result.get("modified"),
            }
        )

    async def get_post(self, post_id: int) -> str:
        """
        Get a WordPress post by ID.

        Args:
            post_id (int): Post ID to retrieve

        Returns:
            str: JSON string with post data
        """
        result = self._make_request("GET", f"posts/{post_id}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "content": result.get("content", {}).get("rendered"),
                "excerpt": result.get("excerpt", {}).get("rendered"),
                "status": result.get("status"),
                "author": result.get("author"),
                "date": result.get("date"),
                "modified": result.get("modified"),
                "link": result.get("link"),
                "categories": result.get("categories", []),
                "tags": result.get("tags", []),
            }
        )

    async def list_posts(
        self,
        per_page: int = 10,
        page: int = 1,
        status: str = "any",
        search: str = None,
        author: int = None,
    ) -> str:
        """
        List WordPress posts with optional filtering.

        Args:
            per_page (int): Number of posts per page (1-100)
            page (int): Page number
            status (str): Post status filter (publish, draft, private, any)
            search (str): Search term
            author (int): Author ID filter

        Returns:
            str: JSON string with posts list
        """
        params = {"per_page": min(per_page, 100), "page": page, "status": status}

        if search:
            params["search"] = search
        if author:
            params["author"] = author

        result = self._make_request("GET", "posts", params=params)

        if result.get("error"):
            return json.dumps(result)

        posts = []
        for post in result:
            posts.append(
                {
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered"),
                    "excerpt": post.get("excerpt", {}).get("rendered"),
                    "status": post.get("status"),
                    "author": post.get("author"),
                    "date": post.get("date"),
                    "link": post.get("link"),
                }
            )

        return json.dumps({"posts": posts, "total_posts": len(posts)})

    async def delete_post(self, post_id: int, force: bool = False) -> str:
        """
        Delete a WordPress post.

        Args:
            post_id (int): Post ID to delete
            force (bool): Whether to permanently delete (bypass trash)

        Returns:
            str: JSON string with deletion result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        params = {"force": force}
        result = self._make_request("DELETE", f"posts/{post_id}", params=params)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps({"success": True, "deleted": True, "post_id": post_id})

    async def publish_post(self, post_id: int) -> str:
        """
        Publish a WordPress post (change status to published).

        Args:
            post_id (int): Post ID to publish

        Returns:
            str: JSON string with publish result
        """
        return await self.update_post(post_id, status="publish")

    async def schedule_post(self, post_id: int, publish_date: str) -> str:
        """
        Schedule a WordPress post for future publication.

        Args:
            post_id (int): Post ID to schedule
            publish_date (str): Publication date in ISO format (YYYY-MM-DDTHH:MM:SS)

        Returns:
            str: JSON string with scheduling result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        update_data = {"status": "future", "date": publish_date}

        result = self._make_request("PUT", f"posts/{post_id}", data=update_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "post_id": result.get("id"),
                "status": result.get("status"),
                "scheduled_date": result.get("date"),
            }
        )

    async def create_page(
        self, title: str, content: str, status: str = "draft", parent: int = None
    ) -> str:
        """
        Create a new WordPress page.

        Args:
            title (str): Page title
            content (str): Page content (HTML allowed)
            status (str): Page status (draft, publish, private)
            parent (int): Parent page ID for hierarchical pages

        Returns:
            str: JSON string with page creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        page_data = {"title": title, "content": content, "status": status}

        if parent:
            page_data["parent"] = parent

        result = self._make_request("POST", "pages", data=page_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "page_id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "status": result.get("status"),
                "link": result.get("link"),
            }
        )

    async def update_page(
        self, page_id: int, title: str = None, content: str = None, status: str = None
    ) -> str:
        """
        Update an existing WordPress page.

        Args:
            page_id (int): Page ID to update
            title (str): New page title (optional)
            content (str): New page content (optional)
            status (str): New page status (optional)

        Returns:
            str: JSON string with update result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        update_data = {}
        if title is not None:
            update_data["title"] = title
        if content is not None:
            update_data["content"] = content
        if status is not None:
            update_data["status"] = status

        if not update_data:
            return json.dumps({"error": "No update data provided"})

        result = self._make_request("PUT", f"pages/{page_id}", data=update_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "page_id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "status": result.get("status"),
            }
        )

    async def get_page(self, page_id: int) -> str:
        """
        Get a WordPress page by ID.

        Args:
            page_id (int): Page ID to retrieve

        Returns:
            str: JSON string with page data
        """
        result = self._make_request("GET", f"pages/{page_id}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "content": result.get("content", {}).get("rendered"),
                "status": result.get("status"),
                "author": result.get("author"),
                "date": result.get("date"),
                "link": result.get("link"),
                "parent": result.get("parent"),
            }
        )

    async def list_pages(
        self, per_page: int = 10, page: int = 1, status: str = "publish"
    ) -> str:
        """
        List WordPress pages.

        Args:
            per_page (int): Number of pages per page (1-100)
            page (int): Page number
            status (str): Page status filter

        Returns:
            str: JSON string with pages list
        """
        params = {"per_page": min(per_page, 100), "page": page, "status": status}

        result = self._make_request("GET", "pages", params=params)

        if result.get("error"):
            return json.dumps(result)

        pages = []
        for page_item in result:
            pages.append(
                {
                    "id": page_item.get("id"),
                    "title": page_item.get("title", {}).get("rendered"),
                    "status": page_item.get("status"),
                    "date": page_item.get("date"),
                    "link": page_item.get("link"),
                }
            )

        return json.dumps({"pages": pages, "total_pages": len(pages)})

    async def delete_page(self, page_id: int, force: bool = False) -> str:
        """
        Delete a WordPress page.

        Args:
            page_id (int): Page ID to delete
            force (bool): Whether to permanently delete (bypass trash)

        Returns:
            str: JSON string with deletion result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        params = {"force": force}
        result = self._make_request("DELETE", f"pages/{page_id}", params=params)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps({"success": True, "deleted": True, "page_id": page_id})

    async def create_category(
        self, name: str, description: str = "", parent: int = None
    ) -> str:
        """
        Create a new WordPress category.

        Args:
            name (str): Category name
            description (str): Category description
            parent (int): Parent category ID

        Returns:
            str: JSON string with category creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        # Check if category already exists
        existing = self._make_request("GET", "categories", params={"search": name})
        if isinstance(existing, list):
            for cat in existing:
                if cat.get("name", "").lower() == name.lower():
                    return json.dumps(
                        {
                            "success": True,
                            "id": cat.get("id"),
                            "name": cat.get("name"),
                            "existing": True,
                        }
                    )

        category_data = {"name": name, "description": description}

        if parent:
            category_data["parent"] = parent

        result = self._make_request("POST", "categories", data=category_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "id": result.get("id"),
                "name": result.get("name"),
                "description": result.get("description"),
            }
        )

    async def list_categories(self, per_page: int = 20) -> str:
        """
        List WordPress categories.

        Args:
            per_page (int): Number of categories per page

        Returns:
            str: JSON string with categories list
        """
        params = {"per_page": min(per_page, 100)}
        result = self._make_request("GET", "categories", params=params)

        if result.get("error"):
            return json.dumps(result)

        categories = []
        for cat in result:
            categories.append(
                {
                    "id": cat.get("id"),
                    "name": cat.get("name"),
                    "description": cat.get("description"),
                    "count": cat.get("count"),
                    "parent": cat.get("parent"),
                }
            )

        return json.dumps({"categories": categories})

    async def create_tag(self, name: str, description: str = "") -> str:
        """
        Create a new WordPress tag.

        Args:
            name (str): Tag name
            description (str): Tag description

        Returns:
            str: JSON string with tag creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        # Check if tag already exists
        existing = self._make_request("GET", "tags", params={"search": name})
        if isinstance(existing, list):
            for tag in existing:
                if tag.get("name", "").lower() == name.lower():
                    return json.dumps(
                        {
                            "success": True,
                            "id": tag.get("id"),
                            "name": tag.get("name"),
                            "existing": True,
                        }
                    )

        tag_data = {"name": name, "description": description}

        result = self._make_request("POST", "tags", data=tag_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "id": result.get("id"),
                "name": result.get("name"),
                "description": result.get("description"),
            }
        )

    async def list_tags(self, per_page: int = 20) -> str:
        """
        List WordPress tags.

        Args:
            per_page (int): Number of tags per page

        Returns:
            str: JSON string with tags list
        """
        params = {"per_page": min(per_page, 100)}
        result = self._make_request("GET", "tags", params=params)

        if result.get("error"):
            return json.dumps(result)

        tags = []
        for tag in result:
            tags.append(
                {
                    "id": tag.get("id"),
                    "name": tag.get("name"),
                    "description": tag.get("description"),
                    "count": tag.get("count"),
                }
            )

        return json.dumps({"tags": tags})

    async def get_comments(
        self, post_id: int = None, per_page: int = 10, status: str = "approve"
    ) -> str:
        """
        Get WordPress comments.

        Args:
            post_id (int): Filter by post ID (optional)
            per_page (int): Number of comments per page
            status (str): Comment status filter (approve, hold, spam, trash)

        Returns:
            str: JSON string with comments list
        """
        params = {"per_page": min(per_page, 100), "status": status}

        if post_id:
            params["post"] = post_id

        result = self._make_request("GET", "comments", params=params)

        if result.get("error"):
            return json.dumps(result)

        comments = []
        for comment in result:
            comments.append(
                {
                    "id": comment.get("id"),
                    "post": comment.get("post"),
                    "author_name": comment.get("author_name"),
                    "author_email": comment.get("author_email"),
                    "date": comment.get("date"),
                    "content": comment.get("content", {}).get("rendered"),
                    "status": comment.get("status"),
                    "parent": comment.get("parent"),
                }
            )

        return json.dumps({"comments": comments})

    async def moderate_comment(self, comment_id: int, status: str) -> str:
        """
        Moderate a WordPress comment (approve, hold, spam, trash).

        Args:
            comment_id (int): Comment ID to moderate
            status (str): New comment status (approve, hold, spam, trash)

        Returns:
            str: JSON string with moderation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        update_data = {"status": status}
        result = self._make_request("PUT", f"comments/{comment_id}", data=update_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "comment_id": result.get("id"),
                "status": result.get("status"),
            }
        )

    async def reply_to_comment(
        self, comment_id: int, content: str, post_id: int
    ) -> str:
        """
        Reply to a WordPress comment.

        Args:
            comment_id (int): Parent comment ID
            content (str): Reply content
            post_id (int): Post ID the comment belongs to

        Returns:
            str: JSON string with reply result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        reply_data = {"content": content, "post": post_id, "parent": comment_id}

        result = self._make_request("POST", "comments", data=reply_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "comment_id": result.get("id"),
                "parent": result.get("parent"),
                "content": result.get("content", {}).get("rendered"),
            }
        )

    async def list_users(self, per_page: int = 10, page: int = 1) -> str:
        """
        List WordPress users.

        Args:
            per_page (int): Number of users per page
            page (int): Page number

        Returns:
            str: JSON string with users list
        """
        params = {"per_page": min(per_page, 100), "page": page}

        result = self._make_request("GET", "users", params=params)

        if result.get("error"):
            return json.dumps(result)

        users = []
        for user in result:
            users.append(
                {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "roles": user.get("roles", []),
                    "registered_date": user.get("registered_date"),
                }
            )

        return json.dumps({"users": users})

    async def get_user(self, user_id: int) -> str:
        """
        Get a WordPress user by ID.

        Args:
            user_id (int): User ID to retrieve

        Returns:
            str: JSON string with user data
        """
        result = self._make_request("GET", f"users/{user_id}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "id": result.get("id"),
                "username": result.get("username"),
                "name": result.get("name"),
                "email": result.get("email"),
                "roles": result.get("roles", []),
                "registered_date": result.get("registered_date"),
                "description": result.get("description"),
            }
        )

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        name: str = "",
        roles: List[str] = None,
    ) -> str:
        """
        Create a new WordPress user.

        Args:
            username (str): Username for the new user
            email (str): Email address
            password (str): User password
            name (str): Display name
            roles (List[str]): User roles (default: subscriber)

        Returns:
            str: JSON string with user creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        user_data = {
            "username": username,
            "email": email,
            "password": password,
            "name": name or username,
            "roles": roles or ["subscriber"],
        }

        result = self._make_request("POST", "users", data=user_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "user_id": result.get("id"),
                "username": result.get("username"),
                "email": result.get("email"),
                "roles": result.get("roles"),
            }
        )

    async def get_site_info(self) -> str:
        """
        Get basic WordPress site information.

        Returns:
            str: JSON string with site information
        """
        # Use the settings endpoint for site info
        result = self._make_request("GET", "settings" if self.auth else "../")

        if result.get("error"):
            # Try alternative endpoint
            try:
                response = self.session.get(f"{self.site_url}/wp-json")
                site_info = response.json()

                return json.dumps(
                    {
                        "name": site_info.get("name", "Unknown"),
                        "description": site_info.get("description", ""),
                        "url": site_info.get("url", self.site_url),
                        "home": site_info.get("home", self.site_url),
                        "namespaces": site_info.get("namespaces", []),
                    }
                )
            except:
                return json.dumps(result)

        return json.dumps(
            {
                "title": result.get("title"),
                "description": result.get("description"),
                "url": result.get("url"),
                "email": result.get("email"),
                "timezone": result.get("timezone"),
                "date_format": result.get("date_format"),
                "time_format": result.get("time_format"),
                "language": result.get("language"),
            }
        )

    async def get_site_statistics(self) -> str:
        """
        Get WordPress site statistics (posts, pages, comments count).

        Returns:
            str: JSON string with site statistics
        """
        stats = {}

        # Get posts count
        posts_response = self._make_request("GET", "posts", params={"per_page": 1})
        if not posts_response.get("error") and isinstance(posts_response, list):
            stats["total_posts"] = len(posts_response)

        # Get pages count
        pages_response = self._make_request("GET", "pages", params={"per_page": 1})
        if not pages_response.get("error") and isinstance(pages_response, list):
            stats["total_pages"] = len(pages_response)

        # Get comments count
        comments_response = self._make_request(
            "GET", "comments", params={"per_page": 1}
        )
        if not comments_response.get("error") and isinstance(comments_response, list):
            stats["total_comments"] = len(comments_response)

        # Get categories count
        categories_response = self._make_request(
            "GET", "categories", params={"per_page": 1}
        )
        if not categories_response.get("error") and isinstance(
            categories_response, list
        ):
            stats["total_categories"] = len(categories_response)

        # Get tags count
        tags_response = self._make_request("GET", "tags", params={"per_page": 1})
        if not tags_response.get("error") and isinstance(tags_response, list):
            stats["total_tags"] = len(tags_response)

        return json.dumps({"site_statistics": stats})

    async def upload_media(
        self, file_path: str, title: str = "", description: str = ""
    ) -> str:
        """
        Upload media file to WordPress.

        Args:
            file_path (str): Path to the file to upload
            title (str): Media title
            description (str): Media description

        Returns:
            str: JSON string with upload result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        try:
            import os

            if not os.path.exists(file_path):
                return json.dumps({"error": f"File not found: {file_path}"})

            filename = os.path.basename(file_path)

            # Read file content
            with open(file_path, "rb") as f:
                file_content = f.read()

            # Determine content type
            content_type = "application/octet-stream"
            if filename.lower().endswith((".jpg", ".jpeg")):
                content_type = "image/jpeg"
            elif filename.lower().endswith(".png"):
                content_type = "image/png"
            elif filename.lower().endswith(".gif"):
                content_type = "image/gif"
            elif filename.lower().endswith(".pdf"):
                content_type = "application/pdf"

            # Upload file
            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
            }

            url = f"{self.api_base}/media"
            response = requests.post(
                url, data=file_content, headers=headers, auth=self.auth
            )

            response.raise_for_status()
            result = response.json()

            # Update title and description if provided
            if title or description:
                update_data = {}
                if title:
                    update_data["title"] = title
                if description:
                    update_data["description"] = description

                self._make_request("PUT", f"media/{result['id']}", data=update_data)

            return json.dumps(
                {
                    "success": True,
                    "media_id": result.get("id"),
                    "url": result.get("source_url"),
                    "title": result.get("title", {}).get("rendered"),
                    "filename": filename,
                }
            )

        except Exception as e:
            logging.error(f"Media upload failed: {e}")
            return json.dumps({"error": str(e)})

    async def get_media(self, media_id: int) -> str:
        """
        Get WordPress media by ID.

        Args:
            media_id (int): Media ID to retrieve

        Returns:
            str: JSON string with media data
        """
        result = self._make_request("GET", f"media/{media_id}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "id": result.get("id"),
                "title": result.get("title", {}).get("rendered"),
                "description": result.get("description", {}).get("rendered"),
                "url": result.get("source_url"),
                "media_type": result.get("media_type"),
                "mime_type": result.get("mime_type"),
                "date": result.get("date"),
            }
        )

    async def list_media(
        self, per_page: int = 10, page: int = 1, media_type: str = None
    ) -> str:
        """
        List WordPress media files.

        Args:
            per_page (int): Number of media files per page
            page (int): Page number
            media_type (str): Filter by media type (image, video, audio, etc.)

        Returns:
            str: JSON string with media list
        """
        params = {"per_page": min(per_page, 100), "page": page}

        if media_type:
            params["media_type"] = media_type

        result = self._make_request("GET", "media", params=params)

        if result.get("error"):
            return json.dumps(result)

        media_files = []
        for media in result:
            media_files.append(
                {
                    "id": media.get("id"),
                    "title": media.get("title", {}).get("rendered"),
                    "url": media.get("source_url"),
                    "media_type": media.get("media_type"),
                    "mime_type": media.get("mime_type"),
                    "date": media.get("date"),
                }
            )

        return json.dumps({"media": media_files})

    async def delete_media(self, media_id: int, force: bool = False) -> str:
        """
        Delete WordPress media file.

        Args:
            media_id (int): Media ID to delete
            force (bool): Whether to permanently delete (bypass trash)

        Returns:
            str: JSON string with deletion result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        params = {"force": force}
        result = self._make_request("DELETE", f"media/{media_id}", params=params)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps({"success": True, "deleted": True, "media_id": media_id})

    async def search_content(
        self, query: str, post_type: str = "any", per_page: int = 10
    ) -> str:
        """
        Search WordPress content.

        Args:
            query (str): Search query
            post_type (str): Type of content to search (post, page, any)
            per_page (int): Number of results per page

        Returns:
            str: JSON string with search results
        """
        results = []

        if post_type in ["post", "any"]:
            posts = self._make_request(
                "GET", "posts", params={"search": query, "per_page": per_page}
            )
            if not posts.get("error") and isinstance(posts, list):
                for post in posts:
                    results.append(
                        {
                            "type": "post",
                            "id": post.get("id"),
                            "title": post.get("title", {}).get("rendered"),
                            "excerpt": post.get("excerpt", {}).get("rendered"),
                            "link": post.get("link"),
                            "date": post.get("date"),
                        }
                    )

        if post_type in ["page", "any"]:
            pages = self._make_request(
                "GET", "pages", params={"search": query, "per_page": per_page}
            )
            if not pages.get("error") and isinstance(pages, list):
                for page in pages:
                    results.append(
                        {
                            "type": "page",
                            "id": page.get("id"),
                            "title": page.get("title", {}).get("rendered"),
                            "excerpt": page.get("excerpt", {}).get("rendered"),
                            "link": page.get("link"),
                            "date": page.get("date"),
                        }
                    )

        return json.dumps(
            {"search_query": query, "results": results, "total_results": len(results)}
        )

    async def analyze_post_seo(self, post_id: int) -> str:
        """
        Analyze a WordPress post for basic SEO factors.

        Args:
            post_id (int): Post ID to analyze

        Returns:
            str: JSON string with SEO analysis
        """
        post_response = await self.get_post(post_id)
        post_data = json.loads(post_response)

        if post_data.get("error"):
            return json.dumps(post_data)

        analysis = {
            "post_id": post_id,
            "title": post_data.get("title"),
            "seo_analysis": {},
        }

        # Analyze title length
        title = post_data.get("title", "")
        title_length = len(title)
        analysis["seo_analysis"]["title_length"] = {
            "length": title_length,
            "status": "good" if 30 <= title_length <= 60 else "needs_improvement",
            "recommendation": (
                "Title length is optimal"
                if 30 <= title_length <= 60
                else "Keep title between 30-60 characters"
            ),
        }

        # Analyze content length
        content = post_data.get("content", "")
        # Strip HTML tags for word count
        import re

        clean_content = re.sub(r"<[^>]+>", "", content)
        word_count = len(clean_content.split())
        analysis["seo_analysis"]["content_length"] = {
            "word_count": word_count,
            "status": "good" if word_count >= 300 else "needs_improvement",
            "recommendation": (
                "Content length is sufficient"
                if word_count >= 300
                else "Consider adding more content (300+ words recommended)"
            ),
        }

        # Check for excerpt
        excerpt = post_data.get("excerpt", "")
        analysis["seo_analysis"]["meta_description"] = {
            "has_excerpt": bool(excerpt and excerpt.strip()),
            "status": "good" if excerpt and excerpt.strip() else "needs_improvement",
            "recommendation": (
                "Excerpt is present"
                if excerpt and excerpt.strip()
                else "Add an excerpt to improve meta description"
            ),
        }

        return json.dumps(analysis)

    async def get_site_health(self) -> str:
        """
        Get basic WordPress site health information.

        Returns:
            str: JSON string with site health data
        """
        health_data = {"timestamp": datetime.now().isoformat(), "checks": {}}

        # Test API connectivity
        try:
            site_info = await self.get_site_info()
            site_data = json.loads(site_info)
            if not site_data.get("error"):
                health_data["checks"]["api_connectivity"] = {
                    "status": "good",
                    "message": "WordPress REST API is accessible",
                }
            else:
                health_data["checks"]["api_connectivity"] = {
                    "status": "error",
                    "message": "WordPress REST API connection failed",
                }
        except Exception as e:
            health_data["checks"]["api_connectivity"] = {
                "status": "error",
                "message": f"API connectivity test failed: {str(e)}",
            }

        # Test authentication
        if self.auth:
            try:
                users_response = await self.list_users(per_page=1)
                users_data = json.loads(users_response)
                if not users_data.get("error"):
                    health_data["checks"]["authentication"] = {
                        "status": "good",
                        "message": "Authentication is working correctly",
                    }
                else:
                    health_data["checks"]["authentication"] = {
                        "status": "error",
                        "message": "Authentication failed",
                    }
            except Exception as e:
                health_data["checks"]["authentication"] = {
                    "status": "error",
                    "message": f"Authentication test failed: {str(e)}",
                }
        else:
            health_data["checks"]["authentication"] = {
                "status": "warning",
                "message": "No authentication configured - limited functionality available",
            }

        return json.dumps(health_data)

    async def bulk_update_posts(self, post_ids: List[int], updates: dict) -> str:
        """
        Bulk update multiple WordPress posts.

        Args:
            post_ids (List[int]): List of post IDs to update
            updates (dict): Update data to apply to all posts

        Returns:
            str: JSON string with bulk update results
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        results = []

        for post_id in post_ids:
            try:
                result = self._make_request("PUT", f"posts/{post_id}", data=updates)
                if result.get("error"):
                    results.append(
                        {
                            "post_id": post_id,
                            "success": False,
                            "error": result.get("error"),
                        }
                    )
                else:
                    results.append(
                        {
                            "post_id": post_id,
                            "success": True,
                            "title": result.get("title", {}).get("rendered"),
                        }
                    )
            except Exception as e:
                results.append({"post_id": post_id, "success": False, "error": str(e)})

        successful_updates = len([r for r in results if r["success"]])

        return json.dumps(
            {
                "total_posts": len(post_ids),
                "successful_updates": successful_updates,
                "failed_updates": len(post_ids) - successful_updates,
                "results": results,
            }
        )
