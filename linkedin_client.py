"""Dünner Wrapper um die offizielle LinkedIn-Posts-API.

Es wird bewusst nur die offizielle, AGB-konforme API benutzt (OAuth-Token mit
der Berechtigung ``w_member_social``). Kein Scraping, kein Login-Nachbauen.
"""

from __future__ import annotations

import requests

API_BASE = "https://api.linkedin.com"

# LinkedIn versioniert die API monatlich (Format JJJJMM); Versionen laufen nach
# ca. 12 Monaten aus. Bei einem 426-Fehler einfach LINKEDIN_API_VERSION setzen.
DEFAULT_API_VERSION = "202506"

VALID_VISIBILITY = ("PUBLIC", "CONNECTIONS")


class LinkedInError(RuntimeError):
    """Fehler beim Aufruf der LinkedIn-API."""


class LinkedInClient:
    def __init__(
        self,
        access_token: str,
        author_urn: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        timeout: int = 30,
    ) -> None:
        if not access_token:
            raise LinkedInError(
                "Kein Access-Token gesetzt (LINKEDIN_ACCESS_TOKEN)."
            )
        self.access_token = access_token
        self._author_urn = author_urn
        self.api_version = api_version
        self.timeout = timeout

    # -- intern ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
        }

    @staticmethod
    def _fail(response: requests.Response, was: str) -> None:
        body = response.text.strip()
        if len(body) > 500:
            body = body[:500] + "…"
        raise LinkedInError(f"{was} fehlgeschlagen (HTTP {response.status_code}): {body}")

    # -- öffentlich -----------------------------------------------------

    @property
    def author_urn(self) -> str:
        """URN des postenden Accounts, bei Bedarf per API ermittelt."""
        if not self._author_urn:
            self._author_urn = self.whoami()
        return self._author_urn

    def whoami(self) -> str:
        """Ermittelt die eigene Person-URN (benötigt den Scope ``openid profile``)."""
        response = requests.get(
            f"{API_BASE}/v2/userinfo",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not response.ok:
            self._fail(response, "Abruf des Profils")

        subject = response.json().get("sub")
        if not subject:
            raise LinkedInError("Antwort von /v2/userinfo enthält kein Feld 'sub'.")
        return f"urn:li:person:{subject}"

    def create_text_post(self, text: str, visibility: str = "PUBLIC") -> str:
        """Veröffentlicht einen Textbeitrag und liefert dessen URN zurück."""
        if not text.strip():
            raise LinkedInError("Der Beitragstext ist leer.")
        if visibility not in VALID_VISIBILITY:
            raise LinkedInError(
                f"Ungültige Sichtbarkeit {visibility!r}, erlaubt: {', '.join(VALID_VISIBILITY)}"
            )

        payload = {
            "author": self.author_urn,
            "commentary": text,
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        response = requests.post(
            f"{API_BASE}/rest/posts",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            self._fail(response, "Veröffentlichen des Beitrags")

        # Die URN des neuen Beitrags kommt im Header, nicht im Body.
        return response.headers.get("x-restli-id", "")
