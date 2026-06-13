import asyncio
import configparser
import glob
import logging
import os
import sys
from typing import Any, Awaitable, Callable, Dict, Optional

import click

from qobuz_dl2.bundle import Bundle
from qobuz_dl2.color import GREEN, RED, RESET, YELLOW
from qobuz_dl2.core import QobuzDL
from qobuz_dl2.downloader import DEFAULT_FOLDER, DEFAULT_TRACK
from qobuz_dl2.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppSecretError,
)

# Reset styling at the end of every line so colors don't bleed (colorama's old
# autoreset behavior, reproduced without the dependency).
logging.basicConfig(level=logging.INFO, format=f"%(message)s{RESET}")

if os.name == "nt":
    # Ensure a valid string path even if APPDATA is unset
    OS_CONFIG = os.environ.get("APPDATA") or os.path.expanduser("~")
else:
    OS_CONFIG = os.path.expanduser("~/.config")

CONFIG_PATH = os.path.join(OS_CONFIG, "qobuz-dl")
CONFIG_FILE = os.path.join(CONFIG_PATH, "config.ini")
QOBUZ_DB = os.path.join(CONFIG_PATH, "qobuz_dl.db")


TOKEN_PROMPT = (
    "Enter your Qobuz user_auth_token.\n"
    "Qobuz removed email/password login, so qobuz-dl authenticates with a\n"
    "token from a logged-in browser session.\n"
    "\n"
    "EASIEST: leave this blank and afterwards run 'qobuz-dl2 login' to capture\n"
    "the token automatically in a browser window (needs the [browser] extra).\n"
    "\n"
    "Or paste it manually: log in at https://play.qobuz.com, open\n"
    "DevTools > Network, filter by 'login', click the 'user/login' request,\n"
    "open the Response tab, and copy the value of 'user_auth_token'.\n"
    "- "
)


def _reset_config(config_file: str) -> None:
    logging.info(f"{YELLOW}Creating config file: {config_file}")
    config = configparser.ConfigParser()
    config["DEFAULT"]["email"] = input("Enter your email (optional, for reference):\n- ")
    # The token is stored verbatim in the historical "password" field so existing
    # config files keep working. It must NOT be hashed.
    config["DEFAULT"]["password"] = input(TOKEN_PROMPT).strip()
    config["DEFAULT"]["default_folder"] = (
        input("Folder for downloads (leave empty for default 'Qobuz Downloads')\n- ")
        or "Qobuz Downloads"
    )
    config["DEFAULT"]["default_quality"] = (
        input(
            "Download quality (5, 6, 7, 27) "
            "[320, LOSSLESS, 24B <96KHZ, 24B >96KHZ]"
            "\n(leave empty for default '6')\n- "
        )
        or "6"
    )
    config["DEFAULT"]["default_limit"] = "20"
    config["DEFAULT"]["no_m3u"] = "false"
    config["DEFAULT"]["albums_only"] = "false"
    config["DEFAULT"]["no_fallback"] = "false"
    config["DEFAULT"]["og_cover"] = "false"
    config["DEFAULT"]["embed_art"] = "false"
    config["DEFAULT"]["no_cover"] = "false"
    config["DEFAULT"]["no_database"] = "false"
    logging.info(f"{YELLOW}Getting tokens. Please wait...")
    bundle = Bundle()
    config["DEFAULT"]["app_id"] = str(bundle.get_app_id())
    config["DEFAULT"]["secrets"] = ",".join(bundle.get_secrets().values())
    config["DEFAULT"]["folder_format"] = DEFAULT_FOLDER
    config["DEFAULT"]["track_format"] = DEFAULT_TRACK
    config["DEFAULT"]["smart_discography"] = "false"
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w") as configfile:
        config.write(configfile)
    logging.info(
        f"{GREEN}Config file updated. Edit more options in {config_file}"
        "\nso you don't have to call custom flags every time you run "
        "a qobuz-dl2 command."
    )


