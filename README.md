# Arcnaboo/github_crawler

Minimal toolkit to crawl GitHub repositories sequentially or concurrently, and discover relevant repos by search or from keywords.

## Files

- github.py - Sequential loader
- github_async.py - Parallel loader
- crawler.py - Searches for a term and crawls repos with github.py
- advanced_crawler.py - Reads keywords from words.txt, finds repos, and crawls them automatically
- README.md - This documentation
- LICENSE - MIT License

## Requirements

Python 3.8+

Install dependencies:
pip install httpx

A GitHub personal access token with repo scope if you want to avoid low rate limits.

## Usage

### Search & crawl a single term:
python crawler.py your search term here

Example:
python crawler.py vector database

### Crawl a specific repo directly:
python crawler.py owner/repo

Example:
python crawler.py Arcnaboo/github_crawler

### Crawl repos for a list of keywords:
1. Add keywords to words.txt, one per line.
2. Run:
python advanced_crawler.py

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
