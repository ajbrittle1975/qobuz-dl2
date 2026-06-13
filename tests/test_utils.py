import pytest

from qobuz_dl2.utils import (
    PartialFormatter,
    format_duration,
    get_url_info,
    smart_discography_filter,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://www.qobuz.com/us-en/album/some-name/abc123",
            ("album", "abc123"),
        ),
        ("https://open.qobuz.com/track/55", ("track", "55")),
        ("https://play.qobuz.com/playlist/999", ("playlist", "999")),
        ("/us-en/artist/-/777", ("artist", "777")),
        ("https://www.qobuz.com/us-en/label/foo/42", ("label", "42")),
    ],
)
def test_get_url_info_valid(url, expected):
    assert get_url_info(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/not/qobuz",
        "garbage",
        "https://www.qobuz.com/us-en/podcast/foo/1",
    ],
)
def test_get_url_info_invalid_raises(url):
    with pytest.raises(ValueError):
        get_url_info(url)


def test_format_duration():
    assert format_duration(0) == "00:00:00"
    assert format_duration(61) == "00:01:01"
    assert format_duration(3661) == "01:01:01"


def test_partial_formatter_missing_key():
    fmt = PartialFormatter()
    # missing key -> "n/a", present key -> value
    assert fmt.format("{artist} - {title}", title="Song") == "n/a - Song"


def test_partial_formatter_present():
    fmt = PartialFormatter()
    assert fmt.format("{a}/{b}", a="x", b="y") == "x/y"


def _album(title, artist, bit_depth=24, sampling_rate=96, version=None):
    return {
        "title": title,
        "version": version,
        "artist": {"name": artist},
        "maximum_bit_depth": bit_depth,
        "maximum_sampling_rate": sampling_rate,
        "id": title,
    }


def test_smart_discography_filter_drops_other_artists_and_dupes():
    contents = [
        {
            "name": "Real Artist",
            "albums": {
                "items": [
                    _album("Greatest Hits", "Real Artist", 24, 96),
                    # duplicate (lower quality) of the same album -> dropped
                    _album("Greatest Hits", "Real Artist", 16, 44),
                    # different artist feature -> dropped
                    _album("Compilation", "Other Artist"),
                ]
            },
        }
    ]
    result = smart_discography_filter(contents)
    titles = [a["title"] for a in result]
    assert titles == ["Greatest Hits"]
    assert result[0]["maximum_bit_depth"] == 24
