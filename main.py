import configparser
import os.path
import re
import uuid
from os import makedirs
from os.path import join, exists, dirname
from shutil import rmtree

import m3u8_To_MP4
import requests
from bs4 import BeautifulSoup
from pick import pick
from .kodik import Kodik

DIRNAME = dirname(__file__)
CONFIG_FILE = os.path.join(DIRNAME, "config.ini")

invalid_chars = r'[\\/:*?"<>|]'

config = configparser.ConfigParser()
ROOT = ""
RESULT = ""
DOWNLOADS = ""
TEMP = ""


class Yummy:
    bad_quality = list()

    def __init__(self, url, yummy_token):
        self.yummy_token = yummy_token
        self.url = url
        while True:
            soup = BeautifulSoup(requests.get(url).content, "lxml")
            if soup.find("b", string="Ошибка доступа"):
                print("Токен устарел, укажите новый токен!")
                self.yummy_token = ask_new_token()
                config["DEFAULT"]["token"] = self.yummy_token
                save_config()
            else:
                break
        self.page_id = soup.find("meta", id="page_id")["content"]
        self.name = soup.find("h1", itemprop="name").text.strip()
        sanitized_name = re.sub(invalid_chars, '', self.name)
        sanitized_name = sanitized_name.strip(' .').strip()
        self.folder = join(DOWNLOADS, sanitized_name)
        makedirs(self.folder, exist_ok=True)
        print(f"FOLDER: {self.folder}")

    @staticmethod
    def get_dubbings(soup):
        return [i["value"] for i in soup.find("select", name="dubbings").find_all("option")]

    def get_series(self):
        response = requests.get(f'https://site.yummyani.me/catalog/edit-anime/{self.page_id}',
                                cookies={"yummy_token": self.yummy_token})
        soup = BeautifulSoup(response.content, "lxml")
        result = {}
        for ve in soup.find_all("li", class_="video-edit"):
            if ve["data-player"] == "Плеер Kodik":
                dub = ve["data-dub"]
                if dub not in result:
                    result[dub] = {}
                inputs = ve.find_all("input", class_="bordered")
                episode = inputs[0]["value"]
                link = inputs[1]["value"]
                link = link if link.startswith("http") else f"https:{link}"
                result[dub][episode] = link
        return result

    def download(self, data):
        for episode, link in data.items():
            _url, all_quality = Kodik(link).get_link()
            max_quality = max([i for i in all_quality if i not in self.bad_quality])
            url = _url.format(quality=max_quality)
            tmp = join(TEMP, uuid.uuid4().hex)
            makedirs(tmp, exist_ok=True)
            try:
                m3u8_To_MP4.multithread_download(url, mp4_file_dir=self.folder, mp4_file_name=episode, tmpdir=tmp)
                rmtree(tmp)
            except ValueError:
                print(self.url)
                new_link = input(f"ERROR: Enter m3u8 url manual, episode {episode}: ").strip()
                if not new_link:
                    _, index = pick([i for i in all_quality if i not in self.bad_quality][::-1], "Исключить качество")
                    self.bad_quality.append(all_quality[index])
                    max_quality = max([i for i in all_quality if i not in self.bad_quality])
                    new_link = _url.format(quality=max_quality)
                rmtree(tmp)
                makedirs(tmp, exist_ok=True)
                m3u8_To_MP4.multithread_download(new_link, mp4_file_dir=self.folder, mp4_file_name=episode, tmpdir=tmp)
            except Exception as e:
                print(f"Error in download episode {episode}")
                print(self.folder)
                print(self.url)
                raise e
        print("SUCCESS")
        print(self.folder)
        print(self.url)

    def run(self):
        series = self.get_series()
        option, index = pick([f"{k} ({len(v.keys())})" for k, v in series.items()], "Выберите озвучку")
        episodes = series[list(series.keys())[index]]
        _, index = pick(["Все", "Выбрать"], "Выберите серию")
        if index == 0:
            for_download = episodes
        else:
            selected = pick(["Все кроме выбранных"] + [f"{k}" for k in episodes.keys()], "Выберите серию",
                            multiselect=True, min_selection_count=1)
            all_except = False
            data = []
            for i, _ in selected:
                if i == 'Все кроме выбранных':
                    all_except = True
                else:
                    data.append(i)
            if all_except is False:
                for_download = {a: episodes[a] for a in data}
            else:
                for_download = {a: episodes[a] for a in episodes.keys() if a not in data}
        self.download(for_download)


def ask_new_token():
    print("Перейдти на сайт https://site.yummyani.me/\n"
          "Пройдите авторизацию и скопируйте yummy_token из любого запроса после авторизации\n")
    token = input("Укажите yummy_token: ").strip()
    return token


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
        config.write(configfile)


def execute():
    if exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8")
    else:
        config["DEFAULT"] = {
            "token": ask_new_token(),
            "root_path": input("Укажите путь для скачивания: ").strip()
        }
        save_config()
    global ROOT, DOWNLOADS, RESULT, TEMP
    ROOT = config["DEFAULT"]["root_path"]
    RESULT = join(ROOT, "yummy")
    DOWNLOADS = join(RESULT, "downloads")
    TEMP = join(RESULT, "temp")
    a_link = input("Укажите ссылку на страницу: ").strip()
    if a_link:
        Yummy(a_link, config["DEFAULT"]["token"]).run()
    else:
        name = input("Название: ").strip()
        if name:
            _sanitized_name = re.sub(invalid_chars, '_', name)
            _sanitized_name = _sanitized_name.strip(' .').strip()
            folder = join(DOWNLOADS, _sanitized_name)
            makedirs(folder, exist_ok=True)
            links = []
            while True:
                l = input("Добавить ссылку на скачивание?: ").strip()
                if l:
                    n = input("Номер серии?: ").strip()
                    links.append((l, n))
                else:
                    break
            for ll, nn in links:
                tmp = join(TEMP, uuid.uuid4().hex)
                makedirs(tmp, exist_ok=True)
                m3u8_To_MP4.multithread_download(ll, mp4_file_dir=folder, mp4_file_name=nn, tmpdir=tmp)
                rmtree(tmp)


def run():
    try:
        execute()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    run()