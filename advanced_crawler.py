#!/usr/bin/env python3
"""
advanced_crawler.py - Written by Arda Akgur for Airweave

Searches GitHub for repositories matching keywords from words.txt
and crawls each unique discovered repo using  established github.py loader.

Dependencies:
    pip install httpx

Usage:
    python advanced_crawler.py
"""

import asyncio
import httpx
from collections import deque
from github import GitHubSource  #  sequential loader from github.py

GITHUB_TOKEN = "YOUR_PERSONAL_ACCESS_TOKEN"  # Only needed for search
STACK = deque()  # FILO stack for repo crawling
SEEN_REPOS = set()  # Track crawled repos to avoid duplicates

async def read_keywords(filepath="words.txt") -> list:
    """Read keywords from a file, one per line."""
    print(f"[+] Reading keywords from {filepath}")
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]

async def search_repos(keyword: str) -> list:
    """Search for repos matching a keyword and return repo names."""
    print(f"[+] Searching for repos matching keyword: '{keyword}'")
    url = "https://api.github.com/search/repositories"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    params = {"q": keyword, "per_page": 10}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
    repos = []
    for item in data.get("items", []):
        repo_full_name = item["full_name"]
        print(f" -> Found repo: {repo_full_name}")
        repos.append(repo_full_name)
    return repos

async def crawl_repo(repo_name: str) -> None:
    """Crawl a repo using github.py sequential loader."""
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
    keywords = await read_keywords()
    keyword_to_repos = {}

    for keyword in keywords:
        repos = await search_repos(keyword)
        keyword_to_repos[keyword] = repos
        for repo in repos:
            if repo not in SEEN_REPOS:
                STACK.append(repo)
                SEEN_REPOS.add(repo)

    print(f"[+] Starting crawl with {len(STACK)} unique repos in FILO stack...")

    while STACK:
        current_repo = STACK.pop()
        await crawl_repo(current_repo)

    print("[✓] Crawl completed successfully.")

    print("\n[+] Keyword to Repos mapping:")
    for keyword, repos in keyword_to_repos.items():
        print(f"\nKeyword: {keyword}")
        for repo in repos:
            print(f" - {repo}")

if __name__ == "__main__":
    asyncio.run(main())
