import logging
import re
from datetime import datetime

from .mqa_identifier_python.mqa_identifier_python.mqa_identifier import MqaIdentifier
from .nugs_api import NugsMobileSession, NugsApi
from utils.utils import create_temp_filename, create_requests_session
from utils.models import *


module_information = ModuleInformation(
    service_name='nugs',
    module_supported_modes=ModuleModes.download | ModuleModes.covers,
    session_settings={'username': '', 'password': '', 'client_id': 'Eg7HuH873H65r5rt325UytR5429',
                      'dev_key': 'x7f54tgbdyc64y656thy47er4'},
    session_storage_variables=['access_token', 'refresh_token', 'expires', 'user_id', 'username'],
    netlocation_constant='nugs',
    url_decoding=ManualEnum.manual,
    test_url='https://play.nugs.net/#/catalog/recording/28751'
)


class ModuleInterface:
    def __init__(self, module_controller: ModuleController):
        self.cover_size = module_controller.orpheus_options.default_cover_options.resolution
        self.exception = module_controller.module_error
        self.oprinter = module_controller.printer_controller
        self.print = module_controller.printer_controller.oprint
        self.temp_settings = module_controller.temporary_settings_controller

        # the numbers are the priorities from self.format_parse
        self.quality_parse = {
            QualityEnum.MINIMUM: 0,
            QualityEnum.LOW: 0,
            QualityEnum.MEDIUM: 0,
            QualityEnum.HIGH: 0,
            QualityEnum.LOSSLESS: 2,
            QualityEnum.HIFI: 3,
        }

        self.format_parse = {
            ".alac16/": {'codec': CodecEnum.ALAC, 'bitrate': 1411, 'priority': 1},
            ".flac16/": {'codec': CodecEnum.FLAC, 'bitrate': 1411, 'priority': 2},
            ".mqa24/": {'codec': CodecEnum.MQA, 'bitrate': None, 'priority': 3},
            ".s360/": {'codec': CodecEnum.MHA1, 'bitrate': 336, 'priority': 4},
            ".aac150/": {'codec': CodecEnum.AAC, 'bitrate': 150, 'priority': 0},
        }

        self.session = NugsApi(NugsMobileSession(module_controller.module_settings['client_id'],
                                                 module_controller.module_settings['dev_key']))

        session = {
            'access_token': self.temp_settings.read('access_token'),
            'refresh_token': self.temp_settings.read('refresh_token'),
            'expires': self.temp_settings.read('expires'),
            'user_id': self.temp_settings.read('user_id'),
            'username': self.temp_settings.read('username')
        }

        self.session.session.set_session(session)

        if session['refresh_token'] is not None and datetime.now() > session['expires']:
            # access token expired, get new refresh token
            self.refresh_token()

        self.sub = self.session.session.get_subscription()

    def login(self, email: str, password: str):
        logging.debug(f'{module_information.service_name}: no session found, login')
        self.session.session.auth(email, password)

        # save the new access_token, refresh_token and expires in the temporary settings
        self.temp_settings.set('access_token', self.session.session.access_token)
        self.temp_settings.set('refresh_token', self.session.session.refresh_token)
        self.temp_settings.set('expires', self.session.session.expires)
        self.temp_settings.set('user_id', self.session.session.user_id)
        self.temp_settings.set('username', self.session.session.username)

        self.sub = self.session.session.get_subscription()

    def refresh_token(self):
        logging.debug(f'{module_information.service_name}: access_token expired, getting a new one')

        # get a new access_token and refresh_token from the API
        self.session.session.refresh()

        # save the new access_token, refresh_token and expires in the temporary settings
        self.temp_settings.set('access_token', self.session.session.access_token)
        self.temp_settings.set('refresh_token', self.session.session.refresh_token)
        self.temp_settings.set('expires', self.session.session.expires)
        self.temp_settings.set('user_id', self.session.session.user_id)
        self.temp_settings.set('username', self.session.session.username)

    @staticmethod
    def custom_url_parse(link: str):
        # the most beautiful regex ever written
        match = re.search(r'https?://play.nugs.net/#/(artist|catalog/recording|playlists/playlist)/(\d+)', link)

        # so parse the regex "match" to the actual DownloadTypeEnum
        media_types = {
            'catalog/recording': DownloadTypeEnum.album,
            'artist': DownloadTypeEnum.artist,
            'playlists/playlist': DownloadTypeEnum.playlist,
        }

        return MediaIdentification(
            media_type=media_types[match.group(1)],
            media_id=match.group(2),
        )

    def search(self, query_type: DownloadTypeEnum, query, track_info: TrackInfo = None, limit: int = 10):
        results = self.session.get_search(query)

        items = []
        if query_type == DownloadTypeEnum.artist:
            # nugs don't return the artistID so you have to fetch ALLLLLLL freaking artists
            all_artists_data = self.session.get_all_artists().get('artists')
            artist_results = [r for r in results.get('catalogSearchTypeContainers') if r.get('matchType') == 1]

            if len(artist_results) == 0:
                return items

            for artist_result in artist_results[0].get('catalogSearchContainers'):
                artist_name = artist_result.get('matchedStr')
                # then you search for the matched artist string in ALL artists....
                artist_data = [a for a in all_artists_data if a.get('artistName') == artist_name][0]

                # get additional info such as numAlbums
                total_albums = artist_data.get('numAlbums')
                items.append(SearchResult(
                    result_id=artist_data.get('artistID'),
                    name=artist_data.get('artistName'),
                    additional=[f"{total_albums} album{'s' if total_albums != 1 else ''}"],
                ))

        elif query_type == DownloadTypeEnum.album:
            album_results = [r for r in results.get('catalogSearchTypeContainers') if r.get('matchType') == 6]

            if len(album_results) == 0:
                return items

            for album_result in album_results[0].get('catalogSearchContainers'):
                for album_data in album_result.get('catalogSearchResultItems'):
                    items.append(SearchResult(
                        result_id=album_data.get('containerID'),
                        artists=[album_data.get('artistName')],
                        name=album_data.get('containerName'),
                    ))

        elif query_type == DownloadTypeEnum.track:
            track_results = [r for r in results.get('catalogSearchTypeContainers') if r.get('matchType') == 2]

            if len(track_results) == 0:
                return items

            for track_result in track_results[0].get('catalogSearchContainers'):
                for track_data in track_result.get('catalogSearchResultItems'):
                    track_data['albumID'] = track_data.get('containerID')
                    items.append(SearchResult(
                        result_id=track_data.get('songID'),
                        artists=[track_data.get('artistName')],
                        name=f"High Hopes: {track_data.get('containerName')}",
                        # get_track_info required the album_id and the track_data
                        extra_kwargs={'data': {track_data.get('songID'): track_data}}
                    ))
        else:
            raise Exception('Query type is invalid')

        return items

    def get_artist_info(self, artist_id: str, get_credited_albums: bool) -> ArtistInfo:
        artist_data = self.session.get_artist(artist_id)
        artist_albums_data = self.session.get_artist_albums(artist_id)

        # now save all the albums
        artist_albums = [a for a in artist_albums_data.get('containers') if a.get('containerType') == 1]
        total_items = artist_albums_data.get('totalMatchedRecords')
        for page in range(2, total_items // 100 + 2):
            print(f'Fetching {page * 100}/{total_items}', end='\r')
            artist_albums += [a for a in self.session.get_artist_albums(artist_id, offset=page).get('containers')
                              if a.get('containerType') == 1]

        return ArtistInfo(
            name=artist_data.get('ownerName'),
            albums=[a.get('containerID') for a in artist_albums],
            album_extra_kwargs={'data': {a.get('containerID'): a for a in artist_albums}},
        )

    def get_playlist_info(self, playlist_id):
        playlist_data = self.session.get_user_playlist(playlist_id)

        cache = {'data': {t.get('track').get('songID'): t.get('track') for t in playlist_data.get('items')}}
        for track in playlist_data.get('items'):
            # stupid API don't save the albumID in the track so every track has the album data attached in
            # playlistContainer, so dumb
            album_data = track.get('playlistContainer')
            cache['data'][track.get('track').get('songID')]['albumID'] = album_data.get('containerID')

        return PlaylistInfo(
            name=playlist_data.get('playListName'),
            creator='Unknown',
            creator_id=playlist_data.get('userID'),
            release_year=int(playlist_data.get('createDate')[:4]) if playlist_data.get('createDate') else None,
            tracks=[t.get('track').get('songID') for t in playlist_data.get('items')],
            track_extra_kwargs=cache
        )

    def get_album_info(self, album_id: str, data=None) -> AlbumInfo:
        # check if album is already in album cache, add it
        if data is None:
            data = {}

        album_data = data.get(album_id) if album_id in data else self.session.get_album(album_id)

        # create the cache with all the tracks and the album data
        cache = {'data': {album_id: album_data}}
        cache['data'].update({s.get('songID'): s for s in album_data.get('songs')})
        for track in album_data.get('songs'):
            cache['data'][track.get('songID')]['albumID'] = album_id

        return AlbumInfo(
            name=album_data.get('containerInfo'),
            release_year=album_data.get('releaseDateFormatted')[:4] if album_data.get('releaseDateFormatted') else None,
            cover_url=f"https://secure.livedownloads.com{album_data.get('img').get('url')}",
            artist=album_data.get('artistName'),
            artist_id=album_data.get('artistID'),
            tracks=[t.get('songID') for t in album_data.get('songs')],
            track_extra_kwargs=cache
        )

    def parse_stream_format(self, stream_url: str):
        # return the quality of the stream and None if it's not a file
        for key, value in self.format_parse.items():
            if key in stream_url:
                return value
        return None

    def get_track_info(self, track_id: str, quality_tier: QualityEnum, codec_options: CodecOptions,
                       data=None) -> TrackInfo:
        if data is None:
            data = {}

        track_data = data[track_id] if track_id in data else None
        # get the manually added albumID
        album_id = track_data.get('albumID')

        album_data = data[album_id] if album_id in data else self.session.get_album(album_id)

        track_name = track_data.get('songTitle')
        release_year = album_data.get('releaseDateFormatted')[:4] if album_data.get('releaseDateFormatted') else None

        tags = Tags(
            album_artist=album_data.get('artistsID'),
            track_number=track_data.get('trackNum'),
            disc_number=track_data.get('discNum'),
            total_tracks=len(album_data.get('songs')),
            release_date=album_data.get('releaseDateFormatted').replace('/', '-') if album_data.get(
                'releaseDateFormatted') else None,
            copyright=f'© {release_year} {album_data.get("licensorName")}',
        )

        error, selected_stream, quality, mqa_file = None, None, None, None

        # why is the API so stupid? Those formats make absolutely no sense, and it's random what you get
        stream_data = []
        for stream_format in [9, 5, 2, None]:
            stream_url = self.session.get_stream(track_data.get('trackID'), self.sub, stream_format).get('streamLink')
            quality = self.parse_stream_format(stream_url)
            if quality:
                stream = {'stream_url': stream_url}
                stream.update(quality)
                stream_data.append(stream)

        # sort the dict by priority
        stream_data = sorted(stream_data, key=lambda k: k['priority'], reverse=True)

        # check if the track is spatial and if spatial_codecs is enabled
        if not codec_options.spatial_codecs and any([codec_data[s.get('codec')].spatial for s in stream_data]):
            self.print(f'Spatial codecs are disabled, if you want to download Sony 360RA, '
                       f'set "spatial_codecs": true', drop_level=1)

        # check if the track is proprietary and if proprietary_codecs is enabled
        if not codec_options.proprietary_codecs and any([codec_data[s.get('codec')].proprietary for s in stream_data]):
            self.print(f'Proprietary codecs are disabled, if you want to download MQA, '
                       f'set "proprietary_codecs": true', drop_level=1)

        # get the highest wanted quality from the settings.json
        highest_priority = self.quality_parse[quality_tier]
        # set the highest wanted priority to match Sony 360RA
        if codec_options.spatial_codecs:
            highest_priority = 4

        wanted_quality = [i for i in range(highest_priority + 1)]

        # remove the MQA priority
        if not codec_options.proprietary_codecs:
            wanted_quality.remove(3)

        # filter out non-valid streams
        valid_streams = [i for i in stream_data if i['priority'] in wanted_quality]

        if len(valid_streams) > 0:
            # select the highest valid stream
            selected_stream = valid_streams[0]
            track_codec = selected_stream.get('codec')
            bitrate = selected_stream.get('bitrate')

            # https://en.wikipedia.org/wiki/Audio_bit_depth#cite_ref-1
            bit_depth = 16 if track_codec in {CodecEnum.FLAC, CodecEnum.ALAC} else None
            sample_rate = 48 if track_codec in {CodecEnum.MHA1} else 44.1

            if track_codec == CodecEnum.MQA:
                # download the first chunk of the flac file to analyze it
                temp_file_path = self.download_temp_header(selected_stream.get('stream_url'))

                # detect MQA file
                mqa_file = MqaIdentifier(temp_file_path)

        else:
            error = f'Selected quality is not available'
            track_codec = CodecEnum.NONE
            bitrate = None
            bit_depth = None
            sample_rate = None

        # now set everything for MQA
        if mqa_file is not None and mqa_file.is_mqa:
            bit_depth = mqa_file.bit_depth
            sample_rate = mqa_file.get_original_sample_rate()

        track_info = TrackInfo(
            name=track_name,
            album=album_data.get('containerInfo'),
            album_id=album_data.get('containerID'),
            artists=[album_data.get('artistName')],
            artist_id=album_data.get('artistID'),
            release_year=release_year,
            cover_url=f"https://secure.livedownloads.com{album_data.get('img').get('url')}",
            tags=tags,
            codec=track_codec,
            bitrate=bitrate,
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            download_extra_kwargs={'stream_url': selected_stream.get('stream_url')},
            error=error
        )

        return track_info

    @staticmethod
    def download_temp_header(file_url: str, chunk_size: int = 32768) -> str:
        # create flac temp_location
        temp_location = create_temp_filename() + '.flac'

        # create session and download the file to the temp_location
        r_session = create_requests_session()

        r = r_session.get(file_url, stream=True, verify=False)
        with open(temp_location, 'wb') as f:
            # only download the first chunk_size bytes
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    break

        return temp_location

    def get_track_download(self, stream_url: str) -> TrackDownloadInfo:
        return TrackDownloadInfo(
            download_type=DownloadEnum.URL,
            file_url=stream_url,
            file_url_headers={'User-Agent': self.session.session.user_agent}
        )
