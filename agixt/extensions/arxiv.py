from Extensions import Extensions
from agixtsdk import AGiXTSDK
from Globals import getenv


class arxiv(Extensions):
    """
    The ArXiv extension provides functionality for searching and learning from arXiv research papers.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Research on arXiv": self.search_arxiv,
        }
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = (
            kwargs["ApiClient"]
            if "ApiClient" in kwargs
            else AGiXTSDK(
                base_uri=getenv("AGIXT_URI"),
                api_key=kwargs["api_key"] if "api_key" in kwargs else "",
            )
        )

    async def search_arxiv(self, query: str, max_articles: int = 5):
        """
        Search for articles on arXiv and learn from them

        Args:
        query (str): The search query
        max_articles (int): The maximum number of articles to read

        Returns:
        str: Success message
        """
        return self.ApiClient.learn_arxiv(
            query=query,
            article_ids=None,
            max_articles=max_articles,
            collection_number="0",
        )
