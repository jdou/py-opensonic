"""
This file is part of py-opensonic.

py-opensonic is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

py-opensonic is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with py-opensonic.  If not, see <http://www.gnu.org/licenses/>
"""

from hashlib import md5
from netrc import netrc
import os

import requests
from requests import Response

from .. import errors
from ..media.media_types import (Album, AlbumID3, AlbumInfo, ArtistID3, ArtistInfo, ArtistInfo2,
                                Artists, Bookmark, ChatMessage, Child, Directory, Error, Genre,
                                Indexes, InternetRadioStation, JukeboxPlaylist, JukeboxStatus,
                                Lyrics, MusicFolder, NowPlayingEntry, OpenSubsonicExtension,
                                Playlist, PlayQueue, PodcastChannel, PodcastEpisode, ScanStatus,
                                SearchResult2, SearchResult3, Share, Starred, Starred2,
                                StructuredLyrics, User)


API_VERSION = '1.16.1'


class Connection:
    """The only class used to make calls to an OpenSubsonic server.

    All return types are defined in media.media_types.py.
    """
    def __init__(self, base_url:str, username:str|None=None, password:str|None=None, port:int=4040,
                 api_key:str|None=None, server_path:str='', app_name:str='py-opensonic', api_version:str=API_VERSION,
                 use_netrc:str|None=None, legacy_auth:bool=False,
                 use_get:bool=False, use_views:bool=True):
        """Create a connection to an OpenSubsonic server.

        Args:
            base_url: The base URL for your server. Use "https" for SSL
                connections. Do not append the port here; use the port
                argument instead. If subsonic lives under a sub-path, use
                server_path, not this argument. Example:
                ``http://subsonic.example.com``
            username: The username for the connection. May be None when using
                API key authentication or when use_netrc provides credentials.
            password: The password for the connection. May be None when using
                API key authentication or when use_netrc provides credentials.
            port: The port number to connect on. Default is 4040.
            api_key: API key for authentication as defined by the Open Subsonic
                API key extension.
            server_path: The base resource path for the subsonic views. Useful
                when subsonic is behind a proxy at a non-default path. The
                full URL becomes
                ``http://example.com:4040/<server_path>/rest/<method>``.
            app_name: The name of your application.
            api_version: The API version to use. Subsonic will error if you
                send a version higher than the server supports. Useful when
                connecting to older Subsonic versions.
            use_netrc: Path to a netrc-formatted file, or True to use the
                default netrc file ($HOME/.netrc).
            legacy_auth: Use pre-1.13.0 API version authentication.
            use_get: Use GET requests instead of the default POST. Not
                recommended as URLs can get very long with some API calls.
            use_views: When True (default), append .view to endpoint names
                as the original Subsonic API requires. Disable to use bare
                method names, e.g. ping instead of ping.view.
        """
        self.base_url = base_url
        self._username = username
        self._raw_pass = password
        self._api_key = api_key
        self._legacy_auth = legacy_auth
        self._use_get = use_get
        self._use_views = use_views
        self._api_version = api_version
        self._sess: requests.Session | None  = None
        self._timeout = (30, 60)

        self._netrc = None
        if use_netrc is not None:
            self._process_netrc(use_netrc)
        elif (username is None or password is None) and api_key is None:
            raise errors.CredentialError('You must specify either a username/password '
                'combination, api key with the api_key parameter or "use_netrc" must be either True or a string '
                'representing a path to a netrc file')
        elif username is not None and password is not None and api_key is not None:
            raise errors.CredentialError('You must specify either username and password or api key')

        self.port = port
        self.app_name = app_name
        self.server_path = server_path


    # Properties
    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, url: str) -> None:
        self._base_url = url
        if '://' in url:
            self._hostname = url.split('://')[1].strip()
        else:
            self._hostname = url

    @property
    def port(self) -> int:
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        self._port = port

    @property
    def username(self) -> str | None:
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        self._username = username

    @property
    def password(self) -> str | None:
        return self._raw_pass

    @password.setter
    def password(self, password: str) -> None:
        self._raw_pass = password

    @property
    def api_version(self) -> str:
        return self._api_version

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @api_key.setter
    def api_key(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def app_name(self) -> str:
        return self._app_name

    @app_name.setter
    def app_name(self, app_name: str) -> None:
        self._app_name = app_name

    @property
    def server_path(self) -> str:
        return self._server_path

    @server_path.setter
    def server_path(self, path: str) -> None:
        sep = ''
        if path != '' and not path.endswith('/'):
            sep = '/'
        self._server_path = f"{path}{sep}rest".strip('/')

    @property
    def legacy_auth(self) -> bool:
        return self._legacy_auth

    @legacy_auth.setter
    def legacy_auth(self, lauth: bool) -> None:
        self._legacy_auth = lauth

    @property
    def use_get(self) -> bool:
        return self._use_get

    @use_get.setter
    def use_get(self, g: bool) -> None:
        self._use_get = g


    def cleanup(self) -> None:
        """ Cleanup the connection by closing the underlying session. """
        if self._sess is not None:
            self._sess.close()
            self._sess = None


    # API methods
    def add_chat_message(self, message:str) -> bool:
        """Add a message to the chat log.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/addchatmessage/

        Args:
            message: The message to add.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'addChatMessage'

        q = {'message': message}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def change_password(self, username:str, password:str) -> bool:
        """Change the password of an existing Subsonic user.

        The user performing this action must have admin privileges.

        Since: 1.1.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/changepassword/

        Args:
            username: The username whose password is being changed.
            password: The new password of the user.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'changePassword'

        # There seems to be an issue with some subsonic implementations
        # not recognizing the "enc:" precursor to the encoded password and
        # encodes the whole "enc:<hex>" as the password.  Weird.
        #q = {'username': username, 'password': hexPass.lower()}
        q = {'username': username, 'password': password}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def create_bookmark(self, mid:str, position:int, comment:str|None=None) -> bool:
        """Create or update a bookmark within a media file.

        Bookmarks are personal and not visible to other users.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createbookmark/

        Args:
            mid: The ID of the media file to bookmark. If a bookmark already
                exists for this file it will be overwritten.
            position: The position in milliseconds within the media file.
            comment: A user-defined comment.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createBookmark'

        q = self._get_query_dict({'id': mid, 'position': position,
            'comment': comment})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def create_internet_radio_station(self, stream_url:str, name:str,
                                      homepage_url:str|None=None) -> bool:
        """Create an internet radio station.

        Since: 1.16.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createinternetradiostation/

        Args:
            stream_url: The stream URL for the station.
            name: The user-defined name for the station.
            homepage_url: The homepage URL for the station.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createInternetRadioStation'

        q = self._get_query_dict({
            'streamUrl':stream_url, 'name': name, 'homepageUrl': homepage_url})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def create_playlist(self, playlist_id:str|None=None, name:str|None=None,
                       song_ids:list[str]|None=None) -> bool:
        """Create or update a playlist.

        If updating, playlist_id is required. If creating, name is required.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createplaylist/

        Args:
            playlist_id: The ID of the playlist to update.
            name: The name of the playlist to create.
            song_ids: The list of song IDs to populate the playlist. In update
                mode this list replaces the existing one.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createPlaylist'

        if song_ids is None:
            song_ids = []

        if playlist_id == name == None:
            raise errors.ArgumentError('You must supply either a playlistId or a name')
        if playlist_id is not None and name is not None:
            raise errors.ArgumentError('You can only supply either a playlistId '
                 'OR a name, not both')

        q = self._get_query_dict({'playlistId': playlist_id, 'name': name})

        res = self._do_request_with_list(method, 'songId', song_ids, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def create_podcast_channel(self, url:str) -> bool:
        """Add a new Podcast channel.

        The user must be authorized for Podcast administration.

        Since: 0.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createpodcastchannel/

        Args:
            url: The URL of the Podcast to add.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createPodcastChannel'

        q = {'url': url}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def create_share(self, shids:list[str]|None=None, description:str|None=None,
                     expires:float|None=None) -> Share:
        """Create a public URL for streaming music or video from the server.

        The URL is short and suitable for posting on social media. The user
        must be authorized to share (see Settings > Users > User is allowed to
        share files with anyone).

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createshare/

        Args:
            shids: A list of IDs of songs, albums or videos to share.
            description: A description displayed to people visiting the shared
                media.
            expires: A unix timestamp at which this share should expire.

        Returns:
            A media.Share object for the newly created share.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createShare'

        if shids is None:
            shids = []

        q = self._get_query_dict({'description': description,
            'expires': self._ts2milli(int(expires or 0))})
        res = self._do_request_with_list(method, 'id', shids, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Share.from_dict(dres['shares']['share'][0])


    def create_user(self, username:str, password:str, email:str,
            ldap_authed:bool=False, admin_role:bool=False,
            settings_role:bool=True, stream_role:bool=True, jukebox_role:bool=False,
            download_role:bool=False, upload_role:bool=False,
            playlist_role:bool=False, cover_art_role:bool=False,
            comment_role:bool=False, podcast_role:bool=False, share_role:bool=False,
            video_conversion_role:bool=False, music_folder_id:int|None=None) -> bool:
        """Create a new Subsonic user.

        Since: 1.1.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/createuser/

        Args:
            username: The username of the new user.
            password: The password for the new user.
            email: The email address of the new user.
            ldap_authed: Whether the user is authenticated via LDAP.
            admin_role: Grant admin role.
            settings_role: Grant settings role.
            stream_role: Grant stream role.
            jukebox_role: Grant jukebox role.
            download_role: Grant download role.
            upload_role: Grant upload role.
            playlist_role: Grant playlist role.
            cover_art_role: Grant cover art role.
            comment_role: Grant comment role.
            podcast_role: Grant podcast role.
            share_role: Grant share role.
            video_conversion_role: Grant video conversion role.
            music_folder_id: Restrict the user to this music folder only.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'createUser'
        hex_pass = f'enc:{self._hex_enc(password)}'

        q = self._get_query_dict({
            'username': username, 'password': hex_pass, 'email': email,
            'ldapAuthenticated': ldap_authed, 'adminRole': admin_role,
            'settingsRole': settings_role, 'streamRole':stream_role,
            'jukeboxRole': jukebox_role, 'downloadRole': download_role,
            'uploadRole': upload_role, 'playlistRole': playlist_role,
            'coverArtRole': cover_art_role, 'commentRole': comment_role,
            'podcastRole': podcast_role, 'shareRole': share_role,
            'videoConversionRole': video_conversion_role,
            'musicFolderId': music_folder_id
        })

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_bookmark(self, mid:str) -> bool:
        """Delete the bookmark for a given media file.

        Other users' bookmarks are not affected.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deletebookmark/

        Args:
            mid: The ID of the media file to delete the bookmark from.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deleteBookmark'

        q = {'id': mid}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_internet_radio_station(self, iid:str) -> bool:
        """Delete an internet radio station.

        Since: 1.16.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deleteinternetradiostation/

        Args:
            iid: The ID of the station to delete.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deleteInternetRadioStation'

        q = {'id': iid}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_podcast_channel(self, pid:str) -> bool:
        """Delete a Podcast channel.

        The user must be authorized for Podcast administration.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deletepodcastchannel/

        Args:
            pid: The ID of the Podcast channel to delete.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deletePodcastChannel'

        q = {'id': pid}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_podcast_episode(self, pid:str) -> bool:
        """Delete a Podcast episode.

        The user must be authorized for Podcast administration.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deletepodcastepisode/

        Args:
            pid: The ID of the Podcast episode to delete.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deletePodcastEpisode'

        q = {'id': pid}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_user(self, username:str) -> bool:
        """Delete an existing Subsonic user.

        Requires admin rights.

        Since: 1.3.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deleteuser/

        Args:
            username: The username of the user to delete.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deleteUser'

        q = {'username': username}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_playlist(self, pid:str) -> bool:
        """Delete a saved playlist.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deleteplaylist/

        Args:
            pid: ID of the playlist to delete, as obtained by get_playlists().

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deletePlaylist'

        res = self._do_request(method, {'id': pid})
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def download(self, sid:str) -> Response:
        """Download a given music file.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/download/

        Args:
            sid: The ID of the music file to download.

        Returns:
            The response object for reading the file content.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'download'

        res = self._do_request(method, {'id': sid})
        dres = self._handle_bin_res(res)
        if isinstance(dres, dict):
            self._check_status(dres)
        return dres


    def download_podcast_episode(self, pid:str) -> bool:
        """Tell the server to start downloading a given Podcast episode.

        The user must be authorized for Podcast administration.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/downloadpodcastepisode/

        Args:
            pid: The ID of the Podcast episode to download.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'downloadPodcastEpisode'

        q = {'id': pid}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def delete_share(self, shid:str) -> bool:
        """Delete an existing share.

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/deleteshare/

        Args:
            shid: The ID of the share to delete.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'deleteShare'

        q = self._get_query_dict({'id': shid})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def get_album(self, album_id:str) -> AlbumID3:
        """Return the info and songs for an album using ID3 tags.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getalbum/

        Args:
            album_id: The album ID.

        Returns:
            A media.AlbumID3 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAlbum'

        q = self._get_query_dict({'id': album_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return AlbumID3.from_dict(dres['album'])


    def get_album_info(self, aid:str) -> AlbumInfo:
        """Return album notes, image URLs, and other info from last.fm.

        Since: 1.14.0

        Args:
            aid: The album ID.

        Returns:
            A media.AlbumInfo object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAlbumInfo'

        q = {'id': aid}
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return AlbumInfo.from_dict(dres['albumInfo'])


    def get_album_info2(self, aid:str) -> AlbumInfo:
        """Return album info using ID3 tags instead of file structure.

        Same as get_album_info but organizes by ID3 tags.

        Since: 1.14.0

        Args:
            aid: The album ID.

        Returns:
            A media.AlbumInfo object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAlbumInfo2'

        q = {'id': aid}
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return AlbumInfo.from_dict(dres['albumInfo'])


    def get_album_list(self, ltype:str, size:int=10, offset:int=0, from_year:int|None=None,
            to_year:int|None=None, genre:str|None=None,
            music_folder_id:str|None=None) -> list[Album]:
        """Return a list of albums filtered by the given type.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getalbumlist/

        Args:
            ltype: The list type. One of: random, newest, highest, frequent,
                recent, starred, alphabeticalByName, alphabeticalByArtist
                (last two since 1.8.0), byYear, byGenre (since 1.10.1).
            size: The number of albums to return. Max 500.
            offset: The list offset for paging. Max 5000.
            from_year: Required when ltype is "byYear". Start of year range.
            to_year: Required when ltype is "byYear". End of year range.
            genre: Required when ltype is "byGenre". The genre name, e.g. "Rock".
            music_folder_id: Only return albums in this music folder.
                See get_music_folders().

        Returns:
            A list of media.Album objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAlbumList'

        q = self._get_query_dict({'type': ltype, 'size': size,
            'offset': offset, 'fromYear': from_year, 'toYear': to_year,
            'genre': genre, 'musicFolderId': music_folder_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'album' not in dres['albumList'] or not dres['albumList']['album']:
            return []
        return [Album.from_dict(entry) for entry in dres['albumList']['album']]


    def get_album_list2(self, ltype:str, size:int=10, offset:int=0,
                      from_year:int|None=None, to_year:int|None=None,
                      genre:str|None=None) -> list[AlbumID3]:
        """Return a list of albums filtered by type, organized using ID3 tags.

        Similar to get_album_list but uses ID3 tags for organization.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getalbumlist2/

        Args:
            ltype: The list type. One of: random, newest, highest, frequent,
                recent, starred, alphabeticalByName, alphabeticalByArtist,
                byYear, byGenre (since 1.10.1).
            size: The number of albums to return. Max 500.
            offset: The list offset for paging. Max 5000.
            from_year: Required when ltype is "byYear". Start of year range.
            to_year: Required when ltype is "byYear". End of year range.
            genre: Required when ltype is "byGenre". The genre name, e.g. "Rock".

        Returns:
            A list of media.AlbumID3 objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAlbumList2'

        q = self._get_query_dict({'type': ltype, 'size': size,
            'offset': offset, 'fromYear': from_year, 'toYear': to_year,
            'genre': genre})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'album' not in dres['albumList2'] or not dres['albumList2']['album']:
            return []
        return [AlbumID3.from_dict(entry) for entry in dres['albumList2']['album']]


    def get_artist(self, artist_id:str) -> ArtistID3:
        """Return the info and albums for an artist using ID3 tags.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getartist/

        Args:
            artist_id: The artist ID.

        Returns:
            A media.ArtistID3 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getArtist'

        q = self._get_query_dict({'id': artist_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return ArtistID3.from_dict(dres['artist'])


    def get_artists(self) -> Artists:
        """Return all artists, organized using ID3 tags.

        Similar to get_indexes() but uses ID3 tags to determine the artist.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getartists/

        Returns:
            A media.Artists object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getArtists'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)

        return Artists.from_dict(dres['artists'])


    def get_artist_info(self, aid:str, count:int=20,
                        include_not_present:bool=False) -> ArtistInfo:
        """Return biography, image URLs, and similar artists for an artist.

        Since: 1.11.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getartistinfo/

        Args:
            aid: The ID of the artist, album or song.
            count: The max number of similar artists to return.
            include_not_present: Whether to return artists not present in the
                media library.

        Returns:
            A media.ArtistInfo object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getArtistInfo'

        q = {'id': aid, 'count': count,
            'includeNotPresent': include_not_present}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return ArtistInfo.from_dict(dres['artistInfo'])


    def get_artist_info2(self, aid:str, count:int=20,
                         include_not_present:bool=False) -> ArtistInfo2:
        """Return artist info organized using ID3 tags.

        Similar to get_artist_info() but organizes music according to ID3 tags.

        Since: 1.11.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getartistinfo2/

        Args:
            aid: The ID of the artist, album or song.
            count: The max number of similar artists to return.
            include_not_present: Whether to return artists not present in the
                media library.

        Returns:
            A media.ArtistInfo2 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getArtistInfo2'

        q = {'id': aid, 'count': count,
            'includeNotPresent': include_not_present}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return ArtistInfo2.from_dict(dres['artistInfo2'])


    def get_avatar(self, username:str) -> Response:
        """Return the avatar image for a user.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getavatar/

        Args:
            username: The user to retrieve the avatar for.

        Returns:
            The aiohttp.ClientResponse object for reading the avatar image.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getAvatar'

        q = {'username': username}

        res = self._do_request(method, q)
        dres = self._handle_bin_res(res)
        if isinstance(dres, dict):
            self._check_status(dres)
        return dres


    def get_bookmarks(self) -> list[Bookmark]:
        """Return all bookmarks for the current user.

        A bookmark is a saved position within a media file.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getbookmarks/

        Returns:
            A list of media.Bookmark objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getBookmarks'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'bookmark' not in dres['bookmarks'] or not dres['bookmarks']['bookmark']:
            return []
        return [Bookmark.from_dict(b) for b in dres['bookmarks']['bookmark']]


    def get_captions(self, vid, fmt=None):
        """Return captions (subtitles) for a video.

        Use get_video_info() to get a list of available captions.

        Since: 1.14.0

        Args:
            vid: The ID of the video.
            fmt: Preferred captions format ("srt" or "vtt").

        Returns:
            The captions response dict.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getCaptions'

        q = self._get_query_dict({'id':int(vid), 'format': fmt})
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return dres


    def get_chat_messages(self, since:int=1) -> list[ChatMessage]:
        """Return current visible (non-expired) chat messages.

        Note: All times returned are in milliseconds since the Unix epoch.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getchatmessages/

        Args:
            since: Only return messages newer than this unix timestamp.

        Returns:
            A list of media.ChatMessage objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getChatMessages'

        q = {'since': self._ts2milli(since)}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'chatMessage' not in dres['chatMessages'] or not dres['chatMessages']['chatMessage']:
            return []
        return [ChatMessage.from_dict(m) for m in dres['chatMessages']['chatMessage']]


    def get_cover_art(self, aid:str, size:int|None=None) -> Response:
        """Return a cover art image.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getcoverart/

        Args:
            aid: ID string for the cover art image to download.
            size: If specified, scale the image to this size.

        Returns:
            The response object for reading the image content.

        Raises:
            errors.SonicError: On failure.
        """
        q = self._get_query_dict({'id': aid, 'size': size})

        res = self._do_request('getCoverArt', q, is_stream=True)
        dres = self._handle_bin_res(res)
        if isinstance(dres, dict):
            self._check_status(dres)
        return dres


    def get_genres(self) -> list[Genre]:
        """Return all genres.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getgenres/

        Returns:
            A list of media.Genre objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getGenres'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'genre' not in dres['genres'] or not dres['genres']['genre']:
            return []
        return [Genre.from_dict(g) for g in dres['genres']['genre']]


    def get_indexes(self, music_folder_id:int|None=None, if_modified_since:int|None=None) -> Indexes:
        """Return an indexed structure of all artists.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getindexes/

        Args:
            music_folder_id: If specified, only return artists for this folder.
                See get_music_folders().
            if_modified_since: If specified, only return a result if the artist
                collection has changed since this unix timestamp.

        Returns:
            A media.Indexes object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getIndexes'

        q = self._get_query_dict({'musicFolderId': music_folder_id,
            'ifModifiedSince': self._ts2milli(if_modified_since) if if_modified_since else 0})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Indexes.from_dict(dres['indexes'])


    def get_internet_radio_stations(self) -> list[InternetRadioStation]:
        """Return all internet radio stations.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getinternetradiostations/

        Returns:
            A list of media.InternetRadioStation objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getInternetRadioStations'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'internetRadioStation' not in dres['internetRadioStations']:
            return []
        if not dres['internetRadioStations']['internetRadioStation']:
            return []
        return [InternetRadioStation.from_dict(i)
                for i in dres['internetRadioStations']['internetRadioStation']]


    def get_license(self) -> dict:
        """Return details about the software license.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getlicense/

        Returns:
            A dict containing license details including date, email, key and
            validity status.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getLicense'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return dres


    def get_lyrics(self, artist:str|None=None, title:str|None=None) -> Lyrics:
        """Search for and return lyrics for a given song.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getlyrics/

        Args:
            artist: The artist name.
            title: The song title.

        Returns:
            A media.Lyrics object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getLyrics'

        q = self._get_query_dict({'artist': artist, 'title': title})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Lyrics.from_dict(dres['lyrics'])


    def get_lyrics_by_song_id(self, song_id:str) -> list[StructuredLyrics]:
        """Retrieve all structured lyrics for a given song.

        Lyrics may come from embedded tags (SYLT/USLT), LRC file, or any
        other external source.

        Since: Open Subsonic ver 1
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getlyricsbysongid/

        Args:
            song_id: The ID of the requested song.

        Returns:
            A list of media.StructuredLyrics objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getLyricsBySongId'

        q = self._get_query_dict({'id': song_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'structuredLyrics' not in dres['lyricsList'] or not dres['lyricsList']['structuredLyrics']:
            return []
        return [StructuredLyrics.from_dict(l) for l in dres['lyricsList']['structuredLyrics']]


    def get_music_directory(self, mid:str) -> Directory:
        """Return a listing of all files in a music directory.

        Typically used to get albums for an artist or songs for an album.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getindexes/

        Args:
            mid: The string ID that uniquely identifies the folder. Obtained
                via get_indexes() or get_music_directory().

        Returns:
            A media.Directory object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getMusicDirectory'

        res = self._do_request(method, {'id': mid})
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Directory.from_dict(dres['directory'])


    def get_music_folders(self) -> list[MusicFolder]:
        """Return all configured music folders.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getmusicfolders/

        Returns:
            A list of media.MusicFolder objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getMusicFolders'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if "musicFolders" not in dres or not dres["musicFolders"]:
            return []
        return [MusicFolder.from_dict(f) for f in dres["musicFolders"]]


    def get_newest_podcasts(self, count:int=20) -> list[PodcastEpisode]:
        """Return the most recently published Podcast episodes.

        Since: 1.13.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getnewestpodcasts/

        Args:
            count: The number of episodes to return.

        Returns:
            A list of media.PodcastEpisode objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getNewestPodcasts'

        q = {'count': count}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'newestPodcasts' not in dres or 'episode' not in dres['newestPodcasts']:
            return []
        return [PodcastEpisode.from_dict(entry) for entry in dres['newestPodcasts']['episode']]


    def get_now_playing(self) -> list[NowPlayingEntry]:
        """Return what is currently being played by all users.

        Since: 1.0.0

        Returns:
            A list of media.NowPlayingEntry objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getNowPlaying'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'entry' not in dres['nowPlaying'] or not dres['nowPlaying']['entry']:
            return []
        return [NowPlayingEntry.from_dict(n) for n in dres['nowPlaying']['entry']]


    def get_open_subsonic_extensions(self) -> list[OpenSubsonicExtension]:
        """List the OpenSubsonic extensions supported by this server.

        Since: OpenSubsonic ver 1
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getopensubsonicextensions/

        Returns:
            A list of media.OpenSubsonicExtension objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getOpenSubsonicExtensions'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return [OpenSubsonicExtension.from_dict(o) for o in dres['openSubsonicExtensions']]


    def get_playlist(self, pid:str) -> Playlist:
        """Return a saved playlist with all its tracks.

        Since: 1.0.0

        Args:
            pid: The ID of the playlist as returned by get_playlists().

        Returns:
            A media.Playlist object with all tracks.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getPlaylist'

        res = self._do_request(method, {'id': pid})
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Playlist.from_dict(dres['playlist'])


    def get_playlists(self, username:str|None=None) -> list[Playlist]:
        """Return the ID and name of all saved playlists.

        The username option was added in 1.8.0. The returned Playlist objects
        contain only basic details, not the full track list. Use get_playlist()
        for the full object.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getplaylists/

        Args:
            username: If specified, return playlists for this user rather than
                the authenticated user. Requires admin role.

        Returns:
            A list of media.Playlist objects (without tracks).

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getPlaylists'

        q = self._get_query_dict({'username': username})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'playlist' not in dres['playlists'] or not dres['playlists']['playlist']:
            return []
        return [Playlist.from_dict(entry) for entry in dres['playlists']['playlist']]


    def get_play_queue(self) -> PlayQueue:
        """Return the saved play queue state for the current user.

        Includes the tracks in the play queue, the currently playing track,
        and the position within that track. Typically used to allow a user to
        move between clients while retaining the same play queue.

        Since: 1.12.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getplayqueue/

        Returns:
            A media.PlayQueue object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getPlayQueue'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return PlayQueue.from_dict(dres['playQueue'])


    def get_podcasts(self, inc_episodes:bool=True, pid:str|None=None) -> list[PodcastChannel]:
        """Return all podcast channels the server subscribes to.

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getpodcasts/

        Args:
            inc_episodes: Whether to include Podcast episodes in the result.
                Added in 1.9.0.
            pid: If specified, only return the Podcast channel with this ID.
                Added in 1.9.0.

        Returns:
            A list of media.PodcastChannel objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getPodcasts'

        q = self._get_query_dict({'includeEpisodes': inc_episodes,
            'id': pid})
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'channel' not in dres['podcasts'] or not dres['podcasts']['channel']:
            return []
        return [PodcastChannel.from_dict(entry) for entry in dres['podcasts']['channel']]


    def get_random_songs(self, size:int=10, genre:str|None=None, from_year:int|None=None,
            to_year:int|None=None, music_folder_id:str|None=None) -> list[Child]:
        """Return random songs matching the given criteria.

        Since: 1.2.0

        Args:
            size: The max number of songs to return. Max 500.
            genre: Only return songs from this genre.
            from_year: Only return songs from this year or later.
            to_year: Only return songs from this year or earlier.
            music_folder_id: Only return songs in this music folder.
                See get_music_folders().

        Returns:
            A list of media.Child objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getRandomSongs'

        q = self._get_query_dict({'size': size, 'genre': genre,
            'fromYear': from_year, 'toYear': to_year,
            'musicFolderId': music_folder_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'song' not in dres['randomSongs'] or not dres['randomSongs']['song']:
            return []
        return [Child.from_dict(entry) for entry in dres['randomSongs']['song']]


    def get_scan_status(self) -> ScanStatus:
        """Return the current status of media library scanning.

        The 'scanning' field changes to False when a scan is complete.
        The 'count' field is the total number of items to be scanned.

        Since: 1.15.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getscanstatus/

        Returns:
            A media.ScanStatus object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getScanStatus'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return ScanStatus.from_dict(dres['scanStatus'])


    def get_shares(self) -> list[Share]:
        """Return information about shared media this user is allowed to manage.

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getshares/

        Returns:
            A list of media.Share objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getShares'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'share' not in dres['shares'] or not dres['shares']['share']:
            return []
        return [Share.from_dict(s) for s in dres['shares']['share']]


    def get_similar_songs(self, iid:str, count:int=50) -> list[Child]:
        """Return a random collection of songs from the given artist and similar artists.

        Uses data from last.fm. Typically used for artist radio features.

        Since: 1.11.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getsimilarsongs/

        Args:
            iid: The artist, album, or song ID.
            count: Max number of songs to return.

        Returns:
            A list of media.Child objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getSimilarSongs'

        q = {'id': iid, 'count': count}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'song' not in dres['similarSongs'] or not dres['similarSongs']['song']:
            return []
        return [Child.from_dict(entry) for entry in dres['similarSongs']['song']]


    def get_similar_songs2(self, iid:str, count:int=50) -> list[Child]:
        """Return similar songs organized using ID3 tags.

        Similar to get_similar_songs() but organizes music according to ID3 tags.

        Since: 1.11.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getsimilarsongs2/

        Args:
            iid: The artist, album, or song ID.
            count: Max number of songs to return.

        Returns:
            A list of media.Child objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getSimilarSongs2'

        q = {'id': iid, 'count': count}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'song' not in dres['similarSongs2'] or not dres['similarSongs2']['song']:
            return []
        return [Child.from_dict(entry) for entry in dres['similarSongs2']['song']]


    def get_song(self, sid:str) -> Child:
        """Return the info for a song, organized using ID3 tags.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getsong/

        Args:
            sid: The song ID.

        Returns:
            A media.Child object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getSong'

        q = self._get_query_dict({'id': sid})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Child.from_dict(dres['song'])


    def get_songs_by_genre(self, genre:str, count:int=10, offset:int=0,
                           music_folder_id:str|None=None) -> list[Child]:
        """Return songs in a given genre.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getsongsbygenre/

        Args:
            genre: The genre, as returned by get_genres().
            count: The maximum number of songs to return. Max 500, default 10.
            offset: The offset for paging. Default 0.
            music_folder_id: Only return results from this music folder.
                See get_music_folders().

        Returns:
            A list of media.Child objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getSongsByGenre'

        q = self._get_query_dict({'genre': genre,
            'count': count,
            'offset': offset,
            'musicFolderId': music_folder_id,
        })

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'song' not in dres['songsByGenre'] or not dres['songsByGenre']['song']:
            return []
        return [Child.from_dict(entry) for entry in dres['songsByGenre']['song']]


    def get_starred(self, music_folder_id:str|None=None) -> Starred:
        """Return starred songs, albums and artists.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getstarred/

        Args:
            music_folder_id: Only return results from this music folder.
                See get_music_folders().

        Returns:
            A media.Starred object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getStarred'

        q = {}
        if music_folder_id:
            q['musicFolderId'] = music_folder_id

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Starred.from_dict(dres['starred'])


    def get_starred2(self, music_folder_id:str|None=None) -> Starred2:
        """Return starred songs, albums and artists organized using ID3 tags.

        Similar to get_starred() but uses ID3 tags for organization.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getstarred2/

        Args:
            music_folder_id: Only return results from this music folder.
                See get_music_folders().

        Returns:
            A media.Starred2 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getStarred2'

        q = {}
        if music_folder_id:
            q['musicFolderId'] = music_folder_id

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return Starred2.from_dict(dres['starred2'])


    def get_top_songs(self, artist:str, count:int=50) -> list[Child]:
        """Return the top songs for a given artist.

        Since: 1.13.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/gettopsongs/

        Args:
            artist: The artist name to get songs for.
            count: The number of songs to return.

        Returns:
            A list of media.Child objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getTopSongs'

        q = {'artist': artist, 'count': count}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        if 'song' not in dres['topSongs'] or not dres['topSongs']['song']:
            return []
        return [Child.from_dict(entry) for entry in dres['topSongs']['song']]


    def get_user(self, username:str) -> User:
        """Return details about a given user, including their auth roles.

        Can be used to enable/disable client features such as jukebox control.
        You can only retrieve your own user unless you have admin privileges.

        Since: 1.3.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getuser/

        Args:
            username: The username to retrieve.

        Returns:
            A media.User object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getUser'

        q = {'username': username}

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return User.from_dict(dres['user'])


    def get_users(self) -> list[User]:
        """Return a list of all users.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/getusers/

        Returns:
            A list of media.User objects.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getUsers'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return [User.from_dict(u) for u in dres['users']['user']]


    def get_videos(self) -> dict:
        """Return all video files.

        Since: 1.8.0

        Returns:
            A dict containing video file information.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getVideos'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return dres


    def get_video_info(self, vid):
        """Return details for a video including audio tracks, subtitles, and conversions.

        Since: 0.14.0

        Args:
            vid: The video ID.

        Returns:
            A dict containing video details.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'getVideoInfo'

        q = {'id':int(vid)}
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return dres


    def hls (self, mid, bitrate=None):
        """Create an HTTP live streaming playlist for a media file.

        HLS is a streaming protocol implemented by Apple that works by
        breaking the stream into a sequence of small HTTP-based file downloads.
        Supports adaptive bitrate streaming via the bitrate parameter.

        Since: 0.8.0

        Args:
            mid: The ID of the media to stream.
            bitrate: If specified, the server will attempt to limit the bitrate
                to this value in kilobits per second. Pass multiple times for
                adaptive bitrate streaming. Since 0.9.0, you may request a
                specific resolution as ``bitrate=999@480x360``.

        Returns:
            The raw m3u8 playlist content as bytes.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'hls'

        q = self._get_query_dict({'id': mid, 'bitrate': bitrate})
        res = self._do_request(method, q)
        dres = self._handle_bin_res(res)
        if isinstance(dres, dict):
            self._check_status(dres)
        return dres.content


    def jukebox_control(self, action:str, index:int|None=None, sids:list[str]|None=None,
                       gain:float|None=None, offset:int|None=None) -> JukeboxStatus|JukeboxPlaylist:
        """Control the jukebox (playback directly on the server's audio hardware).

        The user must be authorized to control the jukebox. Some options were
        added in API version 1.7.0.

        Since: 1.2.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/jukeboxcontrol/

        Args:
            action: The operation to perform. One of: get, start, stop, skip,
                add, clear, remove, shuffle, setGain, status (1.7.0),
                set (1.7.0).
            index: Used by skip and remove. Zero-based index of the song.
            sids: Used by "add" and "set". List of song IDs to add. Must be
                a list even when adding a single song.
            gain: Used by setGain. A float between 0.0 and 1.0.
            offset: Used by "skip" (since 1.7.0). Start this many seconds
                into the track.

        Returns:
            A media.JukeboxPlaylist if action is "get", media.JukeboxStatus
            otherwise.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'jukeboxControl'

        if sids is None:
            sids = []

        q = self._get_query_dict({'action': action, 'index': index,
            'gain': gain, 'offset': offset})

        res = None
        if action == 'add':
            # We have to deal with the sids
            if not (isinstance(sids, list) or isinstance(sids, tuple)):
                raise errors.ArgumentError('If you are adding songs, "sids" must '
                    'be a list or tuple!')
            res = self._do_request_with_list(method, 'id', sids, q)
        else:
            res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)

        if action == 'get':
            return JukeboxPlaylist.from_dict(dres['jukeboxPlaylist'])

        return JukeboxStatus.from_dict(dres['jukeboxStatus'])


    def ping(self) -> bool:
        """Check whether the server is alive.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/ping/

        Returns:
            True if the server is alive.

        Raises:
            errors.SonicError: If the server returns an error.
        """
        method = 'ping'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        if dres['status'] == 'ok':
            return True
        elif dres['status'] == 'failed':
            err = Error.from_dict(dres['error'])
            exc = errors.getExcByCode(err.code)
            raise exc(err.message)
        return False


    def refresh_podcasts(self) -> bool:
        """Tell the server to check for new Podcast episodes.

        The user must be authorized for Podcast administration.

        Since: 1.9.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/refreshpodcasts/

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'refreshPodcasts'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def save_play_queue(self, qids, current=None, position=None) -> bool:
        """Save the state of the play queue for the current user.

        Saves the tracks in the play queue, the currently playing track, and
        the position within that track. Typically used to allow a user to move
        between clients while retaining the same play queue.

        Since: 0.12.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/saveplayqueue/

        Args:
            qids: The list of song IDs in the play queue.
            current: The ID of the currently playing song.
            position: The position in milliseconds within the current song.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'savePlayQueue'

        if not isinstance(qids, (tuple, list)):
            qids = [qids]

        q = self._get_query_dict({'current': current, 'position': position})

        res = self._do_request_with_lists(method, {'id': qids}, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def scrobble(self, sid:str, submission:bool=True, listen_time:int|None=None) -> bool:
        """Scrobble a music file on last.fm.

        Requires that the user has configured last.fm. Since 1.11.0 this also
        updates the play count and last played timestamp for the song and album,
        and makes the song appear in the "Now playing" page.

        Since: 1.5.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/scrobble/

        Args:
            sid: The ID of the file to scrobble.
            submission: Whether this is a "submission" or a "now playing"
                notification.
            listen_time: The unix timestamp at which the song was listened to.
                Added in 1.8.0.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'scrobble'

        q = self._get_query_dict({'id': sid, 'submission': submission,
            'time': self._ts2milli(listen_time)})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def search(self, artist=None, album=None, title=None, dummy=None,
            count=20, offset=0, newer_than=None):
        """Search for media (deprecated since API 1.4.0, use search3() instead).

        Since: 1.0.0

        Raises:
            NotImplementedError: Always. Use search2() or search3() instead.
        """
        raise NotImplementedError("search is deprecated in favor of search2 or search3")


    def search2(self, query:str, artist_count:int=20, artist_offset:int=0,
                album_count:int=20, album_offset:int=0, song_count:int=20,
                song_offset:int=0, music_folder_id:int|None=None) -> SearchResult2:
        """Return albums, artists and songs matching a search query.

        Supports paging through the result.

        Since: 1.4.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/search2/

        Args:
            query: The search query.
            artist_count: Max number of artists to return. Default 20.
            artist_offset: Search offset for artists, for paging. Default 0.
            album_count: Max number of albums to return. Default 20.
            album_offset: Search offset for albums, for paging. Default 0.
            song_count: Max number of songs to return. Default 20.
            song_offset: Search offset for songs, for paging. Default 0.
            music_folder_id: Only return results from this music folder.
                See get_music_folders().

        Returns:
            A media.SearchResult2 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'search2'

        q = self._get_query_dict({'query': query, 'artistCount': artist_count,
            'artistOffset': artist_offset, 'albumCount': album_count,
            'albumOffset': album_offset, 'songCount': song_count,
            'songOffset': song_offset, 'musicFolderId': music_folder_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return SearchResult2.from_dict(dres['searchResult2'])


    def search3(self, query:str, artist_count:int=20, artist_offset:int=0,
                album_count:int=20, album_offset:int=0, song_count:int=20,
                song_offset:int=0, music_folder_id:int|None=None) -> SearchResult3:
        """Return search results organized using ID3 tags.

        Works the same as search2 but uses ID3 tags for organization.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/search3/

        Args:
            query: The search query.
            artist_count: Max number of artists to return. Default 20.
            artist_offset: Search offset for artists, for paging. Default 0.
            album_count: Max number of albums to return. Default 20.
            album_offset: Search offset for albums, for paging. Default 0.
            song_count: Max number of songs to return. Default 20.
            song_offset: Search offset for songs, for paging. Default 0.
            music_folder_id: Only return results from this music folder.
                See get_music_folders().

        Returns:
            A media.SearchResult3 object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'search3'

        q = self._get_query_dict({'query': query, 'artistCount': artist_count,
            'artistOffset': artist_offset, 'albumCount': album_count,
            'albumOffset': album_offset, 'songCount': song_count,
            'songOffset': song_offset, 'musicFolderId': music_folder_id})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return SearchResult3.from_dict(dres['searchResult3'])


    def set_rating(self, item_id:str, rating:int) -> bool:
        """Set the rating for a music file.

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/setrating/

        Args:
            item_id: The ID of the item (song/artist/album) to rate.
            rating: The rating between 1 and 5 inclusive, or 0 to remove the
                rating.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'setRating'

        try:
            rating = int(rating)
        except Exception as exc:
            raise errors.ArgumentError(
                f'Rating must be an integer between 0 and 5: {rating}') from exc
        if rating < 0 or rating > 5:
            raise errors.ArgumentError(
                f'Rating must be an integer between 0 and 5: {rating}')

        q = self._get_query_dict({'id': item_id, 'rating': rating})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def star(self, sids:list[str]|None=None, album_ids:list[str]|None=None,
             artist_ids:list[str]|None=None) -> bool:
        """Attach a star to songs, albums or artists.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/star/

        Args:
            sids: A list of song IDs to star.
            album_ids: A list of album IDs to star. Use instead of sids when
                accessing the media collection by ID3 tags.
            artist_ids: A list of artist IDs to star. Use instead of sids when
                accessing the media collection by ID3 tags.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'star'

        if sids is None:
            sids = []
        if album_ids is None:
            album_ids = []
        if artist_ids is None:
            artist_ids = []

        list_map = {'id': sids,
            'albumId': album_ids,
            'artistId': artist_ids}
        res = self._do_request_with_lists(method, list_map)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def start_scan(self) -> ScanStatus:
        """Initiate a rescan of the media libraries.

        The 'scanning' field changes to False when the scan is complete.
        The 'count' field starts at 0 and ends at the total items scanned.

        Since: 1.15.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/startscan/

        Returns:
            A media.ScanStatus object.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'startScan'

        res = self._do_request(method)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return ScanStatus.from_dict(dres['scanStatus'])


    def stream(self, sid:str, max_bit_rate:int=0, tformat:str|None=None,
               time_offset:int|None=None, size:str|None=None,
               estimate_length:bool=False, converted:bool=False, byte_range:str|None=None) -> Response:
        """Stream a given music file.

        Since: 1.0.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/stream/

        Args:
            sid: The ID of the music file to stream.
            max_bit_rate: Limit the bitrate to this value in kilobits per
                second. 0 means no limit. Legal values: 0, 32, 40, 48, 56,
                64, 80, 96, 112, 128, 160, 192, 224, 256, 320. Added in 1.2.0.
            tformat: Target format (e.g. "mp3" or "flv"). Use "raw" to disable
                transcoding (since 1.9.0). Added in 1.6.0.
            time_offset: Start the video stream at this offset in seconds.
                Video only. Added in 1.6.0.
            size: Requested video size as "WxH", e.g. "640x480". Added in 1.6.0.
            estimate_length: If True, set an estimated Content-Length header
                for transcoded media. Added in 1.8.0.
            converted: If True and a converted MP4 version exists, return the
                converted video instead of the original. Video only. Added in
                1.14.0.
            byte_range: Byte range to stream, passed as the HTTP Range header.

        Returns:
            The response object for reading the stream.

        Raises:
            errors.SonicError: On failure.
        """
        q = self._get_query_dict({'id': sid, 'maxBitRate': max_bit_rate,
            'format': tformat, 'timeOffset': time_offset, 'size': size,
            'estimateContentLength': estimate_length,
            'converted': converted})

        headers = None
        if byte_range:
            headers = {'Range': byte_range}

        res = self._do_request('stream', q, headers=headers)
        dres = self._handle_bin_res(res)
        if isinstance(dres, dict):
            self._check_status(dres)
        return dres


    def unstar(self, sids:list[str]|None=None, album_ids:list[str]|None=None,
               artist_ids:list[str]|None=None) -> bool:
        """Remove a star from songs, albums or artists.

        The reverse of star().

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/unstar/

        Args:
            sids: A list of song IDs to unstar.
            album_ids: A list of album IDs to unstar. Use instead of sids when
                accessing the media collection by ID3 tags.
            artist_ids: A list of artist IDs to unstar. Use instead of sids
                when accessing the media collection by ID3 tags.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'unstar'

        if sids is None:
            sids = []
        if album_ids is None:
            album_ids = []
        if artist_ids is None:
            artist_ids = []

        list_map = {'id': sids,
            'albumId': album_ids,
            'artistId': artist_ids}
        res = self._do_request_with_lists(method, list_map)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def update_internet_radio_station(self, iid:str, stream_url:str, name:str,
            homepage_url:str|None=None) -> bool:
        """Update an existing internet radio station.

        Since: 1.16.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/updateinternetradiostation/

        Args:
            iid: The ID of the station to update.
            stream_url: The new stream URL for the station.
            name: The new user-defined name for the station.
            homepage_url: The new homepage URL for the station.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'updateInternetRadioStation'

        q = self._get_query_dict({
            'id': iid, 'streamUrl':stream_url, 'name': name,
            'homepageUrl': homepage_url,
        })

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def update_playlist(self, lid:str, name:str|None=None, comment:str|None=None,
                       song_ids_to_add:list[str]|None=None,
                       song_indices_to_remove:list[int]|None=None) -> bool:
        """Update a playlist.

        Only the owner of a playlist is allowed to update it.

        Since: 1.8.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/updateplaylist/

        Args:
            lid: The playlist ID.
            name: The new human-readable name of the playlist.
            comment: The new playlist comment.
            song_ids_to_add: A list of song IDs to add to the playlist.
            song_indices_to_remove: Zero-based positions of songs to remove
                from the playlist (not song IDs).

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'updatePlaylist'

        if song_ids_to_add is None:
            song_ids_to_add = []

        if song_indices_to_remove is None:
            song_indices_to_remove = []

        q = self._get_query_dict({'playlistId': lid, 'name': name,
            'comment': comment})
        list_map = {'songIdToAdd': song_ids_to_add,
            'songIndexToRemove': song_indices_to_remove}
        res = self._do_request_with_lists(method, list_map, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def update_share(self, shid:str, description:str|None=None, expires:float|None=None) -> bool:
        """Update the description and/or expiration date for an existing share.

        Since: 1.6.0
        Docs: https://opensubsonic.netlify.app/docs/endpoints/updateshare/

        Args:
            shid: The ID of the share to update.
            description: The new description for the share.
            expires: The new unix timestamp for when this share expires.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'updateShare'

        q = self._get_query_dict({'id': shid, 'description': description,
            expires: self._ts2milli(int(expires or 0))})

        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    def update_user(self, username:str,  password:str|None=None, email:str|None=None,
            ldap_authed:bool=False, admin_role:bool=False,
            settings_role:bool=True, stream_role:bool=True, jukebox_role:bool=False,
            download_role:bool=False, upload_role:bool=False,
            playlist_role:bool=False, cover_art_role:bool=False,
            comment_role:bool=False, podcast_role:bool=False, share_role:bool=False,
            video_conv_role:bool=False, music_folder_id:int|None=None,
            max_bit_rate:int=0) -> bool:
        """Modify an existing Subsonic user.

        Since: 1.10.1
        Docs: https://opensubsonic.netlify.app/docs/endpoints/updateuser/

        Args:
            username: The username of the user to update.
            password: New password for the user.
            email: New email address for the user.
            ldap_authed: Whether the user is authenticated via LDAP.
            admin_role: Grant or revoke admin role.
            settings_role: Grant or revoke settings role.
            stream_role: Grant or revoke stream role.
            jukebox_role: Grant or revoke jukebox role.
            download_role: Grant or revoke download role.
            upload_role: Grant or revoke upload role.
            playlist_role: Grant or revoke playlist role.
            cover_art_role: Grant or revoke cover art role.
            comment_role: Grant or revoke comment role.
            podcast_role: Grant or revoke podcast role.
            share_role: Grant or revoke share role.
            video_conv_role: Grant or revoke video conversion role.
            music_folder_id: Restrict the user to this music folder only.
            max_bit_rate: The max bitrate for the user. 0 is unlimited.

        Returns:
            True on success.

        Raises:
            errors.SonicError: On failure.
        """
        method = 'updateUser'
        if password is not None:
            password = f'enc:{self._hex_enc(password)}'
        q = self._get_query_dict({'username': username, 'password': password,
            'email': email, 'ldapAuthenticated': ldap_authed,
            'adminRole': admin_role,
            'settingsRole': settings_role, 'streamRole':stream_role,
            'jukeboxRole': jukebox_role, 'downloadRole': download_role,
            'uploadRole': upload_role, 'playlistRole': playlist_role,
            'coverArtRole': cover_art_role, 'commentRole': comment_role,
            'podcastRole': podcast_role, 'shareRole': share_role,
            'videoConversionRole': video_conv_role,
            'musicFolderId': music_folder_id, 'maxBitRate': max_bit_rate
        })
        res = self._do_request(method, q)
        dres = self._handle_info_res(res)
        self._check_status(dres)
        return True


    #
    # Private internal methods
    #
    def _get_query_dict(self, d:dict) -> dict:
        """Remove all None-valued entries from the given dictionary."""
        for k, v in list(d.items()):
            if v is None:
                del d[k]
        return d


    def _get_base_qdict(self) -> dict:
        qdict = {
            'f': 'json',
            'v': self._api_version,
            'c': self._app_name,
        }

        if self._api_key:
            qdict['apiKey']  = self._api_key
        elif self._username and self._raw_pass:
            qdict['u'] = self._username
            if self._legacy_auth:
                qdict['p'] = f'enc:{self._hex_enc(self._raw_pass)}'
            else:
                salt = self._get_salt()
                token = md5((self._raw_pass + salt).encode('utf-8')).hexdigest()
                qdict.update({
                    's': salt,
                    't': token,
                })
        else:
            raise errors.CredentialError(
                "Must specify either 'api_key' or ('username' and 'password') but not both.")

        return qdict


    def _check_status(self, result:dict) -> bool:
        if result['status'] == 'failed':
            exc = errors.getExcByCode(result['error']['code'])
            raise exc(result['error']['message'])
        return True


    def _hex_enc(self, raw:str) -> str:
        """Return a hex-encoded string per the Subsonic API docs.

        Args:
            raw: The string to hex encode.

        Returns:
            The hex-encoded string.
        """
        ret = ''
        for c in raw:
            ret += f'{ord(c):02X}'
        return ret


    def _ts2milli(self, ts:int | None) -> int | None:
        """Convert a unix timestamp in seconds to milliseconds.

        Args:
            ts: Unix timestamp in seconds, or None.

        Returns:
            The timestamp multiplied by 1000, or None if ts is None.
        """
        if ts is None:
            return None
        return int(ts * 1000)


    def _fix_last_modified(self, data):
        """Recursively convert lastModified millisecond timestamps to seconds.

        Walks the data structure and converts any "lastModified" value from
        the Java-style millisecond epoch to a standard unix timestamp in
        seconds.
        """
        if isinstance(data, dict):
            for k, v in list(data.items()):
                if k == 'lastModified':
                    data[k] = int(v) / 1000.0
                    return data
                elif isinstance(v, (tuple, list, dict)):
                    return self._fix_last_modified(v)
        elif isinstance(data, (list, tuple)):
            for item in data:
                if isinstance(item, (list, tuple, dict)):
                    return self._fix_last_modified(item)


    def _process_netrc(self, use_netrc:str):
        """Load credentials from a netrc file.

        Args:
            use_netrc: True to use the default netrc file ($HOME/.netrc), or
                a string path to a specific netrc-formatted file.
        """
        if not use_netrc:
            raise errors.CredentialError('use_netrc must be either a boolean "True" '
                'or a string representing a path to a netrc file, '
                f'not {repr(use_netrc)}')
        if isinstance(use_netrc, bool) and use_netrc:
            self._netrc = netrc()
        else:
            # This should be a string specifying a path to a netrc file
            self._netrc = netrc(os.path.expanduser(use_netrc))
        auth = self._netrc.authenticators(self._hostname)
        if not auth:
            raise errors.CredentialError(f'No machine entry found for {self._hostname} in '
                'your netrc file')

        # If we get here, we have credentials
        self._username = auth[0]
        self._raw_pass = auth[2]


    def _get_salt(self, length=16):
        salt = md5(os.urandom(100)).hexdigest()
        return salt[:length]


    def _do_request(self, method: str, query: dict | None = None, headers: dict | None = None) -> Response:
        qdict = self._get_base_qdict()
        if query is not None:
            qdict.update(query)

        if self._use_views:
            method += '.view'
        url = f"{self._base_url}:{self._port}/{self._server_path}/{method}"

        # This dictionary is empty in Async (valid for aiohttp)
        # unasync will replace the line below and the **req_kwargs in the get and post methods
        # Yeah, it's stupid, but so is function coloring...
        

        if not self._sess:
            self._sess = requests.Session()

        if self._use_get:
            return self._sess.get(url, params=qdict, timeout=self._timeout, headers=headers, stream=is_stream)
        return self._sess.post(url, data=qdict, timeout=self._timeout, headers=headers,**req_kwargs)


    def _do_request_with_list(self, method:str, list_name:str, alist:list,
                           query:dict|None=None, headers:dict|None=None) -> Response:
        """Send a request with multiple values for a single key.

        Like _do_request but appends a list of values under the same key,
        bypassing the limitation of urlencode().
        """
        qdict = self._get_base_qdict()
        if query is not None:
            qdict.update(query)
        qdict[list_name] = alist

        if self._use_views:
            method += '.view'
        url = f"{self._base_url}:{self._port}/{self._server_path}/{method}"

        if not self._sess:
            self._sess = requests.Session()

        if self._use_get:
            return self._sess.get(url, params=qdict, timeout=self._timeout, headers=headers)
        return self._sess.post(url, data=qdict, timeout=self._timeout, headers=headers)


    def _do_request_with_lists(self, method:str, list_map:dict, query:dict|None=None, headers:dict|None=None) -> Response:
        """Send a request with multiple list parameters.

        Like _do_request_with_list but accepts a dict mapping parameter names
        to lists, allowing multiple list parameters in one request.

        Args:
            method: The API method name.
            list_map: A mapping of parameter name to list of values.
            query: The normal scalar query parameters.
            headers: Optional HTTP headers.

        Returns:
            The aiohttp.ClientResponse object.
        """
        qdict = self._get_base_qdict()
        if query is not None:
            qdict.update(query)
        qdict.update(list_map)

        if self._use_views:
            method += '.view'

        url = f"{self._base_url}:{self._port}/{self._server_path}/{method}"

        if not self._sess:
            self._sess = requests.Session()

        if self._use_get:
            return self._sess.get(url, params=qdict, timeout=self._timeout, headers=headers)
        return self._sess.post(url, data=qdict, timeout=self._timeout, headers=headers)


    def _handle_info_res(self, res: Response) -> dict:
        # Returns a parsed dictionary version of the result
        res.raise_for_status()
        data = res.json()
        dres = data["subsonic-response"]
        self._check_status(dres)
        return dres


    def _handle_bin_res(self, res: Response) -> Response:
        res.raise_for_status()
        ct = res.headers.get("Content-Type","")
        if ct.startswith("application/json") or ct.startswith("text/html"):
            data = res.json()
            dres = data["subsonic-response"]
            self._check_status(dres)
            raise errors.SonicError("Got text respone when expecting binary")
        return res
