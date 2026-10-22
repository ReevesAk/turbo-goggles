"""Shared constants for the test suite."""

import secrets

# Generated per test run so no credential-like literal lives in the repo.
# Use only where the value is never typed back in (e.g. force_authenticate).
TEST_PASSWORD = secrets.token_urlsafe(16)
