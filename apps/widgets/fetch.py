# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feed fetching uses the core's safe fetcher (``apps.core.safefetch``, ADR-0023)."""
from apps.core.safefetch import MAX_BYTES, Fetched, FetchError, check_url, get

__all__ = ["MAX_BYTES", "FetchError", "Fetched", "check_url", "get"]