def _save_token(token: str) -> None:
    """Persist a refreshed user_auth_token back to the config file."""
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    cfg["DEFAULT"]["password"] = token
    with open(CONFIG_FILE, "w") as f:
        cfg.write(f)


def _remove_leftovers(directory: str) -> None:
    directory = os.path.join(directory, "**", ".*.tmp")
    for i in glob.glob(directory, recursive=True):
        try:
            os.remove(i)
        except Exception:
            pass


def _ensure_config_exists() -> None:
    if not os.path.isdir(CONFIG_PATH) or not os.path.isfile(CONFIG_FILE):
        os.makedirs(CONFIG_PATH, exist_ok=True)
        _reset_config(CONFIG_FILE)


def _load_config() -> Dict[str, Any]:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    try:
        email = cfg["DEFAULT"].get("email", "")
        password = cfg["DEFAULT"]["password"]
        default_folder = cfg["DEFAULT"]["default_folder"]
        default_limit = cfg["DEFAULT"]["default_limit"]
        default_quality = cfg["DEFAULT"]["default_quality"]
        no_m3u = cfg.getboolean("DEFAULT", "no_m3u")
        albums_only = cfg.getboolean("DEFAULT", "albums_only")
        no_fallback = cfg.getboolean("DEFAULT", "no_fallback")
        og_cover = cfg.getboolean("DEFAULT", "og_cover")
        embed_art = cfg.getboolean("DEFAULT", "embed_art")
        no_cover = cfg.getboolean("DEFAULT", "no_cover")
        no_database = cfg.getboolean("DEFAULT", "no_database")
        app_id = cfg["DEFAULT"]["app_id"]
        smart_discography = cfg.getboolean("DEFAULT", "smart_discography")
        folder_format = cfg["DEFAULT"]["folder_format"]
        track_format = cfg["DEFAULT"]["track_format"]
        secrets = [s for s in cfg["DEFAULT"]["secrets"].split(",") if s]
    except (KeyError, UnicodeDecodeError, configparser.Error) as error:
        raise RuntimeError(
            f"{RED}Your config file is corrupted: {error}! "
            "Run 'qobuz-dl2 -r' to fix this."
        )
    return {
        "email": email,
        "password": password,
        "app_id": app_id,
        "secrets": secrets,
        "defaults": {
            "default_folder": default_folder,
            "default_limit": int(default_limit) if str(default_limit).isdigit() else 20,
            "default_quality": (
                int(default_quality) if str(default_quality).isdigit() else 6
            ),
            "no_m3u": no_m3u,
            "albums_only": albums_only,
            "no_fallback": no_fallback,
            "og_cover": og_cover,
            "embed_art": embed_art,
            "no_cover": no_cover,
            "no_database": no_database,
            "folder_format": folder_format,
            "track_format": track_format,
            "smart_discography": smart_discography,
        },
    }


async def _build_qobuz(
    ctx: click.Context,
    *,
    directory: Optional[str] = None,
    quality: Optional[int] = None,
    embed_art: Optional[bool] = None,
    albums_only: Optional[bool] = None,
    no_m3u: Optional[bool] = None,
    no_fallback: Optional[bool] = None,
    og_cover: Optional[bool] = None,
    no_cover: Optional[bool] = None,
    no_db: Optional[bool] = None,
    folder_format: Optional[str] = None,
    track_format: Optional[str] = None,
    smart_discography: Optional[bool] = None,
) -> QobuzDL:
    cfg = ctx.obj
    dflt = cfg["defaults"]
    effective = {
        "directory": directory or dflt["default_folder"],
        "quality": int(quality if quality is not None else dflt["default_quality"]),
        "embed_art": bool(embed_art if embed_art is not None else dflt["embed_art"]),
        "ignore_singles_eps": bool(
            albums_only if albums_only is not None else dflt["albums_only"]
        ),
        "no_m3u_for_playlists": bool(no_m3u if no_m3u is not None else dflt["no_m3u"]),
        "quality_fallback": not (
            no_fallback if no_fallback is not None else dflt["no_fallback"]
        ),
        "cover_og_quality": bool(
            og_cover if og_cover is not None else dflt["og_cover"]
        ),
        "no_cover": bool(no_cover if no_cover is not None else dflt["no_cover"]),
        "downloads_db": (
            None if (no_db if no_db is not None else dflt["no_database"]) else QOBUZ_DB
        ),
        "folder_format": folder_format or dflt["folder_format"],
        "track_format": track_format or dflt["track_format"],
        "smart_discography": bool(
            smart_discography
            if smart_discography is not None
            else dflt["smart_discography"]
        ),
    }
    q = QobuzDL(**effective)
    await q.initialize_client(
        cfg["password"], cfg["app_id"], cfg["secrets"], on_token_refresh=_save_token
    )
    return q


