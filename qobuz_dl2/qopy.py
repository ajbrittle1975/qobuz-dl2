# Wrapper for Qo-DL Reborn. This is a slightly modified version
# of qopy, originally written by Sorrow446. All credits to the
# original author.

import hashlib
import logging
import time
from typing import Callable, Optional

import httpx

from qobuz_dl2.color import GREEN, YELLOW
from qobuz_dl2.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppSecretError,
    InvalidQuality,
)

RESET = "Reset your credentials with 'qobuz-dl2 -r'"

# Qobuz removed the direct email/password login API (migrated to an OAuth flow
# protected by reCAPTCHA). Automated login is no longer possible, so we
# authenticate with a `user_auth_token` copied from an active browser session.
TOKEN_HELP = (
    "Your Qobuz token is missing, expired or invalid.\n"
    "Grab a fresh one from your browser:\n"
    "  1. Log in at https://play.qobuz.com\n"
    "  2. Open DevTools > Network and filter by 'login'\n"
    "  3. Click the 'user/login' request, open the Response tab\n"
    "  4. Copy the value of 'user_auth_token'\n"
    "Then run 'qobuz-dl2 -r' and paste it when asked for the token."
)

logger = logging.getLogger(__name__)


class Client:
    def __init__(
        self,
        token: str,
        app_id,
        secrets,
        on_token_refresh: Optional[Callable[[str], None]] = None,
    ):
        logger.info(f"{YELLOW}Logging...")
        self.secrets = secrets
        self.id = str(app_id)
        self.token = (token or "").strip()
        self.on_token_refresh = on_token_refresh
        self.base = "https://www.qobuz.com/api.json/0.2/"
        self.sec = None
        self.uat = self.token
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0",
                "X-App-Id": self.id,
                "X-User-Auth-Token": self.token,
            },
            timeout=httpx.Timeout(30.0),
        )

    async def initialize(self):
        await self.auth()
        await self.cfg_setup()

    async def aclose(self):
        await self.client.aclose()

    async def auth(self):
        """Authenticate using a stored user_auth_token.

        The token is refreshed through the partner endpoint and, if Qobuz
        returns a new token, persisted back to the config via the
        ``on_token_refresh`` callback so the user does not have to re-copy it
        on every run.
        """
        if not self.token:
            raise AuthenticationError(TOKEN_HELP)

        try:
            r = await self.client.post(
                self.base + "user/login", data={"extra": "partner"}
            )
        except httpx.HTTPError as e:
            raise AuthenticationError(f"Could not reach Qobuz: {e}\n{RESET}")

        if r.status_code in (400, 401):
            raise AuthenticationError(TOKEN_HELP)
        r.raise_for_status()
        data = r.json()

        new_token = data.get("user_auth_token")
        if new_token and new_token != self.token:
            self.token = new_token
            if self.on_token_refresh is not None:
                try:
                    self.on_token_refresh(new_token)
                    logger.info(f"{GREEN}Token refreshed and saved")
                except Exception as e:  # pragma: no cover - best effort
                    logger.warning(f"{YELLOW}Could not save refreshed token: {e}")
        self.uat = self.token
        self.client.headers["X-User-Auth-Token"] = self.uat

        params = (data.get("user") or {}).get("credential", {}).get("parameters")
        # An empty (but present) parameters object means a free account.
        if params is not None and not params:
            raise IneligibleError("Free accounts are not eligible to download tracks.")
        self.label = (params or {}).get("short_label", "unknown")
        logger.info(f"{GREEN}Logged: OK\n{GREEN}Membership: {self.label}")

    async def api_call(self, epoint, **kwargs):
        if epoint == "track/get":
            params = {"track_id": kwargs["id"]}
        elif epoint == "album/get":
            params = {"album_id": kwargs["id"]}
        elif epoint == "playlist/get":
            params = {
                "extra": "tracks",
                "playlist_id": kwargs["id"],
                "limit": 500,
                "offset": kwargs["offset"],
            }
        elif epoint == "artist/get":
            params = {
                "artist_id": kwargs["id"],
                "limit": 500,
                "offset": kwargs["offset"],
                "extra": "albums",
            }
        elif epoint == "label/get":
            params = {
                "label_id": kwargs["id"],
                "limit": 500,
                "offset": kwargs["offset"],
                "extra": "albums",
            }
        elif epoint == "track/getFileUrl":
            unix = time.time()
            track_id = kwargs["id"]
            fmt_id = kwargs["fmt_id"]
            if int(fmt_id) not in (5, 6, 7, 27):
                raise InvalidQuality("Invalid quality id: choose between 5, 6, 7 or 27")
            r_sig = f"trackgetFileUrlformat_id{fmt_id}intentstreamtrack_id{track_id}{unix}{kwargs.get('sec', self.sec)}"
            r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
            params = {
                "request_ts": unix,
                "request_sig": r_sig_hashed,
                "track_id": track_id,
                "format_id": fmt_id,
                "intent": "stream",
            }
        else:
            params = kwargs

        r = await self.client.get(self.base + epoint, params=params)

        if r.status_code == 401:
            raise AuthenticationError(TOKEN_HELP)
        if epoint == "track/getFileUrl" and r.status_code == 400:
            raise InvalidAppSecretError(f"Invalid app secret: {r.json()}.\n" + RESET)

        r.raise_for_status()
        return r.json()

    async def multi_meta(self, epoint, key, id, type):
        offset = 0
        total = 1
        while total > 0:
            j = await self.api_call(epoint, id=id, offset=offset, type=type)
            yield j
            if offset == 0:
                total = j.get(key, 0)
            total -= 500
            offset += 500

    async def get_album_meta(self, id):
        return await self.api_call("album/get", id=id)

    async def get_track_meta(self, id):
        return await self.api_call("track/get", id=id)

    async def get_track_url(self, id, fmt_id):
        return await self.api_call("track/getFileUrl", id=id, fmt_id=fmt_id)

    async def get_artist_meta(self, id):
        return self.multi_meta("artist/get", "albums_count", id, None)

    async def get_plist_meta(self, id):
        return self.multi_meta("playlist/get", "tracks_count", id, None)

    async def get_label_meta(self, id):
        return self.multi_meta("label/get", "albums_count", id, None)

    async def search_albums(self, query, limit):
        return await self.api_call("album/search", query=query, limit=limit)

    async def search_artists(self, query, limit):
        return await self.api_call("artist/search", query=query, limit=limit)

    async def search_playlists(self, query, limit):
        return await self.api_call("playlist/search", query=query, limit=limit)

    async def search_tracks(self, query, limit):
        return await self.api_call("track/search", query=query, limit=limit)

    async def test_secret(self, sec):
        try:
            await self.api_call("track/getFileUrl", id=5966783, fmt_id=5, sec=sec)
            return True
        except InvalidAppSecretError:
            return False

    async def cfg_setup(self):
        for secret in self.secrets:
            if not secret:
                continue
            if await self.test_secret(secret):
                self.sec = secret
                return
        raise InvalidAppSecretError("Can't find any valid app secret.\n" + RESET)
