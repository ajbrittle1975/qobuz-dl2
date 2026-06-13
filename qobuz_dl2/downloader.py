import asyncio
import logging
import os
from typing import Optional, Tuple

import httpx
from pathvalidate import sanitize_filename, sanitize_filepath
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

import qobuz_dl2.metadata as metadata
from qobuz_dl2.color import GREEN, OFF, RED, YELLOW
from qobuz_dl2.exceptions import NonStreamable

QL_DOWNGRADE = "FormatRestrictedByFormatAvailability"
# used in case of error
DEFAULT_FORMATS = {
    "MP3": [
        "{artist} - {album} ({year}) [MP3]",
        "{tracknumber}. {tracktitle}",
    ],
    "Unknown": [
        "{artist} - {album}",
        "{tracknumber}. {tracktitle}",
    ],
}

DEFAULT_FOLDER = "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"
DEFAULT_TRACK = "{tracknumber}. {tracktitle}"

logger = logging.getLogger(__name__)


class Download:
    def __init__(
        self,
        client,
        item_id: str,
        path: str,
        quality: int,
        embed_art: bool = False,
        albums_only: bool = False,
        downgrade_quality: bool = False,
        cover_og_quality: bool = False,
        no_cover: bool = False,
        folder_format=None,
        track_format=None,
        limit: int = 4,
    ):
        self.client = client
        self.item_id = item_id
        self.path = path
        self.quality = quality
        self.albums_only = albums_only
        self.embed_art = embed_art
        self.downgrade_quality = downgrade_quality
        self.cover_og_quality = cover_og_quality
        self.no_cover = no_cover
        self.folder_format = folder_format or DEFAULT_FOLDER
        self.track_format = track_format or DEFAULT_TRACK
        self.semaphore = asyncio.Semaphore(limit)
        self.progress = Progress(
            TextColumn("[bold blue]{task.description}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
        )

    async def download_id_by_type(self, track=True):
        # Progress is a synchronous context manager; httpx.AsyncClient is async.
        # Nest them to satisfy type checkers and runtime semantics.
        with self.progress:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                if not track:
                    await self.download_release(client)
                else:
                    await self.download_track(client)

    async def download_release(self, client: httpx.AsyncClient):
        meta = await self.client.get_album_meta(self.item_id)

        if not meta.get("streamable"):
            raise NonStreamable("This release is not streamable")

        if self.albums_only and (
            meta.get("release_type") != "album"
            or _safe_get(meta, "artist", "name") == "Various Artists"
        ):
            logger.info(f'{OFF}Ignoring Single/EP/VA: {meta.get("title", "n/a")}')
            return

        album_title = _get_title(meta)
        format_info = await self._get_format(meta)
        file_format, quality_met, bit_depth, sampling_rate = format_info

        if not self.downgrade_quality and not quality_met:
            logger.info(
                f"{OFF}Skipping {album_title} as it doesn't meet quality requirement"
            )
            return

        logger.info(
            f"\n{YELLOW}Downloading: {album_title}\nQuality: {file_format}"
            f" ({bit_depth}/{sampling_rate})\n"
        )
        album_attr = self._get_album_attr(
            meta, album_title, file_format, bit_depth, sampling_rate
        )
        folder_format, _ = _clean_format_str(
            self.folder_format, self.track_format, file_format
        )
        sanitized_title = sanitize_filepath(folder_format.format(**album_attr))
        dirn = os.path.join(self.path, sanitized_title)
        os.makedirs(dirn, exist_ok=True)

        tasks = []
        if not self.no_cover:
            tasks.append(
                self._get_extra(
                    client,
                    meta["image"]["large"],
                    dirn,
                    og_quality=self.cover_og_quality,
                )
            )

        if "goodies" in meta:
            try:
                tasks.append(
                    self._get_extra(client, meta["goodies"][0]["url"], dirn, "booklet.pdf")
                )
            except:  # noqa
                pass

        media_numbers = [track["media_number"] for track in meta["tracks"]["items"]]
        is_multiple = len(set(media_numbers)) > 1

        for i, track in enumerate(meta["tracks"]["items"]):
            tasks.append(
                self._process_track(
                    client,
                    dirn,
                    i,
                    track,
                    meta,
                    is_multiple,
                )
            )

        await asyncio.gather(*tasks)
        logger.info(f"{GREEN}Completed")

    async def _process_track(
        self,
        client: httpx.AsyncClient,
        dirn: str,
        count: int,
        track_meta: dict,
        album_meta: dict,
        is_multiple: bool,
    ):
        async with self.semaphore:
            parse = await self.client.get_track_url(track_meta["id"], fmt_id=self.quality)
            if "sample" not in parse and parse.get("sampling_rate"):
                is_mp3 = int(self.quality) == 5
                await self._download_and_tag(
                    client,
                    dirn,
                    count,
                    parse,
                    track_meta,
                    album_meta,
                    False,
                    is_mp3,
                    track_meta["media_number"] if is_multiple else None,
                )
            else:
                logger.info(f"{OFF}Demo track. Skipping")

    async def download_track(self, client: httpx.AsyncClient):
        parse = await self.client.get_track_url(self.item_id, self.quality)

        if "sample" not in parse and parse.get("sampling_rate"):
            meta = await self.client.get_track_meta(self.item_id)
            track_title = _get_title(meta)
            artist = _safe_get(meta, "performer", "name")
            logger.info(f"\n{YELLOW}Downloading: {artist} - {track_title}")
            format_info = await self._get_format(
                meta, is_track_id=True, track_url_dict=parse
            )
            file_format, quality_met, bit_depth, sampling_rate = format_info

            if not self.downgrade_quality and not quality_met:
                logger.info(
                    f"{OFF}Skipping {track_title} as it doesn't meet quality requirement"
                )
                return

            track_attr = self._get_track_attr(
                meta, track_title, bit_depth, sampling_rate
            )
            folder_format, _ = _clean_format_str(
                self.folder_format, self.track_format, str(bit_depth)
            )
            sanitized_title = sanitize_filepath(folder_format.format(**track_attr))
            dirn = os.path.join(self.path, sanitized_title)
            os.makedirs(dirn, exist_ok=True)

            tasks = []
            if not self.no_cover:
                tasks.append(
                    self._get_extra(
                        client,
                        meta["album"]["image"]["large"],
                        dirn,
                        og_quality=self.cover_og_quality,
                    )
                )

            is_mp3 = int(self.quality) == 5
            tasks.append(
                self._download_and_tag(
                    client, dirn, 1, parse, meta, meta, True, is_mp3, None
                )
            )
            await asyncio.gather(*tasks)
        else:
            logger.info(f"{OFF}Demo track. Skipping")
        logger.info(f"{GREEN}Completed")

    async def _download_and_tag(
        self,
        client: httpx.AsyncClient,
        root_dir: str,
        tmp_count: int,
        track_url_dict: dict,
        track_metadata: dict,
        album_or_track_metadata: dict,
        is_track: bool,
        is_mp3: bool,
        multiple: Optional[int] = None,
    ):
        extension = ".mp3" if is_mp3 else ".flac"
        url = track_url_dict.get("url")
        if not url:
            logger.info(f"{OFF}Track not available for download")
            return

        if multiple:
            root_dir = os.path.join(root_dir, f"Disc {multiple}")
            os.makedirs(root_dir, exist_ok=True)

        filename = os.path.join(root_dir, f".{tmp_count:02}.tmp")
        track_title = track_metadata.get("title")
        artist = _safe_get(track_metadata, "performer", "name")
        filename_attr = self._get_filename_attr(artist, track_metadata, track_title)
        formatted_path = sanitize_filename(self.track_format.format(**filename_attr))
        # Truncate only the file name (not the directory) to stay within
        # filesystem name limits, then add the extension.
        final_file = os.path.join(root_dir, formatted_path[:250]) + extension

        if os.path.isfile(final_file):
            logger.info(f"{OFF}{track_title} was already downloaded")
            return

        await rich_download(client, url, filename, self.progress, track_title)
        tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                tag_function,
                filename,
                root_dir,
                final_file,
                track_metadata,
                album_or_track_metadata,
                is_track,
                self.embed_art,
            )
        except Exception as e:
            logger.error(f"{RED}Error tagging the file: {e}", exc_info=True)

    @staticmethod
    def _get_filename_attr(artist, track_metadata, track_title):
        return {
            "artist": artist,
            "albumartist": _safe_get(
                track_metadata, "album", "artist", "name", default=artist
            ),
            "bit_depth": track_metadata["maximum_bit_depth"],
            "sampling_rate": track_metadata["maximum_sampling_rate"],
            "tracktitle": track_title,
            "version": track_metadata.get("version"),
            "tracknumber": f"{track_metadata['track_number']:02}",
        }

    @staticmethod
    def _get_track_attr(meta, track_title, bit_depth, sampling_rate):
        return {
            "album": sanitize_filename(meta["album"]["title"]),
            "artist": sanitize_filename(meta["album"]["artist"]["name"]),
            "tracktitle": track_title,
            "year": meta["album"]["release_date_original"].split("-")[0],
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    @staticmethod
    def _get_album_attr(meta, album_title, file_format, bit_depth, sampling_rate):
        return {
            "artist": sanitize_filename(meta["artist"]["name"]),
            "album": sanitize_filename(album_title),
            "year": meta["release_date_original"].split("-")[0],
            "format": file_format,
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    async def _get_format(
        self, item_dict, is_track_id=False, track_url_dict=None
    ) -> Tuple[str, bool, Optional[int], Optional[int]]:
        quality_met = True
        if int(self.quality) == 5:
            return "MP3", quality_met, None, None

        track_dict = item_dict
        if not is_track_id:
            track_dict = item_dict["tracks"]["items"][0]

        try:
            new_track_dict = (
                await self.client.get_track_url(track_dict["id"], fmt_id=self.quality)
                if not track_url_dict
                else track_url_dict
            )
            restrictions = new_track_dict.get("restrictions")
            if isinstance(restrictions, list) and any(
                r.get("code") == QL_DOWNGRADE for r in restrictions
            ):
                quality_met = False

            return (
                "FLAC",
                quality_met,
                new_track_dict.get("bit_depth"),
                new_track_dict.get("sampling_rate"),
            )
        except (KeyError, httpx.HTTPError):
            return "Unknown", quality_met, None, None

    async def _get_extra(
        self,
        client: httpx.AsyncClient,
        item: str,
        dirn: str,
        extra: str = "cover.jpg",
        og_quality: bool = False,
    ):
        extra_file = os.path.join(dirn, extra)
        if os.path.isfile(extra_file):
            logger.info(f"{OFF}{extra} was already downloaded")
            return

        url = item.replace("_600.", "_org.") if og_quality else item
        await rich_download(client, url, extra_file, self.progress, extra)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, ConnectionError)),
)
async def _stream_to_file(
    client: httpx.AsyncClient, url: str, fname: str, progress: Progress, task_id
) -> None:
    download_size = 0
    async with client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        # Reset in case this is a retry of a partially-completed attempt.
        progress.update(task_id, total=total, completed=0)
        with open(fname, "wb") as file:
            async for data in r.aiter_bytes(chunk_size=8192):
                size = file.write(data)
                progress.update(task_id, advance=size)
                download_size += size

    if total != 0 and total != download_size:
        raise ConnectionError(f"File download was interrupted for {fname}")