def _common_options() -> Callable:
    def decorator(f: Callable) -> Callable:
        options = [
            click.option(
                "-d",
                "--directory",
                metavar="PATH",
                type=click.Path(path_type=str),
                help="directory for downloads (default from config)",
            ),
            click.option(
                "-q",
                "--quality",
                metavar="int",
                type=int,
                help='audio "quality" (5, 6, 7, 27)',
            ),
            click.option(
                "--albums-only",
                is_flag=True,
                help="don't download singles, EPs and VA releases",
            ),
            click.option(
                "--no-m3u",
                is_flag=True,
                help="don't create .m3u files when downloading playlists",
            ),
            click.option(
                "--no-fallback",
                is_flag=True,
                help="disable quality fallback (skip releases not available in set quality)",
            ),
            click.option(
                "-e", "--embed-art", is_flag=True, help="embed cover art into files"
            ),
            click.option(
                "--og-cover",
                is_flag=True,
                help="download cover art in its original quality (bigger file)",
            ),
            click.option("--no-cover", is_flag=True, help="don't download cover art"),
            click.option("--no-db", is_flag=True, help="don't call the database"),
            click.option(
                "-ff",
                "--folder-format",
                metavar="PATTERN",
                help="pattern for formatting folder names",
            ),
            click.option(
                "-tf",
                "--track-format",
                metavar="PATTERN",
                help="pattern for formatting track names",
            ),
            click.option(
                "-s",
                "--smart-discography",
                is_flag=True,
                help="Enable heuristics to reduce spam-like albums in artist discographies",
            ),
        ]
        for opt in reversed(options):
            f = opt(f)
        return f

    return decorator


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("-r", "--reset", is_flag=True, help="create/reset config file")
@click.option(
    "-p", "--purge", is_flag=True, help="purge/delete downloaded-IDs database"
)
@click.option("-sc", "--show-config", is_flag=True, help="show configuration")
@click.pass_context
def cli(ctx: click.Context, reset: bool, purge: bool, show_config: bool) -> None:
    """The ultimate Qobuz music downloader."""
    # Bootstrapping and config lifecycle
    os.makedirs(CONFIG_PATH, exist_ok=True)
    if reset:
        _reset_config(CONFIG_FILE)
        ctx.exit(0)

    _ensure_config_exists()

    if show_config:
        click.echo(f"Configuration: {CONFIG_FILE}\nDatabase: {QOBUZ_DB}\n---")
        with open(CONFIG_FILE, "r") as f:
            click.echo(f.read())
        ctx.exit(0)

    if purge:
        try:
            os.remove(QOBUZ_DB)
        except FileNotFoundError:
            pass
        click.echo(f"{GREEN}The database was deleted.{RESET}")
        ctx.exit(0)

    try:
        ctx.obj = _load_config()
    except RuntimeError as e:
        click.echo(f"{str(e)}{RESET}")
        ctx.exit(2)


