# Wrapper for Qo-DL Reborn. This is a sligthly modified version
# of qopy, originally written by Sorrow446. All credits to the
# original author.

import hashlib
import logging
import time

import httpx

from qobuz_dl.color import GREEN, YELLOW
from qobuz_dl.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)

RESET = "Reset your credentials with 'qobuz-dl -r'"

logger = logging.getLogger(__name__)


class Client:
    def __init__(self, email, pwd, app_id, secrets):
        logger.info(f"{YELLOW}Logging...")
        self.secrets = secrets
        self.id = str(app_id)
        self.base = "https://www.qobuz.com/api.json/0.2/"
        self.sec = None
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0",
                "X-App-Id": self.id,
                "Content-Type": "application/json;charset=UTF-8",
            }
        )

    async def initialize(self, email, pwd):
        await self.auth(email, pwd)
        await self.cfg_setup()

    async def api_call(self, epoint, **kwargs):
        params = {}
        if epoint == "user/login":
            params = {
                "email": kwargs["email"],
                "password": kwargs["pwd"],
                "app_id": self.id,
            }
        elif epoint == "track/get":
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

        if epoint == "user/login":
            if r.status_code == 401:
                raise AuthenticationError("Invalid credentials.\n" + RESET)
            if r.status_code == 400:
                raise InvalidAppIdError("Invalid app id.\n" + RESET)
            logger.info(f"{GREEN}Logged: OK")
        elif epoint == "track/getFileUrl" and r.status_code == 400:
            raise InvalidAppSecretError(f"Invalid app secret: {r.json()}.\n" + RESET)

        r.raise_for_status()
        return r.json()

    async def auth(self, email, pwd):
        usr_info = await self.api_call("user/login", email=email, pwd=pwd)
        if not usr_info["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")
        self.uat = usr_info["user_auth_token"]
        self.client.headers["X-User-Auth-Token"] = self.uat
        self.label = usr_info["user"]["credential"]["parameters"]["short_label"]
        logger.info(f"{GREEN}Membership: {self.label}")

    async def multi_meta(self, epoint, key, id, type):
        offset = 0
        while True:
            j = await self.api_call(epoint, id=id, offset=offset, type=type)
            yield j
            if offset == 0:
                total = j.get(key, 0)
            total -= 500
            if total <= 0:
                break
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
