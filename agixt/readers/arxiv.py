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
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        )

    async def write_arxiv_articles_to_memory(
        self, query: str = None, article_ids: str = None, max_articles: int = 5
    ):
        if query and article_ids:
            articles = article_ids.split(",") if "," in article_ids else [article_ids]
            results = arxiv.Search(
                id_list=articles, query=query, max_results=max_articles
            )
        if article_ids and not query:  # Comma separated list of article IDs
            articles = article_ids.split(",") if "," in article_ids else [article_ids]
            results = arxiv.Search(id_list=articles)
        if query and not article_ids:  # Search query
            results = arxiv.Search(query=query, max_results=max_articles)
        if results:
            base_path = os.path.join(os.getcwd(), "WORKSPACE")
            for result in results:
                try:
                    filename = f"{result.get_short_id()}.pdf"
                    file_path = os.path.join(base_path, filename)
                    result.download_pdf(dirpath=base_path, filename=filename)
                    with pdfplumber.open(file_path) as pdf:
                        content = "\n".join([page.extract_text() for page in pdf.pages])
                    if content != "":
                        await self.write_text_to_memory(
                            user_input=file_path if not query else query,
                            text=content,
                            external_source=f"file called {filename} from arXiv",
                        )
                    os.remove(file_path)
                except Exception as e:
                    logging.error(f"arXiv Reader Error: {e}. Article skipped.")
            return True
        else:
            return False
