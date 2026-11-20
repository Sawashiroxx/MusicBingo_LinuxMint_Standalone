"""Gezogenen Song in Spotify oder YouTube öffnen.

Die App selbst sendet nichts ins Netz. Sie übergibt nur eine Adresse an die
Spotify-Desktop-App (lokal über MPRIS oder das spotify:-Schema) bzw. an den
Standardbrowser, so als hätte man den Link selbst angeklickt.
"""
from dataclasses import dataclass

from gi.repository import Gio, GLib

from musik_bingo.domain.links import (
    is_spotify,
    is_youtube,
    spotify_search_uri,
    spotify_web_search_url,
    youtube_search_url,
)
from musik_bingo.domain.models import Song


@dataclass(frozen=True)
class LaunchPlan:
    method: str  # "mpris" (Spotify spielt direkt), "uri" (an System übergeben)
    uri: str
    exact: bool  # True: genau dieser Titel; False: Suche
    description: str


def plan_launch(song: Song, target: str, spotify_mpris: bool, spotify_scheme: bool) -> LaunchPlan:
    if target == "spotify":
        if is_spotify(song.link):
            if spotify_mpris:
                return LaunchPlan("mpris", song.link, True, "Spotify spielt den Titel ab")
            if spotify_scheme:
                return LaunchPlan("uri", song.link, True, "Titel in Spotify geöffnet")
            return LaunchPlan("uri", "https://open.spotify.com/track/" + song.link.rsplit(":", 1)[-1], True,
                              "Titel im Spotify-Webplayer geöffnet")
        if spotify_scheme:
            return LaunchPlan("uri", spotify_search_uri(song.title, song.artist), False,
                              "Spotify-Suche geöffnet – bitte den Titel anklicken")
        return LaunchPlan("uri", spotify_web_search_url(song.title, song.artist), False,
                          "Spotify-Websuche geöffnet – bitte den Titel anklicken")
    if target == "youtube":
        if is_youtube(song.link):
            return LaunchPlan("uri", song.link, True, "Video im Browser geöffnet")
        return LaunchPlan("uri", youtube_search_url(song.title, song.artist), False,
                          "YouTube-Suche im Browser geöffnet – bitte das Video anklicken")
    raise ValueError("Für dieses Wiedergabeziel gibt es keinen externen Start.")


def has_scheme_handler(scheme: str) -> bool:
    try:
        return Gio.AppInfo.get_default_for_uri_scheme(scheme) is not None
    except (GLib.Error, TypeError):
        return False


def open_uri(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error as error:
        raise RuntimeError(f"Adresse konnte nicht geöffnet werden: {error.message}") from error
