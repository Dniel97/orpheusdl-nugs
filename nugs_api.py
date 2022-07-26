import hashlib
import json
import re
import secrets
from abc import ABC, abstractmethod
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
import urllib.parse as urlparse
from urllib.parse import parse_qs
from urllib3 import Retry


@dataclass
class NugsSubscription:
    subscription_id: str
    sub_cost_plan_id_access_list: str
    start_stamp: int
    end_stamp: int


class NugsNotAvailableError(Exception):
    def __init__(self, message):
        super(NugsNotAvailableError, self).__init__(message)


class NugsSession(ABC):
    """
    Nugs abstract session object with all (abstract) functions needed: auth_headers(), refresh()
    """
    def __init__(self):
        self.user_agent = None

        self.access_token = None
        self.refresh_token = None
        self.expires = None

        self.username = None
        self.user_id = None

        self.client_id = None
        self.dev_key = None

    @staticmethod
    def convert_timestamps(time_string: str):
        return int(datetime.strptime(time_string, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())

    def get_legacy_token(self):
        if self.access_token:
            # make sure to add padding?
            jwt = json.loads(b64decode(f"{self.access_token.split('.')[1]}===").decode('utf-8'))
            return jwt.get('legacy_token')
        return None

    def set_session(self, session: dict):
        self.access_token = session.get('access_token')
        self.refresh_token = session.get('refresh_token')
        self.expires = session.get('expires')
        self.user_id = session.get('user_id')
        self.username = session.get('username')

    def get_session(self):
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires': self.expires,
            'user_id': self.user_id,
            'username': self.username
        }

    def get_user(self):
        """
        Returns the user data.
        """
        if self.access_token:
            r = requests.get('https://id.nugs.net/connect/userinfo', headers=self.auth_headers())

            if r.status_code != 200:
                raise Exception(r.json())

            self.user_id = r.json()['sub']

    def get_subscription(self):
        """
        Returns the subscription status of the user.
        """
        if self.access_token:
            r = requests.get('https://subscriptions.nugs.net/api/v1/me/subscriptions/', headers=self.auth_headers())

            if r.status_code != 200:
                raise Exception(r.json())

            r = r.json()

            return NugsSubscription(
                subscription_id=r.get('legacySubscriptionId'),
                sub_cost_plan_id_access_list=r.get('promo').get('plan').get('id') if r.get('promo') else r.get('plan').get('id'),
                start_stamp=self.convert_timestamps(r.get('startedAt')),
                end_stamp=self.convert_timestamps(r.get('endsAt'))
            )

    @abstractmethod
    def auth_headers(self, use_access_token: bool = True) -> dict:
        pass

    @abstractmethod
    def auth(self, username: str, password: str):
        pass

    @abstractmethod
    def refresh(self):
        pass


class NugsApi:
    API_URL = 'https://streamapi.nugs.net/'

    def __init__(self, session: NugsSession):
        self.session = session

        self.s = requests.Session()

        retries = Retry(total=10,
                        backoff_factor=0.4,
                        status_forcelist=[429, 500, 502, 503, 504])

        self.s.mount('http://', HTTPAdapter(max_retries=retries))
        self.s.mount('https://', HTTPAdapter(max_retries=retries))

    def _get(self, url: str = '', params=None, parse_response: bool = True):
        if not params:
            params = {}

        r = self.s.get(f'{self.API_URL}{url}', params=params, headers=self.session.auth_headers())

        if r.status_code not in {200, 201, 202}:
            raise ConnectionError(r.text)

        if parse_response:
            r = r.json()
            if r.get('responseAvailabilityCode') == 0:
                return r.get('Response')
            raise NugsNotAvailableError(r.get('responseAvailabilityCodeStr'))

        return r.json()

    def get_album(self, album_id: str):
        return self._get('api.aspx', {
            'method': 'catalog.container',
            'containerID': album_id,
            'vdisp': 1
        })

    def get_user_playlist(self, playlist_id: str):
        return self._get('secureApi.aspx', {
            'method': 'user.playlist',
            'playlistID': playlist_id,
            'token': self.session.get_legacy_token(),
            'developerKey': self.session.dev_key,
            'user': self.session.username,
        })

    def get_artist(self, artist_id: str):
        return self._get('api.aspx', {
            'method': 'catalog.artist.years',
            'artistId': artist_id,
            'limit': '10',
        })

    def get_artist_albums(self, artist_id: str, offset: int = 1, limit: int = 100):
        return self._get('api.aspx', {
            'method': 'catalog.containersAll',
            'startOffset': offset,
            'artistList': artist_id,
            'limit': limit,
            'vdisp': '1',
            'availType':  '1'
        })

    def get_stream(self, track_id: str, sub: NugsSubscription, quality: int or None = 8):
        # quality can be 2, 5, 8, 9 or None
        return self._get('bigriver/subPlayer.aspx', {
            'trackID': track_id,
            'subscriptionID': sub.subscription_id,
            'subCostplanIDAccessList': sub.sub_cost_plan_id_access_list,
            'startDateStamp': sub.start_stamp,
            'endDateStamp': sub.end_stamp,
            'nn_userID': self.session.user_id,
            'app': '1',
            'platformID': quality
        }, parse_response=False)

    def get_search(self, query: str):
        return self._get('api.aspx', {
            'method': 'catalog.search',
            'searchStr': query
        })

    def get_all_artists(self):
        return self._get('api.aspx', {
            'method': 'catalog.artists'
        })


