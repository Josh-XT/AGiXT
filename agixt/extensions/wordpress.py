import logging
import json
import base64
import requests
from datetime import datetime
from typing import List, Dict, Optional, Union
from Extensions import Extensions
from requests.auth import HTTPBasicAuth


class wordpress(Extensions):
    """
    The WordPress extension for AGiXT enables you to interact with WordPress websites through the WordPress REST API.
    This extension provides comprehensive functionality for managing posts, pages, users, media, categories, tags, and comments.
    """

    CATEGORY = "Productivity"
    friendly_name = "WordPress"

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
            "Resize WordPress Media": self.resize_media,
            "Generate WordPress Media Thumbnails": self.generate_thumbnails,
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
            # Custom Post Types
            "List WordPress Post Types": self.list_post_types,
            "Get WordPress Post Type Details": self.get_post_type_details,
            "Create Custom Post": self.create_custom_post,
            "List Custom Posts": self.list_custom_posts,
            # Plugin Management
            "List WordPress Plugins": self.list_plugins,
            "Get WordPress Plugin Details": self.get_plugin_details,
            "Activate WordPress Plugin": self.activate_plugin,
            "Deactivate WordPress Plugin": self.deactivate_plugin,
            # Theme Management
            "List WordPress Themes": self.list_themes,
            "Get Active WordPress Theme": self.get_active_theme,
            "Switch WordPress Theme": self.switch_theme,
            # Site Information
            "Get WordPress Site Info": self.get_site_info,
            "Get WordPress Site Statistics": self.get_site_statistics,
            # SEO and Analytics
            "Analyze WordPress Post SEO": self.analyze_post_seo,
            "Advanced WordPress SEO Analysis": self.advanced_seo_analysis,
            "Get WordPress Site Health": self.get_site_health,
            "Optimize WordPress Content": self.optimize_content,
            "Check WordPress Broken Links": self.check_broken_links,
            # Content Management
            "Search WordPress Content": self.search_content,
            "Bulk Update WordPress Posts": self.bulk_update_posts,
            "WordPress Content Audit": self.content_audit,
            # Custom Fields & Meta
            "Get WordPress Post Meta": self.get_post_meta,
            "Update WordPress Post Meta": self.update_post_meta,
            "List WordPress Custom Fields": self.list_custom_fields,
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
        post_type: str = "posts",
        meta: dict = None,
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
            post_type (str): Post type (posts, pages, or custom post type)
            meta (dict): Custom fields/meta data

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

        if meta:
            post_data["meta"] = meta

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

        result = self._make_request("POST", post_type, data=post_data)

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
        post_type: str = "posts",
    ) -> str:
        """
        List WordPress posts with optional filtering.

        Args:
            per_page (int): Number of posts per page (1-100)
            page (int): Page number
            status (str): Post status filter (publish, draft, private, any)
            search (str): Search term
            author (int): Author ID filter
            post_type (str): Post type to list (posts, pages, or custom post type)

        Returns:
            str: JSON string with posts list
        """
        params = {"per_page": min(per_page, 100), "page": page, "status": status}

        if search:
            params["search"] = search
        if author:
            params["author"] = author

        result = self._make_request("GET", post_type, params=params)

        if isinstance(result, dict) and result.get("error"):
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

        if isinstance(result, dict) and result.get("error"):
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

        if isinstance(result, dict) and result.get("error"):
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

        if isinstance(result, dict) and result.get("error"):
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

        if isinstance(result, dict) and result.get("error"):
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

        if isinstance(result, dict) and result.get("error"):
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
        if isinstance(posts_response, list):
            stats["total_posts"] = len(posts_response)

        # Get pages count
        pages_response = self._make_request("GET", "pages", params={"per_page": 1})
        if isinstance(pages_response, list):
            stats["total_pages"] = len(pages_response)

        # Get comments count
        comments_response = self._make_request(
            "GET", "comments", params={"per_page": 1}
        )
        if isinstance(comments_response, list):
            stats["total_comments"] = len(comments_response)

        # Get categories count
        categories_response = self._make_request(
            "GET", "categories", params={"per_page": 1}
        )
        if isinstance(categories_response, list):
            stats["total_categories"] = len(categories_response)

        # Get tags count
        tags_response = self._make_request("GET", "tags", params={"per_page": 1})
        if isinstance(tags_response, list):
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

        if isinstance(result, dict) and result.get("error"):
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
            if isinstance(posts, list):
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
            if isinstance(pages, list):
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

    # ===============================
    # ENHANCED FUNCTIONALITY
    # ===============================

    # Custom Post Types Management
    async def list_post_types(self) -> str:
        """
        List all registered WordPress post types.

        Returns:
            str: JSON string with post types list
        """
        result = self._make_request("GET", "types")

        if result.get("error"):
            return json.dumps(result)

        post_types = []
        for key, post_type in result.items():
            post_types.append(
                {
                    "name": key,
                    "label": post_type.get("name"),
                    "description": post_type.get("description"),
                    "hierarchical": post_type.get("hierarchical"),
                    "public": post_type.get("public"),
                    "rest_base": post_type.get("rest_base"),
                }
            )

        return json.dumps({"post_types": post_types})

    async def get_post_type_details(self, post_type: str) -> str:
        """
        Get detailed information about a specific post type.

        Args:
            post_type (str): Post type name

        Returns:
            str: JSON string with post type details
        """
        result = self._make_request("GET", f"types/{post_type}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "name": result.get("slug"),
                "label": result.get("name"),
                "description": result.get("description"),
                "hierarchical": result.get("hierarchical"),
                "public": result.get("public"),
                "capabilities": result.get("capabilities"),
                "supports": result.get("supports"),
                "rest_base": result.get("rest_base"),
            }
        )

    async def create_custom_post(
        self,
        post_type: str,
        title: str,
        content: str,
        status: str = "draft",
        meta: dict = None,
    ) -> str:
        """
        Create a custom post of specified post type.

        Args:
            post_type (str): Custom post type name
            title (str): Post title
            content (str): Post content
            status (str): Post status
            meta (dict): Custom fields/meta data

        Returns:
            str: JSON string with creation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        post_data = {"title": title, "content": content, "status": status}

        if meta:
            post_data["meta"] = meta

        result = self._make_request("POST", post_type, data=post_data)

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "post_id": result.get("id"),
                "post_type": post_type,
                "title": result.get("title", {}).get("rendered"),
                "status": result.get("status"),
                "link": result.get("link"),
            }
        )

    async def list_custom_posts(
        self, post_type: str, per_page: int = 10, status: str = "publish"
    ) -> str:
        """
        List posts of a specific custom post type.

        Args:
            post_type (str): Custom post type name
            per_page (int): Number of posts per page
            status (str): Post status filter

        Returns:
            str: JSON string with posts list
        """
        params = {"per_page": min(per_page, 100), "status": status}

        result = self._make_request("GET", post_type, params=params)

        if isinstance(result, dict) and result.get("error"):
            return json.dumps(result)

        posts = []
        for post in result:
            posts.append(
                {
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered"),
                    "content": post.get("content", {}).get("rendered"),
                    "status": post.get("status"),
                    "date": post.get("date"),
                    "link": post.get("link"),
                    "meta": post.get("meta", {}),
                }
            )

        return json.dumps({"posts": posts, "post_type": post_type})

    # Plugin Management
    async def list_plugins(self) -> str:
        """
        List WordPress plugins (requires appropriate permissions).

        Returns:
            str: JSON string with plugins list
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        result = self._make_request("GET", "plugins")

        if result.get("error"):
            return json.dumps(result)

        plugins = []
        for plugin_file, plugin_data in result.items():
            plugins.append(
                {
                    "plugin": plugin_file,
                    "name": plugin_data.get("name"),
                    "version": plugin_data.get("version"),
                    "status": plugin_data.get("status"),
                    "description": plugin_data.get("description"),
                    "author": plugin_data.get("author"),
                    "plugin_uri": plugin_data.get("plugin_uri"),
                }
            )

        return json.dumps({"plugins": plugins})

    async def get_plugin_details(self, plugin: str) -> str:
        """
        Get detailed information about a specific plugin.

        Args:
            plugin (str): Plugin file path (e.g., 'plugin-folder/plugin-file.php')

        Returns:
            str: JSON string with plugin details
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        result = self._make_request("GET", f"plugins/{plugin}")

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "plugin": result.get("plugin"),
                "name": result.get("name"),
                "version": result.get("version"),
                "status": result.get("status"),
                "description": result.get("description"),
                "author": result.get("author"),
                "plugin_uri": result.get("plugin_uri"),
                "requires_wp": result.get("requires_wp"),
                "requires_php": result.get("requires_php"),
            }
        )

    async def activate_plugin(self, plugin: str) -> str:
        """
        Activate a WordPress plugin.

        Args:
            plugin (str): Plugin file path

        Returns:
            str: JSON string with activation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        result = self._make_request(
            "PUT", f"plugins/{plugin}", data={"status": "active"}
        )

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "plugin": result.get("plugin"),
                "name": result.get("name"),
                "status": result.get("status"),
            }
        )

    async def deactivate_plugin(self, plugin: str) -> str:
        """
        Deactivate a WordPress plugin.

        Args:
            plugin (str): Plugin file path

        Returns:
            str: JSON string with deactivation result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        result = self._make_request(
            "PUT", f"plugins/{plugin}", data={"status": "inactive"}
        )

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "plugin": result.get("plugin"),
                "name": result.get("name"),
                "status": result.get("status"),
            }
        )

    # Theme Management
    async def list_themes(self) -> str:
        """
        List WordPress themes.

        Returns:
            str: JSON string with themes list
        """
        result = self._make_request("GET", "themes")

        if result.get("error"):
            return json.dumps(result)

        themes = []
        for theme_slug, theme_data in result.items():
            themes.append(
                {
                    "slug": theme_slug,
                    "name": theme_data.get("name", {}).get("rendered"),
                    "description": theme_data.get("description", {}).get("rendered"),
                    "version": theme_data.get("version"),
                    "status": theme_data.get("status"),
                    "screenshot": theme_data.get("screenshot"),
                    "author": theme_data.get("author", {}).get("display_name"),
                }
            )

        return json.dumps({"themes": themes})

    async def get_active_theme(self) -> str:
        """
        Get information about the currently active theme.

        Returns:
            str: JSON string with active theme details
        """
        themes_response = await self.list_themes()
        themes_data = json.loads(themes_response)

        if themes_data.get("error"):
            return json.dumps(themes_data)

        active_theme = None
        for theme in themes_data.get("themes", []):
            if theme.get("status") == "active":
                active_theme = theme
                break

        if active_theme:
            return json.dumps({"active_theme": active_theme})
        else:
            return json.dumps({"error": "No active theme found"})

    async def switch_theme(self, theme_slug: str) -> str:
        """
        Switch to a different WordPress theme.

        Args:
            theme_slug (str): Theme slug/folder name

        Returns:
            str: JSON string with switch result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        # This typically requires admin privileges and may not be available via REST API
        # Would need custom endpoint or WP-CLI integration
        return json.dumps(
            {
                "error": "Theme switching requires admin access and may need custom implementation",
                "suggestion": "Use WordPress admin interface or WP-CLI for theme switching",
            }
        )

    # Advanced Media Management
    async def resize_media(self, media_id: int, width: int, height: int = None) -> str:
        """
        Resize WordPress media (requires image editing capabilities).

        Args:
            media_id (int): Media ID to resize
            width (int): Target width
            height (int): Target height (optional, maintains aspect ratio if not provided)

        Returns:
            str: JSON string with resize result
        """
        # This would typically require a custom WordPress plugin or external service
        return json.dumps(
            {
                "info": "Media resizing requires additional WordPress plugins or external services",
                "media_id": media_id,
                "requested_width": width,
                "requested_height": height,
                "suggestion": "Consider using WordPress image editing plugins or external APIs",
            }
        )

    async def generate_thumbnails(self, media_id: int) -> str:
        """
        Regenerate thumbnails for a media file.

        Args:
            media_id (int): Media ID to regenerate thumbnails for

        Returns:
            str: JSON string with generation result
        """
        # Get media details first
        media_response = await self.get_media(media_id)
        media_data = json.loads(media_response)

        if media_data.get("error"):
            return json.dumps(media_data)

        # WordPress automatically generates thumbnails, but regeneration requires plugins
        return json.dumps(
            {
                "info": "Thumbnail regeneration requires WordPress plugins like 'Regenerate Thumbnails'",
                "media_id": media_id,
                "current_url": media_data.get("url"),
                "media_type": media_data.get("media_type"),
            }
        )

    # Enhanced SEO Analysis
    async def advanced_seo_analysis(self, post_id: int) -> str:
        """
        Perform advanced SEO analysis on a WordPress post.

        Args:
            post_id (int): Post ID to analyze

        Returns:
            str: JSON string with comprehensive SEO analysis
        """
        post_response = await self.get_post(post_id)
        post_data = json.loads(post_response)

        if post_data.get("error"):
            return json.dumps(post_data)

        title = post_data.get("title", "")
        content = post_data.get("content", "")

        # Advanced SEO analysis
        analysis = {"post_id": post_id, "title": title, "advanced_seo_analysis": {}}

        # Content analysis
        import re

        clean_content = re.sub(r"<[^>]+>", "", content)
        words = clean_content.split()
        word_count = len(words)

        # Readability analysis (simple Flesch Reading Ease approximation)
        sentences = len(re.split(r"[.!?]+", clean_content))
        if sentences > 0 and word_count > 0:
            avg_words_per_sentence = word_count / sentences
            readability_score = 206.835 - (1.015 * avg_words_per_sentence)

            if readability_score >= 90:
                readability_level = "Very Easy"
            elif readability_score >= 80:
                readability_level = "Easy"
            elif readability_score >= 70:
                readability_level = "Fairly Easy"
            elif readability_score >= 60:
                readability_level = "Standard"
            elif readability_score >= 50:
                readability_level = "Fairly Difficult"
            elif readability_score >= 30:
                readability_level = "Difficult"
            else:
                readability_level = "Very Difficult"
        else:
            readability_score = 0
            readability_level = "Cannot calculate"

        analysis["advanced_seo_analysis"]["readability"] = {
            "score": round(readability_score, 2),
            "level": readability_level,
            "words_per_sentence": (
                round(avg_words_per_sentence, 1) if sentences > 0 else 0
            ),
        }

        # Keyword density (top 10 words)
        word_freq = {}
        for word in words:
            word = re.sub(r"[^a-zA-Z0-9]", "", word.lower())
            if len(word) > 3:  # Ignore short words
                word_freq[word] = word_freq.get(word, 0) + 1

        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        keyword_analysis = []
        for word, count in top_keywords:
            density = (count / word_count) * 100 if word_count > 0 else 0
            keyword_analysis.append(
                {"keyword": word, "count": count, "density_percent": round(density, 2)}
            )

        analysis["advanced_seo_analysis"]["keywords"] = keyword_analysis

        # Title analysis
        title_length = len(title)
        analysis["advanced_seo_analysis"]["title_analysis"] = {
            "length": title_length,
            "character_count": title_length,
            "word_count": len(title.split()),
            "status": "optimal" if 30 <= title_length <= 60 else "needs_improvement",
            "recommendation": (
                "Title length is good"
                if 30 <= title_length <= 60
                else "Keep title between 30-60 characters"
            ),
        }

        # Content structure analysis
        heading_pattern = r"<h([1-6])[^>]*>(.*?)</h[1-6]>"
        headings = re.findall(heading_pattern, content, re.IGNORECASE)

        analysis["advanced_seo_analysis"]["content_structure"] = {
            "headings_count": len(headings),
            "headings": [
                {"level": h[0], "text": re.sub(r"<[^>]+>", "", h[1])} for h in headings
            ],
            "has_h1": any(h[0] == "1" for h in headings),
            "structure_score": "good" if len(headings) > 0 else "needs_improvement",
        }

        return json.dumps(analysis)

    async def optimize_content(self, post_id: int, target_keyword: str = None) -> str:
        """
        Provide content optimization suggestions for a WordPress post.

        Args:
            post_id (int): Post ID to optimize
            target_keyword (str): Target keyword for optimization

        Returns:
            str: JSON string with optimization suggestions
        """
        seo_response = await self.advanced_seo_analysis(post_id)
        seo_data = json.loads(seo_response)

        if seo_data.get("error"):
            return json.dumps(seo_data)

        suggestions = {"post_id": post_id, "optimization_suggestions": []}

        # Analyze current SEO data and provide suggestions
        seo_analysis = seo_data.get("advanced_seo_analysis", {})

        # Title suggestions
        title_analysis = seo_analysis.get("title_analysis", {})
        if title_analysis.get("status") == "needs_improvement":
            suggestions["optimization_suggestions"].append(
                {
                    "category": "Title",
                    "priority": "high",
                    "suggestion": title_analysis.get("recommendation"),
                    "current_length": title_analysis.get("length"),
                }
            )

        # Content length suggestions
        if seo_analysis.get("readability", {}).get("score", 0) < 60:
            suggestions["optimization_suggestions"].append(
                {
                    "category": "Readability",
                    "priority": "medium",
                    "suggestion": "Consider simplifying sentences and using more common words to improve readability",
                    "current_score": seo_analysis.get("readability", {}).get("score"),
                }
            )

        # Heading structure suggestions
        content_structure = seo_analysis.get("content_structure", {})
        if not content_structure.get("has_h1"):
            suggestions["optimization_suggestions"].append(
                {
                    "category": "Content Structure",
                    "priority": "high",
                    "suggestion": "Add an H1 heading to improve content structure",
                    "current_headings": content_structure.get("headings_count", 0),
                }
            )

        # Keyword optimization suggestions
        if target_keyword:
            keywords = seo_analysis.get("keywords", [])
            keyword_found = any(
                target_keyword.lower() in k["keyword"] for k in keywords
            )
            if not keyword_found:
                suggestions["optimization_suggestions"].append(
                    {
                        "category": "Keywords",
                        "priority": "medium",
                        "suggestion": f"Consider including the target keyword '{target_keyword}' more prominently in the content",
                        "target_keyword": target_keyword,
                    }
                )

        return json.dumps(suggestions)

    async def check_broken_links(self, post_id: int) -> str:
        """
        Check for broken links in a WordPress post.

        Args:
            post_id (int): Post ID to check for broken links

        Returns:
            str: JSON string with broken links analysis
        """
        post_response = await self.get_post(post_id)
        post_data = json.loads(post_response)

        if post_data.get("error"):
            return json.dumps(post_data)

        content = post_data.get("content", "")

        # Extract links from content
        import re

        link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>'
        links = re.findall(link_pattern, content, re.IGNORECASE)

        broken_links = []
        working_links = []

        for link in links:
            if link.startswith(("http://", "https://")):
                try:
                    response = self.session.head(link, timeout=10, allow_redirects=True)
                    if response.status_code >= 400:
                        broken_links.append(
                            {
                                "url": link,
                                "status_code": response.status_code,
                                "error": f"HTTP {response.status_code}",
                            }
                        )
                    else:
                        working_links.append(
                            {"url": link, "status_code": response.status_code}
                        )
                except Exception as e:
                    broken_links.append({"url": link, "error": str(e)})

        return json.dumps(
            {
                "post_id": post_id,
                "total_links": len(links),
                "working_links": len(working_links),
                "broken_links": len(broken_links),
                "broken_link_details": broken_links,
                "health_status": (
                    "good" if len(broken_links) == 0 else "needs_attention"
                ),
            }
        )

    # Content Management Enhancements
    async def content_audit(self, days_old: int = 365) -> str:
        """
        Perform a content audit to identify old or outdated content.

        Args:
            days_old (int): Consider content older than this many days as outdated

        Returns:
            str: JSON string with content audit results
        """
        from datetime import datetime, timedelta

        cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime("%Y-%m-%d")

        # Get posts older than cutoff date
        old_posts_response = await self.list_posts(per_page=50, status="publish")
        posts_data = json.loads(old_posts_response)

        if posts_data.get("error"):
            return json.dumps(posts_data)

        audit_results = {
            "audit_date": datetime.now().isoformat(),
            "cutoff_date": cutoff_date,
            "outdated_content": [],
            "recent_content": [],
            "recommendations": [],
        }

        for post in posts_data.get("posts", []):
            post_date = post.get("date", "")
            if post_date < cutoff_date:
                audit_results["outdated_content"].append(
                    {
                        "id": post.get("id"),
                        "title": post.get("title"),
                        "date": post_date,
                        "link": post.get("link"),
                    }
                )
            else:
                audit_results["recent_content"].append(
                    {
                        "id": post.get("id"),
                        "title": post.get("title"),
                        "date": post_date,
                    }
                )

        # Generate recommendations
        outdated_count = len(audit_results["outdated_content"])
        if outdated_count > 0:
            audit_results["recommendations"].append(
                {
                    "priority": "high",
                    "action": "Review and update outdated content",
                    "details": f"Found {outdated_count} posts older than {days_old} days",
                }
            )

        if outdated_count > 10:
            audit_results["recommendations"].append(
                {
                    "priority": "medium",
                    "action": "Consider consolidating or removing very old content",
                    "details": "Large amount of outdated content may affect SEO",
                }
            )

        return json.dumps(audit_results)

    # Custom Fields & Meta Management
    async def get_post_meta(self, post_id: int, meta_key: str = None) -> str:
        """
        Get custom fields/meta data for a WordPress post.

        Args:
            post_id (int): Post ID
            meta_key (str): Specific meta key to retrieve (optional)

        Returns:
            str: JSON string with meta data
        """
        params = {"_embed": "true"} if not meta_key else {}
        result = self._make_request("GET", f"posts/{post_id}", params=params)

        if result.get("error"):
            return json.dumps(result)

        meta_data = result.get("meta", {})

        if meta_key:
            return json.dumps(
                {
                    "post_id": post_id,
                    "meta_key": meta_key,
                    "meta_value": meta_data.get(meta_key),
                }
            )
        else:
            return json.dumps({"post_id": post_id, "meta_data": meta_data})

    async def update_post_meta(
        self, post_id: int, meta_key: str, meta_value: str
    ) -> str:
        """
        Update custom field/meta data for a WordPress post.

        Args:
            post_id (int): Post ID
            meta_key (str): Meta key to update
            meta_value (str): New meta value

        Returns:
            str: JSON string with update result
        """
        if not self.auth:
            return json.dumps({"error": "WordPress authentication not configured"})

        meta_data = {meta_key: meta_value}
        result = self._make_request("PUT", f"posts/{post_id}", data={"meta": meta_data})

        if result.get("error"):
            return json.dumps(result)

        return json.dumps(
            {
                "success": True,
                "post_id": post_id,
                "meta_key": meta_key,
                "meta_value": meta_value,
                "updated": True,
            }
        )

    async def list_custom_fields(self, post_id: int) -> str:
        """
        List all custom fields for a WordPress post.

        Args:
            post_id (int): Post ID

        Returns:
            str: JSON string with custom fields list
        """
        result = self._make_request("GET", f"posts/{post_id}")

        if result.get("error"):
            return json.dumps(result)

        meta_data = result.get("meta", {})

        custom_fields = []
        for key, value in meta_data.items():
            if not key.startswith("_"):  # Exclude WordPress internal meta keys
                custom_fields.append({"key": key, "value": value})

        return json.dumps(
            {
                "post_id": post_id,
                "custom_fields": custom_fields,
                "total_fields": len(custom_fields),
            }
        )
