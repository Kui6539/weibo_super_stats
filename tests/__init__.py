"""Unit tests for extracted backend modules.

Importing this package redirects the cache root to a throwaway directory
unless the caller already set one. Without this, any test that builds a
CacheStore without an explicit ``cache_root`` writes into the real project
``cache/`` and never cleans up -- the repository had accumulated 160 leaked
``tmp*`` directories that way, and output cleanup and history scanning both
treat them as real runs.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

from core.cache import CACHE_ROOT_ENV

if not os.environ.get(CACHE_ROOT_ENV):
    _sandbox_cache_root = tempfile.mkdtemp(prefix="weibo_stats_test_cache_")
    os.environ[CACHE_ROOT_ENV] = _sandbox_cache_root
    atexit.register(shutil.rmtree, _sandbox_cache_root, ignore_errors=True)
