"""Gitective: GitLab merge request process checker."""

__version__ = "1.2.0"
APP_NAME = "Gitective"
BUILD = ""  # Release number (e.g. 2026.10.29-1), written by tools/make_edition.py; empty when run from git.

# The user edition (GDPR) is built without the admin blocks below and elsewhere (tools/make_edition.py).
EDITION = "user"
# admin:begin
EDITION = "admin"
# admin:end
