import json
from base64 import b64decode
import requests
from bs4 import BeautifulSoup
import re


class Kodik:
    _crypt_step = None

    def __init__(self, link):
        response = requests.get(link)
        soup = BeautifulSoup(response.content, "lxml")
        self.urlParams = json.loads(re.findall(r"var urlParams = '(.*)';", response.text)[0])
        self.video_type = re.findall(r"videoInfo.type = '(.*)';", response.text)[0]
        self.video_hash = re.findall(r"videoInfo.hash = '(.*)';", response.text)[0]
        self.video_id = re.findall(r"videoInfo.id = '(.*)';", response.text)[0]
        script_url = soup.find_all("script")[1].get_attribute_list("src")[0]
        data = requests.get("https://kodik.info" + script_url).text
        self.post_link = b64decode(data[data.find("$.ajax") + 30: data.find("cache:!1") - 3].encode()).decode()


    def _convert_char(self, char: str, num):
        low = char.islower()
        alph = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if char.upper() in alph:
            ch = alph[(alph.index(char.upper()) + num) % len(alph)]
            if low:
                return ch.lower()
            else:
                return ch
        else:
            return char

    def _convert(self, string: str):
        if self._crypt_step:
            crypted_url = "".join([self._convert_char(i, self._crypt_step) for i in string])
            padding = (4 - (len(crypted_url) % 4)) % 4
            crypted_url += "=" * padding
            try:
                result = b64decode(crypted_url).decode("utf-8")
                if "mp4:hls:manifest" in result:
                    return result
            except UnicodeDecodeError:
                pass

        for rot in range(0, 26):
            crypted_url = "".join([self._convert_char(i, rot) for i in string])
            padding = (4 - (len(crypted_url) % 4)) % 4
            crypted_url += "=" * padding
            try:
                result = b64decode(crypted_url).decode("utf-8")
                if "mp4:hls:manifest" in result:
                    self._crypt_step = rot
                    return result
            except UnicodeDecodeError:
                continue
        else:
            raise "DecryptionFailure"

    def get_link(self):
        params = {
            "hash": self.video_hash,
            "id": self.video_id,
            "type": self.video_type,
            'd': self.urlParams['d'],
            'd_sign': self.urlParams['d_sign'],
            'pd': self.urlParams['pd'],
            'pd_sign': self.urlParams['pd_sign'],
            'ref': '',
            'ref_sign': self.urlParams['ref_sign'],
            'bad_user': 'true',
            'cdn_is_working': 'true',
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = requests.post(f"https://kodik.info{self.post_link}", data=params, headers=headers).json()
        data_url = data["links"]["360"][0]["src"]
        url = data_url if "mp4:hls:manifest" in data_url else self._convert(data_url)
        all_quality = [int(x) for x in data["links"].keys()]
        download_url = str(url).replace("https:", "")
        download_url = download_url[: download_url.rfind("/") + 1]
        return 'https:' + download_url + "{quality}" + '.mp4:hls:manifest.m3u8', all_quality

