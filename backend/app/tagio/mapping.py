from __future__ import annotations

UNIFIED_FIELDS = [
    "TITLE",
    "ARTIST",
    "ALBUMARTIST",
    "ALBUM",
    "DATE",
    "TRACKNUMBER",
    "TRACKTOTAL",
    "DISCNUMBER",
    "DISCTOTAL",
    "GENRE",
    "LABEL",
    "CATALOGNUMBER",
    "BARCODE",
    "ISRC",
    "MUSICBRAINZ_ALBUMID",
    "MUSICBRAINZ_TRACKID",
]

ALBUM_FIELDS = [
    "ALBUM",
    "ALBUMARTIST",
    "DATE",
    "GENRE",
    "LABEL",
    "CATALOGNUMBER",
    "BARCODE",
    "MUSICBRAINZ_ALBUMID",
]

TRACK_FIELDS = [
    "TITLE",
    "ARTIST",
    "TRACKNUMBER",
    "TRACKTOTAL",
    "DISCNUMBER",
    "DISCTOTAL",
    "ISRC",
    "MUSICBRAINZ_TRACKID",
]

ID3_TEXT = {
    "TITLE": "TIT2",
    "ARTIST": "TPE1",
    "ALBUMARTIST": "TPE2",
    "ALBUM": "TALB",
    "DATE": "TDRC",
    "GENRE": "TCON",
    "LABEL": "TPUB",
    "ISRC": "TSRC",
}

ID3_TXXX = {
    "CATALOGNUMBER": "CATALOGNUMBER",
    "BARCODE": "BARCODE",
    "MUSICBRAINZ_ALBUMID": "MUSICBRAINZ_ALBUMID",
    "MUSICBRAINZ_TRACKID": "MUSICBRAINZ_TRACKID",
}

MP4_ATOMS = {
    "TITLE": "\xa9nam",
    "ARTIST": "\xa9ART",
    "ALBUMARTIST": "aART",
    "ALBUM": "\xa9alb",
    "DATE": "\xa9day",
    "GENRE": "\xa9gen",
}

MP4_FREEFORM = {
    "LABEL": "LABEL",
    "CATALOGNUMBER": "CATALOGNUMBER",
    "BARCODE": "BARCODE",
    "ISRC": "ISRC",
    "MUSICBRAINZ_ALBUMID": "MUSICBRAINZ_ALBUMID",
    "MUSICBRAINZ_TRACKID": "MUSICBRAINZ_TRACKID",
}

APE_KEYS = {
    "TITLE": "Title",
    "ARTIST": "Artist",
    "ALBUMARTIST": "Album Artist",
    "ALBUM": "Album",
    "DATE": "Year",
    "TRACKNUMBER": "Track",
    "DISCNUMBER": "Disc",
    "GENRE": "Genre",
    "LABEL": "Label",
    "CATALOGNUMBER": "CatalogNumber",
    "BARCODE": "Barcode",
    "ISRC": "ISRC",
    "MUSICBRAINZ_ALBUMID": "MusicBrainz Album Id",
    "MUSICBRAINZ_TRACKID": "MusicBrainz Track Id",
}

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".mp4", ".ape", ".wav", ".ogg"}