class NugsMobileSession(NugsSession):
    """
    Nugs session object based on the mobile Android oauth flow
    """

    def __init__(self, client_id: str, dev_key: str):
        super().__init__()

        self.NUGS_AUTH_BASE = 'https://id.nugs.net'

        self.client_id = client_id
        self.dev_key = dev_key

        self.redirect_uri = 'nugsnet://oauth2/callback'
        self.code_verifier = urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b'=')
        self.code_challenge = urlsafe_b64encode(hashlib.sha256(self.code_verifier).digest()).rstrip(b'=')
        self.user_agent = 'Mozilla/5.0 (Linux; Android 12; Google Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) ' \
                          'Chrome/103.0.0.0 Mobile Safari/537.36'

    def auth(self, username: str, password: str):
        s = requests.Session()
        s.headers.update({'User-Agent': self.user_agent})

        # get the login url
        r = s.get(f'{self.NUGS_AUTH_BASE}/connect/authorize', params={
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'response_type': 'code',
            'prompt': 'login',
            'state': urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b'='),
            'nonce': urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b'='),
            'scope': 'roles email profile openid nugsnet:api nugsnet:legacyapi offline_access',
            'code_challenge_method': 'S256'
        })

        assert r.status_code == 200

        # save the login url for later
        login_url = r.url

        # request the login site to get the __RequestVerificationToken from the form
        r = s.get(login_url)

        assert r.status_code == 200

        # extract the __RequestVerificationToken from the form
        request_verification_token = re.search(
            r'name="__RequestVerificationToken" type="hidden" value="(.*?)"', r.text).group(1)

        # ok that's dumb, but you have to disable redirects in order to avoid the InvalidSchema error because of the
        # redirect url: nugsnet://
        r = s.post(login_url, data={
            'Input.Email': username,
            'Input.Password': password,
            'Input.RememberLogin': 'true',
            '__RequestVerificationToken': request_verification_token
        }, allow_redirects=False)

        # so get the actual redirect_url finally, again disable redirects to avoid the InvalidSchema error
        if 'location' not in r.headers:
            raise Exception('Invalid username/password')

        # WHY IS THEIR STUPID API NOT RETURNING THE code_challenge PROPERLY?!
        r = s.get(f"{self.NUGS_AUTH_BASE}{r.headers['location']}", params={
            'code_challenge': self.code_challenge,
        }, allow_redirects=False)

        # extract the oauth code from the redirect url
        url = urlparse.urlparse(r.headers['location'])
        oauth_code = parse_qs(url.query)['code'][0]

        # exchange the code for access token
        r = s.post(f'{self.NUGS_AUTH_BASE}/connect/token', data={
            'code': oauth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri,
            'code_verifier': self.code_verifier,
            'client_id': self.client_id
        })

        assert (r.status_code == 200)

        self.access_token = r.json()['access_token']
        self.refresh_token = r.json()['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

        # save the user id in the session
        self.username = username
        self.get_user()

    def refresh(self):
        s = requests.Session()
        s.headers.update({'User-Agent': self.user_agent})

        # exchange the code for access token
        r = s.post(f'{self.NUGS_AUTH_BASE}/connect/token', data={
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'grant_type': 'refresh_token'
        })

        assert (r.status_code == 200)

        self.access_token = r.json()['access_token']
        self.refresh_token = r.json()['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

    def auth_headers(self, use_access_token: bool = True) -> dict:
        return {
            'User-Agent': 'NugsNet/3.16.1.682 (Android; 11; Xiaomi; Mi 9T Pro)',
            'Authorization': f'Bearer {self.access_token}' if use_access_token else None,
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }
