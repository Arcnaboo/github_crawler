# SourceGithubAirweave

Minimal toolkit to crawl GitHub repositories sequentially or concurrently, and discover relevant repos by search.

## Files

- github.py - Sequential loader
- github_async.py - Parallel loader
- crawler.py - Searches for repos and crawls them with github.py
- README.md - This documentation
- LICENSE - MIT License

## Requirements

Python 3.8+

Install dependencies:
pip install httpx

A GitHub personal access token with repo scope if you want to avoid low rate limits.

## Usage

Search & crawl mode:
python crawler.py your search term here

Example:
python crawler.py vector database

Direct repo mode:
python crawler.py owner/repo

Example:
python crawler.py Arcnaboo/SourceGithubAirweave

## Output

As each repo is crawled, entities such as repositories, directories, and files will be printed:
[+] Crawling repo: octocat/Hello-World
[✓] Entity: GitHubCodeFileEntity | src/main.py
[✓] Entity: GitHubDirectoryEntity | src/

## Notes

Be mindful of GitHub API rate limits when crawling many repos.
Keep your personal access token private; do not commit it publicly.

## License

MIT License
