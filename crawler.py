#!/usr/bin/env python3
"""
crawler.py - Written by Arda Akgur for Airweave

Searches GitHub for repositories matching a term or crawls a specific repo,
then uses github.py (your sequential loader) to fetch data from each repo
using a FILO stack.

Dependencies:
    pip install httpx

Usage:
    python crawler.py <search-term | owner/repo>

Example:
    python crawler.py airflow operators
    python crawler.py octocat/Hello-World
"""

import sys
import asyncio
import httpx
from collections import deque
from github import GitHubSource  # Your established sequential loader

GITHUB_TOKEN = "YOUR_PERSONAL_ACCESS_TOKEN"  # Only needed for search step

STACK = deque()  # FILO stack for repo crawling

async def search_repos(search_term: str) -> None:
    """Search for repos with GitHub Search API and push them onto the stack."""
    print(f"[+] Searching GitHub for repos matching: '{search_term}'")
    url = "https://api.github.com/search/repositories"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    params = {"q": search_term, "per_page": 10}  # Adjust per_page as needed
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    for item in data.get("items", []):
        repo_full_name = item["full_name"]
        print(f" -> Found repo: {repo_full_name}")
        STACK.append(repo_full_name)

async def crawl_repo(repo_name: str) -> None:
    """Use established github.py sequential loader to crawl the given repo."""
    print(f"[+] Crawling repo: {repo_name}")
    try:
        github_source = await GitHubSource.create(
            credentials=type("Creds", (), {
                "repo_name": repo_name,
            })(),
            config={},
        )
        async for entity in github_source.generate_entities():
            print(f"[✓] Entity: {entity.__class__.__name__} | {getattr(entity, 'path', getattr(entity, 'full_name', ''))}")
    except Exception as e:
        print(f"[!] Error crawling {repo_name}: {str(e)}")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python crawler.py <search-term|owner/repo>")
        sys.exit(1)

    term_or_repo = " ".join(sys.argv[1:])

    if "/" in term_or_repo:
        # Direct repo mode
        STACK.append(term_or_repo)
    else:
        # Search mode
        await search_repos(term_or_repo)

    print(f"[+] Starting crawl with {len(STACK)} repos in FILO stack...")

    while STACK:
        current_repo = STACK.pop()  # FILO: newest repo crawled first
        await crawl_repo(current_repo)

    print("[✓] Crawl completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
