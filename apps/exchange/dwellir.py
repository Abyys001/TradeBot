"""Dwellir archive downloader.

Downloads pre-aggregated OHLCV Parquet snapshots from the Dwellir endpoint
and feeds them into the existing local archive-import pipeline without any
row-by-row SQL interaction.

URL pattern (configurable via DWELLIR_BASE_URL setting):
    {base}/{coin}/{interval}.parquet
    e.g. https://snapshots.dwellir.com/hl/BTC/1h.parquet

The downloaded file is streamed to a temp directory, imported via
``archive_importer.import_archive``, then deleted.
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://snapshots.dwellir.com/hl"
_CHUNK = 8 * 1024 * 1024  # 8 MB streaming chunk
_VALID_CONTENT_TYPES = {
    "application/octet-stream",
    "application/x-parquet",
    "application/parquet",
    "binary/octet-stream",
}


class DwellirDownloadError(Exception):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET"},
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


class DwellirDownloader:
    """Stream-download a Dwellir OHLCV Parquet archive to a local temp file."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: int = 300,
    ) -> None:
        raw = base_url or getattr(settings, "DWELLIR_BASE_URL", "") or _DEFAULT_BASE_URL
        self.base_url = raw.rstrip("/")
        self.timeout = timeout

    def build_url(self, coin: str, interval: str) -> str:
        return f"{self.base_url}/{coin.upper()}/{interval}.parquet"

    def download(self, coin: str, interval: str, *, dest_dir: Path) -> Path:
        """Download the archive and save it to *dest_dir*.

        Returns the absolute path of the downloaded file.
        Raises :class:`DwellirDownloadError` on any HTTP or I/O failure.
        """
        url = self.build_url(coin, interval)
        dest = dest_dir / f"{coin.upper()}_{interval}_{int(time.time())}.parquet"

        logger.info("dwellir download start url=%s dest=%s", url, dest)

        try:
            with _session() as sess:
                resp = sess.get(url, stream=True, timeout=self.timeout)
        except requests.RequestException as exc:
            raise DwellirDownloadError(f"HTTP error for {url}: {exc}") from exc

        if resp.status_code != 200:
            raise DwellirDownloadError(
                f"Non-200 response {resp.status_code} for {url}"
            )

        ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ct and ct not in _VALID_CONTENT_TYPES:
            logger.warning("dwellir unexpected Content-Type %r for %s", ct, url)

        try:
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=_CHUNK):
                    if chunk:
                        fh.write(chunk)
        except OSError as exc:
            dest.unlink(missing_ok=True)
            raise DwellirDownloadError(f"Write failed for {dest}: {exc}") from exc

        size_mb = dest.stat().st_size / (1024 ** 2)
        logger.info("dwellir download done coin=%s interval=%s size=%.1f MB", coin, interval, size_mb)
        return dest
