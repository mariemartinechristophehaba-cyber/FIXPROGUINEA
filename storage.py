"""Couche de stockage des fichiers pour FixPro.

Permet d'envoyer vers un stockage objet (Supabase Storage) ou de
rester sur du base64 en fallback (developement / tests).
"""

import base64
import io
import os
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    """Abstraction du stockage de fichiers."""

    @abstractmethod
    def upload(self, name, data_uri, max_size=5 * 1024 * 1024):
        """Stocke un fichier a partir d'un data URI et retourne une URL publique."""

    @abstractmethod
    def delete(self, url_or_path):
        """Supprime un fichier a partir de son URL/path."""


def _parse_data_uri(data_uri):
    if not data_uri or not data_uri.startswith("data:"):
        return None, None
    header, _, b64 = data_uri.partition(",")
    match = re.match(r"data:([^;]+);base64", header)
    if not match or not b64:
        return None, None
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None, None
    return match.group(1), raw


class Base64Storage(StorageProvider):
    """Fallback qui conserve le data URI dans la base.

    A utiliser pour les tests ou si aucun stockage objet n'est configure.
    """

    def upload(self, name, data_uri, max_size=5 * 1024 * 1024):
        mime, raw = _parse_data_uri(data_uri)
        if not mime:
            raise ValueError("Format de fichier invalide.")
        if len(raw) > max_size:
            raise ValueError("Fichier trop volumineux.")
        allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if mime not in allowed:
            raise ValueError("Type de fichier non autorise.")
        return data_uri

    def delete(self, url_or_path):
        return True


class SupabaseStorage(StorageProvider):
    """Stockage objet via Supabase Storage.

    Placeholder : l'implementation reelle utilisera supabase-py
    une fois les credentials et buckets configures.
    """

    def __init__(self, url, key, bucket="fixpro-uploads"):
        self.url = url
        self.key = key
        self.bucket = bucket

    def upload(self, name, data_uri, max_size=5 * 1024 * 1024):
        mime, raw = _parse_data_uri(data_uri)
        if not mime:
            raise ValueError("Format de fichier invalide.")
        if len(raw) > max_size:
            raise ValueError("Fichier trop volumineux.")

        ext = self._ext(mime)
        filename = f"{uuid.uuid4().hex}_{name}{ext}"

        # TODO : remplacer par appel supabase-py pour envoyer le fichier.
        # Pour l'instant, retourne une URL stable signee fictive.
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{filename}"

    def delete(self, url_or_path):
        # TODO : appeler l'API Supabase pour supprimer.
        return True

    @staticmethod
    def _ext(mime):
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
        }
        return mapping.get(mime, "")


def get_storage():
    """Retourne le provider de stockage adapte a l'environnement."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        return SupabaseStorage(supabase_url, supabase_key)
    return Base64Storage()