def _run(
    ctx: click.Context,
    opts: Dict[str, Any],
    action: Callable[[QobuzDL], Awaitable[None]],
) -> None:
    """Build a client from the shared options and run an async action with
    uniform auth-error handling, Ctrl-C handling and temp-file cleanup."""

    async def runner() -> None:
        try:
            q = await _build_qobuz(ctx, **opts)
        except (
            AuthenticationError,
            IneligibleError,
            InvalidAppSecretError,
        ) as e:
            logging.error(f"{RED}{e}")
            return
        try:
            await action(q)
        except KeyboardInterrupt:
            logging.info(
                f"{RED}Interrupted by user\n{YELLOW}Already downloaded items will "
                "be skipped if you try to download the same releases again."
            )
        finally:
            await q.aclose()
            _remove_leftovers(q.directory)

    asyncio.run(runner())


@cli.command("fun")
@_common_options()
@click.option(
    "-l",
    "--limit",
    metavar="int",
    type=int,
    help="limit of search results (default from config)",
)
@click.pass_context
def fun_cmd(ctx: click.Context, limit: Optional[int], **opts: Any) -> None:
    """Interactive mode."""

    async def action(q: QobuzDL) -> None:
        dflt_limit = ctx.obj["defaults"]["default_limit"]
        q.interactive_limit = int(limit) if limit is not None else int(dflt_limit)
        await q.interactive()

    _run(ctx, opts, action)


@cli.command("dl")
@_common_options()
@click.argument("source", nargs=-1, required=True)
@click.pass_context
def dl_cmd(ctx: click.Context, source: tuple[str, ...], **opts: Any) -> None:
    """Input mode: download by album/track/artist/label/playlist/last.fm-playlist URL(s) or a text file."""
    _run(ctx, opts, lambda q: q.download_list_of_urls(list(source)))


@cli.command("lucky")
@_common_options()
@click.option(
    "-t",
    "--type",
    "type_",
    default=None,
    show_default=False,
    help="type of items to search (artist, album, track, playlist)",
)
@click.option(
    "-n",
    "--number",
    metavar="int",
    type=int,
    default=None,
    show_default=False,
    help="number of results to download",
)
@click.argument("query", nargs=-1, required=True)
@click.pass_context
def lucky_cmd(
    ctx: click.Context,
    query: tuple[str, ...],
    type_: Optional[str],
    number: Optional[int],
    **opts: Any,
) -> None:
    """Lucky mode: Download the first <n> results from a Qobuz search."""

    async def action(q: QobuzDL) -> None:
        q.lucky_type = (type_ or "album").lower()
        q.lucky_limit = int(number) if number is not None else 1
        await q.lucky_mode(" ".join(query))

    _run(ctx, opts, action)


@cli.command("login")
@click.option(
    "--timeout",
    type=int,
    default=300,
    show_default=True,
    help="seconds to wait for you to finish logging in",
)
@click.pass_context
def login_cmd(ctx: click.Context, timeout: int) -> None:
    """Open a browser to log in to Qobuz and capture your token automatically."""
    from qobuz_dl2.browser_login import fetch_token_via_browser

    click.echo(
        f"{YELLOW}Opening a browser window. Log in to Qobuz as usual "
        "(solve any captcha yourself).\nThis window will close and your token "
        "will be saved automatically once you're in."
    )
    try:
        token = fetch_token_via_browser(timeout=timeout)
    except RuntimeError as e:
        click.echo(f"{RED}{e}{RESET}")
        ctx.exit(1)
        return
    if not token:
        click.echo(
            f"{RED}No token captured (login not completed or window closed). "
            "Please try again."
        )
        ctx.exit(1)
        return
    _save_token(token)
    click.echo(f"{GREEN}Token captured and saved to {CONFIG_FILE}{RESET}")


@cli.command("set-token")
@click.argument("token")
def set_token_cmd(token: str) -> None:
    """Store a fresh Qobuz user_auth_token in the config (no browser needed)."""
    _save_token(token.strip())
    click.echo(f"{GREEN}Token saved to {CONFIG_FILE}{RESET}")


def main() -> int:
    # If no subcommand provided, Click will show help automatically.
    try:
        cli(prog_name="qobuz-dl2", standalone_mode=True)
        return 0
    except SystemExit as e:
        # Normalize exit code
        return int(e.code) if e.code is not None else 0


if __name__ == "__main__":
    sys.exit(main())