async def rich_download(
    client: httpx.AsyncClient,
    url: str,
    fname: str,
    progress: Progress,
    desc: Optional[str] = None,
):
    """Asynchronously download a file with a progress bar, retrying on
    transient network errors."""
    task_id = progress.add_task(
        f"[cyan]Downloading[/] [bold magenta]{desc or fname}[/]", total=0
    )
    try:
        await _stream_to_file(client, url, fname, progress, task_id)
    finally:
        progress.update(task_id, visible=False)


def _get_title(item_dict):
    album_title = item_dict["title"]
    version = item_dict.get("version")
    if version:
        album_title = (
            f"{album_title} ({version})"
            if version.lower() not in album_title.lower()
            else album_title
        )
    return album_title




def _clean_format_str(folder: str, track: str, file_format: str) -> Tuple[str, str]:
    """Cleans up the format strings, avoids errors
    with MP3 files.
    """
    cleaned: list[str] = []
    for i, fs in enumerate((folder, track)):
        if fs.endswith(".mp3"):
            fs = fs[:-4]
        elif fs.endswith(".flac"):
            fs = fs[:-5]
        fs = fs.strip()

        # default to pre-chosen string if format is invalid
        if file_format in ("MP3", "Unknown") and (
            "bit_depth" in fs or "sampling_rate" in fs
        ):
            default = DEFAULT_FORMATS[file_format][i]
            logger.error(
                f"{RED}invalid format string for format {file_format}"
                f". defaulting to {default}"
            )
            fs = default
        cleaned.append(fs)

    # Return a fixed-length tuple to satisfy typing (Tuple[str, str])
    return cleaned[0], cleaned[1]


def _safe_get(d: dict, *keys, default=None):
    """Safely traverse nested dicts using keys, returning default if any level is missing."""
    curr = d
    for i, key in enumerate(keys):
        if not isinstance(curr, dict):
            return default
        val = curr.get(key, default)
        if val is default:
            return default
        curr = val
    return curr
