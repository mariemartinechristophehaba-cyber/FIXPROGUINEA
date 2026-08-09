"""Point d'entree serverless pour Vercel.

Vercel recherche une variable nommee `app` exposant une application WSGI.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fixpro_app import app  # noqa: E402

__all__ = ["app"]
