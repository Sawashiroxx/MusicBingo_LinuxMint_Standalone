"""Prozess, der den Spotify-Busnamen besitzt, aber nie antwortet (wie ein hängendes Spotify).

Aufruf: python3 hung_player_process.py – meldet „ready“, sobald der Name belegt ist.
Der Test friert den Prozess danach mit SIGSTOP ein: Nachrichten an ihn bleiben unbeantwortet.
"""
import os
import time

from gi.repository import Gio, GLib

BUS_NAME = "org.mpris.MediaPlayer2.spotify"


def main() -> None:
    connection = Gio.DBusConnection.new_for_address_sync(
        os.environ["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
                         GLib.Variant("(su)", (BUS_NAME, 4)), None, Gio.DBusCallFlags.NONE, -1, None)
    print("ready", flush=True)
    time.sleep(600)  # kein Hauptloop: Aufrufe werden nie beantwortet


if __name__ == "__main__":
    main()
