from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import validators
from flask import abort

from shared.interfaces import Post
from shared.processing_paths import get_in_root

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = str(get_in_root())


def _host_matches(host: str, patterns: list[str]) -> bool:
    return any(host == p or host.endswith("." + p) for p in patterns)


def _redact_proxy(proxy: str) -> str:
    parts = urlsplit(proxy)
    if parts.username or parts.password:
        return f"{parts.scheme}://***@{parts.hostname}:{parts.port}"
    return proxy


# Why DOWNLOAD_PROXY failed, read from the exception text. urllib3 reports
# every proxy failure, a timeout included, as ProxyError, so the class alone
# says nothing. The text also names the full episode URL (private feeds carry
# tokens there), so only the matched reason is ever logged.
_PROXY_FAILURES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Tunnel connection failed: (\d{3})"), "proxy answered HTTP {0}"),
    (re.compile(r"timed out"), "connection timed out"),
    (re.compile(r"Connection refused"), "connection refused"),
    (
        re.compile(r"Failed to resolve|Name or service not known"),
        "proxy host name not resolvable",
    ),
    (
        re.compile(r"No route to host|Network is unreachable"),
        "no route to the proxy host",
    ),
)


def proxy_failure_reason(exc: requests.RequestException) -> str:
    """Short, URL-free reason for a failed connection through DOWNLOAD_PROXY."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "connection timed out"
    text = str(exc)
    for pattern, reason in _PROXY_FAILURES:
        match = pattern.search(text)
        if match:
            return reason.format(*match.groups())
    return type(exc).__name__


def download_proxies(url: str) -> dict[str, str] | None:
    """Proxy for an episode download, from DOWNLOAD_PROXY / DOWNLOAD_PROXY_HOSTS.

    Some hosts (e.g. Patreon behind Cloudflare) refuse downloads from data
    centre IPs. DOWNLOAD_PROXY (http:// or https://) routes episode downloads
    through another connection, such as a proxy at home reached over a VPN
    (NetBird, Tailscale).
    DOWNLOAD_PROXY_HOSTS limits it to these domains and their subdomains
    (comma-separated); empty means every download. Feeds and API calls never
    use it.
    """
    proxy = (os.environ.get("DOWNLOAD_PROXY") or "").strip()
    if not proxy:
        return None
    scheme = urlsplit(proxy).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            "DOWNLOAD_PROXY must start with http:// or https:// "
            f"(got {scheme or 'no scheme'}://)"
        )
    hosts = [
        h.strip().lower().lstrip(".")
        for h in (os.environ.get("DOWNLOAD_PROXY_HOSTS") or "").split(",")
        if h.strip()
    ]
    host = (urlsplit(url).hostname or "").lower()
    if hosts and not _host_matches(host, hosts):
        return None
    return {"http": proxy, "https": proxy}


def proxy_fallback_enabled() -> bool:
    """Download directly when DOWNLOAD_PROXY cannot be reached (default).

    DOWNLOAD_PROXY_FALLBACK=none fails the download instead, for setups where
    a direct download is pointless (a host that blocks the server) or
    unwanted (ads chosen for the server's location).
    """
    value = (os.environ.get("DOWNLOAD_PROXY_FALLBACK") or "direct").strip().lower()
    return value != "none"


class PodcastDownloader:
    """
    Handles downloading podcast episodes with robust file checking and path management.
    """

    def __init__(
        self, download_dir: str = DOWNLOAD_DIR, logger: logging.Logger | None = None
    ):
        self.download_dir = download_dir
        self.logger = logger or logging.getLogger(__name__)
        # Why the last download_episode() returned None, for the job status.
        self.last_error: str | None = None

    def download_episode(self, post: Post, dest_path: str) -> str | None:
        """
        Download a podcast episode if it doesn't already exist.

        Args:
            post: The Post object containing the podcast episode to download

        Returns:
            Path to the downloaded file, or None if download failed
        """
        self.last_error = None
        # Destination is required; ensure parent directory exists
        download_path = dest_path
        Path(download_path).parent.mkdir(parents=True, exist_ok=True)
        if not download_path:
            self.logger.error(f"Invalid download path for post {post.id}")
            return None

        # First, check if the file truly exists and has nonzero size.
        try:
            if os.path.isfile(download_path) and os.path.getsize(download_path) > 0:
                self.logger.info("Episode already downloaded.")
                return download_path
            self.logger.info("File is zero bytes, re-downloading.")  # else

        except FileNotFoundError:
            # Covers both "file actually missing" and "broken symlink"
            pass

        # If we get here, the file is missing or zero bytes -> perform download
        audio_link = post.download_url
        if audio_link is None or not validators.url(audio_link):
            abort(404)
            return None

        # Private feeds (Patreon, Supercast, ...) put tokens in the URL's path
        # and query, so only the host goes into the log.
        self.logger.info(
            "Downloading from %s into %s...",
            urlsplit(audio_link).hostname,
            download_path,
        )
        referer = "https://open.acast.com/" if "acast.com" in audio_link else None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": referer,
        }
        request_options: dict[str, Any] = {}
        proxies = download_proxies(audio_link)
        if proxies:
            request_options["proxies"] = proxies
            self.logger.info(
                "Downloading through DOWNLOAD_PROXY %s",
                _redact_proxy(proxies["https"]),
            )
        try:
            return self._fetch_to_path(
                audio_link, headers, request_options, download_path
            )
        except (
            requests.exceptions.ProxyError,
            requests.exceptions.ConnectTimeout,
        ) as exc:
            if not proxies:
                # The exception text holds the full episode URL; keep it out
                # of the job status and the log.
                self.last_error = (
                    "proxy not reachable"
                    if isinstance(exc, requests.exceptions.ProxyError)
                    else f"network error ({type(exc).__name__})"
                )
                self.logger.warning("Download failed: %s", self.last_error)
                return None
            return self._download_without_proxy(
                f"DOWNLOAD_PROXY {_redact_proxy(proxies['https'])} failed: "
                f"{proxy_failure_reason(exc)}",
                audio_link,
                headers,
                download_path,
            )
        except requests.RequestException as exc:
            self.last_error = f"network error ({type(exc).__name__})"
            self.logger.warning("Download failed: %s", self.last_error)
            return None

    def _download_without_proxy(
        self,
        proxy_error: str,
        audio_link: str,
        headers: dict[str, Any],
        download_path: str,
    ) -> str | None:
        """Fall back to a direct download when the proxy is unreachable."""
        if not proxy_fallback_enabled():
            self.last_error = proxy_error
            self.logger.warning("Download failed: %s", self.last_error)
            return None
        self.logger.warning(
            "%s; downloading directly instead (ads may then be chosen for the "
            "server's location)",
            proxy_error,
        )
        try:
            result = self._fetch_to_path(audio_link, headers, {}, download_path)
        except requests.RequestException as exc:
            self.last_error = (
                f"{proxy_error}; direct download: network error ({type(exc).__name__})"
            )
            self.logger.warning("Download failed: %s", self.last_error)
            return None
        if result is None:
            self.last_error = f"{proxy_error}; direct download: {self.last_error}"
        return result

    def _fetch_to_path(
        self,
        audio_link: str,
        headers: dict[str, Any],
        request_options: dict[str, Any],
        download_path: str,
    ) -> str | None:
        """Download audio_link to download_path; None on a non-200 answer."""
        with requests.get(
            audio_link, stream=True, timeout=60, headers=headers, **request_options
        ) as response:
            if response.status_code != 200:
                self.last_error = f"HTTP {response.status_code}"
                self.logger.info(
                    f"Failed to download the podcast episode, response: {response.status_code}"
                )
                return None
            # Write to a side file and move it into place only when complete:
            # a download cut off midway must not be mistaken for the finished
            # episode ("already downloaded") next time.
            partial_path = download_path + ".part"
            try:
                with open(partial_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                os.replace(partial_path, download_path)
            finally:
                if os.path.exists(partial_path):
                    os.remove(partial_path)
            self.logger.info("Download complete.")
        return download_path

    def get_and_make_download_path(self, post_title: str) -> Path:
        """
        Generate the download path for a post and create necessary directories.

        Args:
            post_title: The title of the post to generate a path for

        Returns:
            Path object for the download location
        """
        sanitized_title = sanitize_title(post_title)

        post_directory = sanitized_title
        post_filename = sanitized_title + ".mp3"

        post_directory_path = Path(self.download_dir) / post_directory

        post_directory_path.mkdir(parents=True, exist_ok=True)

        return post_directory_path / post_filename


def sanitize_title(title: str) -> str:
    """Sanitize a title for use in file paths."""
    return re.sub(r"[^a-zA-Z0-9\s]", "", title)


def find_audio_link(entry: Any) -> str:
    """Find the audio link in a feed entry."""
    audio_mime_types: set[str] = {
        "audio/mpeg",
        "audio/mp3",
        "audio/x-mp3",
        "audio/mpeg3",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/opus",
        "audio/flac",
    }

    for url in _iter_enclosure_audio_urls(entry, audio_mime_types):
        return url
    for url in _iter_link_audio_urls(entry, audio_mime_types, match_any_audio=False):
        return url
    for url in _iter_link_audio_urls(entry, audio_mime_types, match_any_audio=True):
        return url

    return str(getattr(entry, "id", ""))


def _iter_enclosure_audio_urls(entry: Any, audio_mime_types: set[str]) -> Iterator[str]:
    enclosures = getattr(entry, "enclosures", None) or []
    for enclosure in enclosures:
        enc_type = (getattr(enclosure, "type", "") or "").lower()
        if enc_type not in audio_mime_types:
            continue
        href = getattr(enclosure, "href", None)
        if href:
            yield str(href)
        url = getattr(enclosure, "url", None)
        if url:
            yield str(url)


def _iter_link_audio_urls(
    entry: Any,
    audio_mime_types: set[str],
    *,
    match_any_audio: bool,
) -> Iterator[str]:
    links = getattr(entry, "links", None) or []
    for link in links:
        link_type = (getattr(link, "type", "") or "").lower()
        if match_any_audio:
            if not link_type.startswith("audio/"):
                continue
        elif link_type not in audio_mime_types:
            continue

        href = getattr(link, "href", None)
        if href:
            yield str(href)


# Backward compatibility - create a default instance
_default_downloader = PodcastDownloader()


def download_episode(post: Post, dest_path: str) -> str | None:
    return _default_downloader.download_episode(post, dest_path)


def get_and_make_download_path(post_title: str) -> Path:
    return _default_downloader.get_and_make_download_path(post_title)
