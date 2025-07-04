"""GitHub source implementation (read-only).

Retrieves data from a user's GitHub account, focusing on:
 - Repositories
 - Repository Contents (files, directories, etc.)

and yields them as entities using the corresponding GitHub entity schemas
(GithubRepoEntity and GithubContentEntity).

References:
  https://docs.github.com/en/rest/repos/repos
  https://docs.github.com/en/rest/repos/contents

Notes:
  - This connector uses a read-only scope.
  - For each repository, we gather basic repo metadata, then traverse the
    repository contents recursively (default branch only).
"""

import asyncio
import base64
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
import tenacity
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from airweave.platform.auth.schemas import AuthType
from airweave.platform.configs.auth import GitHubAuthConfig
from airweave.platform.decorators import source
from airweave.platform.entities._base import Breadcrumb, ChunkEntity
from airweave.platform.entities.github import (
    GitHubCodeFileEntity,
    GitHubDirectoryEntity,
    GitHubRepositoryEntity,
)
from airweave.platform.sources._base import BaseSource
from airweave.platform.utils.file_extensions import (
    get_language_for_extension,
    is_text_file,
)


@source(
    name="GitHub",
    short_name="github",
    auth_type=AuthType.config_class,
    auth_config_class="GitHubAuthConfig",
    config_class="GitHubConfig",
    labels=["Code"],
)
class GitHubSource(BaseSource):
    """GitHub source implementation."""

    BASE_URL = "https://api.github.com"
    MAX_CONCURRENT_DIRECTORIES = 10  # Added for parallel traversal control

    @classmethod
    async def create(
        cls, credentials: GitHubAuthConfig, config: Optional[Dict[str, Any]] = None
    ) -> "GitHubSource":
        """Create a new source instance with authentication."""
        instance = cls()
        instance.personal_access_token = credentials.personal_access_token
        instance.repo_name = credentials.repo_name
        instance.branch = config.get("branch", None)
        return instance

    @tenacity.retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get_with_auth(
        self, client: httpx.AsyncClient, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated API request using Personal Access Token."""
        headers = {
            "Authorization": f"token {self.personal_access_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def _get_paginated_results(
        self, client: httpx.AsyncClient, url: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get all pages of results from a paginated GitHub API endpoint."""
        if params is None:
            params = {}

        params["per_page"] = 100
        all_results = []
        page = 1

        while True:
            params["page"] = page
            headers = {
                "Authorization": f"token {self.personal_access_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            results = response.json()
            if not results:
                break

            all_results.extend(results)

            link_header = response.headers.get("Link", "")
            if 'rel="next"' not in link_header:
                break

            page += 1

        return all_results

    def _detect_language_from_extension(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        return get_language_for_extension(ext)

    async def _get_repository_info(
        self, client: httpx.AsyncClient, repo_name: str
    ) -> GitHubRepositoryEntity:
        """Get repository information."""
        url = f"{self.BASE_URL}/repos/{repo_name}"
        repo_data = await self._get_with_auth(client, url)

        return GitHubRepositoryEntity(
            entity_id=str(repo_data["id"]),
            source_name="github",
            name=repo_data["name"],
            full_name=repo_data["full_name"],
            description=repo_data.get("description"),
            default_branch=repo_data["default_branch"],
            created_at=datetime.fromisoformat(repo_data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(repo_data["updated_at"].replace("Z", "+00:00")),
            language=repo_data.get("language"),
            fork=repo_data["fork"],
            size=repo_data["size"],
            stars_count=repo_data.get("stargazers_count"),
            watchers_count=repo_data.get("watchers_count"),
            forks_count=repo_data.get("forks_count"),
            open_issues_count=repo_data.get("open_issues_count"),
            url=repo_data["html_url"],
        )

    async def _traverse_repository(
        self, client: httpx.AsyncClient, repo_name: str, branch: str
    ) -> AsyncGenerator[ChunkEntity, None]:
        """Traverse repository contents using DFS."""
        repo_entity = await self._get_repository_info(client, repo_name)
        yield repo_entity

        owner, repo = repo_name.split("/")
        repo_breadcrumb = Breadcrumb(
            entity_id=repo_entity.entity_id, name=repo_entity.name, type="repository"
        )

        processed_paths = set()
        async for entity in self._traverse_directory(
            client, repo_name, "", [repo_breadcrumb], owner, repo, branch, processed_paths
        ):
            yield entity

    async def _traverse_directory(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
        path: str,
        breadcrumbs: List[Breadcrumb],
        owner: str,
        repo: str,
        branch: str,
        processed_paths: set,
    ) -> AsyncGenerator[ChunkEntity, None]:
        """Recursively traverse a directory using parallel processing."""
        if path in processed_paths:
            return

        processed_paths.add(path)

        url = f"{self.BASE_URL}/repos/{repo_name}/contents/{path}"
        params = {"ref": branch}

        try:
            contents = await self._get_with_auth(client, url, params)
            items = contents if isinstance(contents, List) else [contents]

            # Process files sequentially first
            file_items = [item for item in items if item["type"] == "file"]
            for item in file_items:
                async for entity in self._process_file(
                    client, repo_name, item["path"], item, 
                    breadcrumbs, owner, repo, branch
                ):
                    yield entity

            # Process directories in parallel
            dir_items = [item for item in items if item["type"] == "dir"]
            if dir_items:
                semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DIRECTORIES)

                async def process_directory(item):
                    async with semaphore:
                        # Create directory entity
                        dir_entity = GitHubDirectoryEntity(
                            entity_id=f"{repo_name}/{item['path']}",
                            source_name="github",
                            path=item["path"],
                            repo_name=repo,
                            repo_owner=owner,
                            content=f"Directory: {item['path']}",
                            breadcrumbs=breadcrumbs.copy(),
                            url=item["html_url"],
                        )

                        # Create breadcrumb
                        dir_breadcrumb = Breadcrumb(
                            entity_id=dir_entity.entity_id,
                            name=Path(item["path"]).name,
                            type="directory",
                        )

                        yield dir_entity

                        # Recursive traversal
                        async for child_entity in self._traverse_directory(
                            client,
                            repo_name,
                            item["path"],
                            breadcrumbs.copy() + [dir_breadcrumb],
                            owner,
                            repo,
                            branch,
                            processed_paths,
                        ):
                            yield child_entity

                # Process directories in parallel
                tasks = [process_directory(item) for item in dir_items]
                for task in asyncio.as_completed(tasks):
                    async for entity in await task:
                        yield entity

        except Exception as e:
            self.logger.error(f"Error traversing path {path}: {str(e)}")

    async def _process_file(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
        item_path: str,
        item: Dict[str, Any],
        breadcrumbs: List[Breadcrumb],
        owner: str,
        repo: str,
        branch: str,
    ) -> AsyncGenerator[ChunkEntity, None]:
        """Process a file item and create file entities."""
        try:
            file_url = f"{self.BASE_URL}/repos/{repo_name}/contents/{item_path}"
            file_data = await self._get_with_auth(client, file_url, {"ref": branch})
            file_size = file_data.get("size", 0)

            content_sample = None
            content_text = None
            if file_data.get("encoding") == "base64" and file_data.get("content"):
                try:
                    content_sample = base64.b64decode(file_data["content"])
                    content_text = content_sample.decode("utf-8", errors="replace")
                except Exception:
                    pass

            if is_text_file(item_path, file_size, content_sample):
                language = self._detect_language_from_extension(item_path)
                file_name = Path(item_path).name

                line_count = 0
                if content_text:
                    try:
                        line_count = content_text.count("\n") + 1
                    except Exception as e:
                        self.logger.error(f"Error counting lines for {item_path}: {str(e)}")

                file_entity = GitHubCodeFileEntity(
                    entity_id=f"{repo_name}/{item_path}",
                    source_name="github",
                    file_id=file_data["sha"],
                    name=file_name,
                    mime_type=mimetypes.guess_type(item_path)[0] or "text/plain",
                    size=file_size,
                    path=item_path or file_name,
                    repo_name=repo,
                    repo_owner=owner,
                    sha=file_data["sha"],
                    breadcrumbs=breadcrumbs.copy(),
                    url=file_data["html_url"],
                    language=language,
                    line_count=line_count,
                    path_in_repo=item_path,
                    content=content_text,
                    last_modified=None,
                )

                yield file_entity
        except Exception as e:
            self.logger.error(f"Error processing file {item_path}: {str(e)}")

    async def generate_entities(self) -> AsyncGenerator[ChunkEntity, None]:
        """Generate entities from GitHub repository."""
        if not hasattr(self, "repo_name") or not self.repo_name:
            raise ValueError("Repository name must be specified")

        async with httpx.AsyncClient() as client:
            repo_url = f"{self.BASE_URL}/repos/{self.repo_name}"
            repo_data = await self._get_with_auth(client, repo_url)

            branch = (
                self.branch
                if hasattr(self, "branch") and self.branch
                else repo_data["default_branch"]
            )

            if hasattr(self, "branch") and self.branch:
                branches_url = f"{self.BASE_URL}/repos/{self.repo_name}/branches"
                branches_data = await self._get_paginated_results(client, branches_url)
                branch_names = [b["name"] for b in branches_data]

                if branch not in branch_names:
                    available_branches = ", ".join(branch_names)
                    raise ValueError(
                        f"Branch '{branch}' not found in repository '{self.repo_name}'. "
                        f"Available branches: {available_branches}"
                    )

            self.logger.info(f"Using branch: {branch} for repo {self.repo_name}")

            async for entity in self._traverse_repository(client, self.repo_name, branch):
                yield entity