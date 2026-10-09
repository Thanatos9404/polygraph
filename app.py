"""Vercel entry point: Vercel detects this FastAPI app and serves every route from it."""

from polygraph.server import app  # noqa: F401
