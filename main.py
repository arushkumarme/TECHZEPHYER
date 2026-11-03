"""Vercel entrypoint for the "app" service (see vercel.json).

Vercel needs a module file it can find from the project root, and the package lives under
src/. Import the installed package rather than pointing Vercel at src/netcoop/api/app.py:
that would load a second copy of the module, and the feature-flagged routers would register
on the other copy's EXTENSIONS list.
"""

from netcoop.api.app import app

__all__ = ["app"]
