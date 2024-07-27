import re
import cloudscraper
import time
from requests.exceptions import HTTPError

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    merge_dicts,
    parse_duration,
    parse_resolution,
    str_to_int,
    url_or_none,
    urlencode_postdata,
    urljoin,
)

def get_page_content(url, request_interval=2, page_load_delay=2):
    # Create a cloudscraper instance with a random user agent
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False,
        }
    )

    # Pause before making the request
    time.sleep(request_interval)

    try:
        # Make the request to the URL
        response = scraper.get(url)
        response.raise_for_status()  # Check if the response was successful

        # Pause after receiving the response
        time.sleep(page_load_delay)

        return response.content

    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")  # Print the HTTP error
    except Exception as err:
        print(f"Other error occurred: {err}")  # Print any other error

    return None

class SpankBangIE(InfoExtractor):
    _VALID_URL = r'''(?x)
                    https?://
                        (?:[^/]+\.)?spankbang\.com/
                        (?:
                            (?P<id>[\da-z]+)/(?:video|play|embed)\b|
                            [\da-z]+-(?P<id_2>[\da-z]+)/playlist/[^/?#&]+
                        )
                    '''
    _TESTS = [{
        'url': 'https://spankbang.com/56b3d/video/the+slut+maker+hmv',
        'md5': '2D13903DE4ECC7895B5D55930741650A',
        'info_dict': {
            'id': '56b3d',
            'ext': 'mp4',
            'title': 'The Slut Maker HMV',
            'description': 'Girls getting converted into cock slaves.',
            'thumbnail': r're:^https?://.*\.jpg$',
            'uploader': 'Mindself',
            'uploader_id': 'mindself',
            'timestamp': 1617109572,
            'upload_date': '20210330',
            'age_limit': 18,
        },
    }, {
        # 480p only
        'url': 'http://spankbang.com/1vt0/video/solvane+gangbang',
        'only_matching': True,
    }, {
        # no uploader
        'url': 'http://spankbang.com/lklg/video/sex+with+anyone+wedding+edition+2',
        'only_matching': True,
    }, {
        # mobile page
        'url': 'http://m.spankbang.com/1o2de/video/can+t+remember+her+name',
        'only_matching': True,
    }, {
        # 4k
        'url': 'https://spankbang.com/1vwqx/video/jade+kush+solo+4k',
        'only_matching': True,
    }, {
        'url': 'https://m.spankbang.com/3vvn/play/fantasy+solo/480p/',
        'only_matching': True,
    }, {
        'url': 'https://m.spankbang.com/3vvn/play',
        'only_matching': True,
    }, {
        'url': 'https://spankbang.com/2y3td/embed/',
        'only_matching': True,
    }, {
        'url': 'https://spankbang.com/2v7ik-7ecbgu/playlist/latina+booty',
        'only_matching': True,
    }]

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        video_id = mobj.group('id') or mobj.group('id_2')
        
        # Use get_page_content to download the webpage content
        webpage = get_page_content(
            url.replace(f'/{video_id}/embed', f'/{video_id}/video')
        )

        if not webpage:
            raise ExtractorError(
                f'Failed to download webpage for video {video_id}', expected=True)

        if re.search(r'<[^>]+\b(?:id|class)=["\']video_removed', webpage.decode('utf-8')):
            raise ExtractorError(
                f'Video {video_id} is not available', expected=True)

        formats = []

        def extract_format(format_id, format_url):
            f_url = url_or_none(format_url)
            if not f_url:
                return
            f = parse_resolution(format_id)
            ext = determine_ext(f_url)
            if format_id.startswith('m3u8') or ext == 'm3u8':
                formats.extend(self._extract_m3u8_formats(
                    f_url, video_id, 'mp4', entry_protocol='m3u8_native',
                    m3u8_id='hls', fatal=False))
            elif format_id.startswith('mpd') or ext == 'mpd':
                formats.extend(self._extract_mpd_formats(
                    f_url, video_id, mpd_id='dash', fatal=False))
            elif ext == 'mp4' or f.get('width') or f.get('height'):
                f.update({
                    'url': f_url,
                    'format_id': format_id,
                })
                formats.append(f)

        STREAM_URL_PREFIX = 'stream_url_'

        for mobj in re.finditer(
                rf'{STREAM_URL_PREFIX}(?P<id>[^\s=]+)\s*=\s*(["\'])(?P<url>(?:(?!\2).)+)\2', webpage.decode('utf-8')):
            extract_format(mobj.group('id', 'url'))

        if not formats:
            stream_key = self._search_regex(
                r'data-streamkey\s*=\s*(["\'])(?P<value>(?:(?!\1).)+)\1',
                webpage.decode('utf-8'), 'stream key', group='value')

            stream = self._download_json(
                'https://spankbang.com/api/videos/stream', video_id,
                'Downloading stream JSON', data=urlencode_postdata({
                    'id': stream_key,
                    'data': 0,
                }), headers={
                    'Referer': url,
                    'X-Requested-With': 'XMLHttpRequest',
                })

            for format_id, format_url in stream.items():
                if format_url and isinstance(format_url, list):
                    format_url = format_url[0]
                extract_format(format_id, format_url)

        info = self._search_json_ld(webpage.decode('utf-8'), video_id, default={})

        title = self._html_search_regex(
            r'(?s)<h1[^>]+\btitle=["\']([^"]+)["\']>', webpage.decode('utf-8'), 'title', default=None)
        description = self._search_regex(
            r'<div[^>]+\bclass=["\']bottom[^>]+>\s*<p>[^<]*</p>\s*<p>([^<]+)',
            webpage.decode('utf-8'), 'description', default=None)
        thumbnail = self._og_search_thumbnail(webpage.decode('utf-8'), default=None)
        uploader = self._html_search_regex(
            r'<svg[^>]+\bclass="(?:[^"]*?user[^"]*?)">.*?</svg>([^<]+)', webpage.decode('utf-8'), 'uploader', default=None)
        uploader_id = self._html_search_regex(
            r'<a[^>]+href="/profile/([^"]+)"', webpage.decode('utf-8'), 'uploader_id', default=None)
        duration = parse_duration(self._search_regex(
            r'<div[^>]+\bclass=["\']right_side[^>]+>\s*<span>([^<]+)',
            webpage.decode('utf-8'), 'duration', default=None))
        view_count = str_to_int(self._search_regex(
            r'([\d,.]+)\s+plays', webpage.decode('utf-8'), 'view count', default=None))

        age_limit = self._rta_search(webpage.decode('utf-8'))

        return merge_dicts({
            'id': video_id,
            'title': title or video_id,
            'description': description,
            'thumbnail': thumbnail,
            'uploader': uploader,
            'uploader_id': uploader_id,
            'duration': duration,
            'view_count': view_count,
            'formats': formats,
            'age_limit': age_limit,
        }, info)
