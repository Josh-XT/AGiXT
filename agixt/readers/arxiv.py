from Memories import Memories
import os
import pdfplumber
import arxiv
import logging


class ArxivReader(Memories):
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: int = 0,
        ApiClient=None,
        user=None,
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            ApiClient=ApiClient,
            user=user,
        )

    async def write_arxiv_articles_to_memory(
        self, query: str = None, article_ids: str = None, max_articles: int = 5
    ):
        if query and article_ids:
            articles = article_ids.split(",") if "," in article_ids else [article_ids]
            results = arxiv.Search(
                id_list=articles, query=query, max_results=max_articles
            )
        elif article_ids != None and article_ids != "":
            # Comma separated list of article IDs
            articles = article_ids.split(",") if "," in article_ids else [article_ids]
            articles = [article.strip() for article in articles]
            results = arxiv.Search(id_list=articles)
        elif query != None and query != "":  # Search query
            results = arxiv.Search(query=query, max_results=max_articles)
        else:
            return False
        if results:
            base_path = os.path.join(os.getcwd(), "WORKSPACE")
            for result in results.results():
                try:
                    filename = f"{result.get_short_id()}.pdf"
                    file_path = os.path.join(base_path, filename)
                    result.download_pdf(dirpath=base_path, filename=filename)
                    with pdfplumber.open(file_path) as pdf:
                        content = "\n".join([page.extract_text() for page in pdf.pages])
                    if content != "":
                        stored_content = f"From arXiv article: {result.title} by {result.authors}\nSummary: {result.summary}\n\nAttached PDF `{filename}` Content:\n{content}"
                        await self.write_text_to_memory(
                            user_input=file_path if not query else query,
                            text=stored_content,
                            external_source=f"From arXiv article: {result.title} by {result.authors}",
                        )
                    os.remove(file_path)
                except Exception as e:
                    logging.error(f"arXiv Reader Error: {e}. Article skipped.")
            return True
        else:
            return False
