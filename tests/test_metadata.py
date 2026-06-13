from qobuz_dl2.metadata import _format_copyright, _format_genres, _get_title


def test_format_genres_dedupes_and_splits():
    g = ["Pop/Rock", "Pop/Rock→Rock", "Pop/Rock→Rock→Alternatif et Indé"]
    assert _format_genres(g) == "Pop, Rock, Alternatif et Indé"


def test_format_copyright_symbols():
    assert _format_copyright("(P) 2020 (C) Label") == "℗ 2020 © Label"


def test_format_copyright_empty():
    assert _format_copyright("") == ""


def test_get_title_plain():
    assert _get_title({"title": "Song"}) == "Song"


def test_get_title_with_version():
    assert _get_title({"title": "Song", "version": "Remix"}) == "Song (Remix)"


def test_get_title_classical_work():
    out = _get_title({"title": "Allegro", "work": "Symphony No. 5"})
    assert out == "Symphony No. 5: Allegro"
