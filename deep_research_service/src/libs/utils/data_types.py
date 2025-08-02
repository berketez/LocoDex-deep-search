import asyncio
import select
import sys
from dataclasses import dataclass

from pydantic import BaseModel, Field

from libs.utils.tavily_search import SearchResult, SearchResults


class ResearchPlan(BaseModel):
    queries: list[str] = Field(
        description="A list of search queries to thoroughly research the topic")


class SourceList(BaseModel):
    sources: list[int] = Field(
        description="A list of source numbers from the search results")


class UserCommunication:
    """Handles user input/output interactions with timeout functionality."""

    @staticmethod
    async def get_input_with_timeout(prompt: str, timeout: float = 30.0) -> str:
        """
        Get user input with a timeout.
        Returns empty string if timeout occurs or no input is provided.

        Args:
            prompt: The prompt to display to the user
            timeout: Number of seconds to wait for user input (default: 30.0)

        Returns:
            str: User input or empty string if timeout occurs
        """
        print(prompt, end="", flush=True)

        # Different implementation for Windows vs Unix-like systems
        if sys.platform == "win32":
            # Windows implementation
            try:
                # Run input in an executor to make it async
                loop = asyncio.get_event_loop()
                user_input = await asyncio.wait_for(loop.run_in_executor(None, input), timeout)
                return user_input.strip()
            except TimeoutError:
                print("\nTimeout reached, continuing...")
                return ""
        else:
            # Unix-like implementation
            i, _, _ = select.select([sys.stdin], [], [], timeout)
            if i:
                return sys.stdin.readline().strip()
            else:
                print("\nTimeout reached, continuing...")
                return ""


@dataclass(frozen=True, kw_only=True)
class DeepResearchResult(SearchResult):
    """Wrapper on top of SearchResults to adapt it to the DeepResearch.

    This class extends the basic SearchResult by adding a filtered version of the raw content
    that has been processed and refined for the specific research context. It maintains
    the original search result while providing additional research-specific information.

    Attributes:
        filtered_raw_content: A processed version of the raw content that has been filtered
                             and refined for relevance to the research topic
    """

    filtered_raw_content: str

    def __str__(self):
        return f"Title: {self.title}\n" f"Link: {self.link}\n" f"Refined Content: {self.filtered_raw_content[:10000]}"

    def short_str(self):
        return f"Title: {self.title}\nLink: {self.link}\nRaw Content: {self.content[:10000]}"


@dataclass(frozen=True, kw_only=True)
class DeepResearchResults(SearchResults):
    results: list[DeepResearchResult]

    def __add__(self, other):
        return DeepResearchResults(results=self.results + other.results)

    def dedup(self):
        def deduplicate_by_link(results):
            seen_links = set()
            unique_results = []

            for result in results:
                if result.link not in seen_links:
                    seen_links.add(result.link)
                    unique_results.append(result)

            return unique_results

        return DeepResearchResults(results=deduplicate_by_link(self.results))
