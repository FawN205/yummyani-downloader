import configparser
import os.path
import re
import uuid
from os import makedirs
from os.path import join, exists, dirname, isdir
from shutil import rmtree
from urllib.parse import urlparse

import m3u8_To_MP4
import requests
from bs4 import BeautifulSoup
from pick import pick

from kodik import Kodik
import lxml

DIRNAME = dirname(__file__)
CONFIG_FILE = os.path.join(DIRNAME, "config.ini")

invalid_chars = r'[\\/:*?"<>|]'

config = configparser.ConfigParser()
ROOT = ""
RESULT = ""
DOWNLOADS = ""
TEMP = ""


def asc_creeds():
    if not config["YUMMY"].get("email") and not config["YUMMY"].get("pwd"):
        config["YUMMY"]["email"] = ask_new_data(
            "Отправьте ваш email для авторизации: ",
            validation=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,7}$')
        config["YUMMY"]["pwd"] = ask_new_data("Отправьте ваш пароль для авторизации: ")
        save_config()


class Yummy:
    bad_quality = list()

    def __init__(self, url):
        self.url = url
        soup = BeautifulSoup(requests.get(url).content, "lxml")
        self.page_id = soup.find("meta", id="page_id")["content"]
        self.name = soup.find("h1", itemprop="name").text.strip()
        sanitized_name = re.sub(invalid_chars, '', self.name)
        sanitized_name = sanitized_name.strip(' .').strip()
        self.folder = join(DOWNLOADS, sanitized_name)
        makedirs(self.folder, exist_ok=True)
        print(f"FOLDER: {self.folder}")

    def login(self):
        uri = urlparse(self.url)
        response = requests.post(f'{uri.scheme}://{uri.netloc}/api/profile/login',
                                 json={'login': config["YUMMY"]["email"], 'password': config["YUMMY"]["pwd"]})
        response.raise_for_status()
        cookie = response.headers.get("Set-Cookie")
        assert cookie, ("Ошибка авторизации, не удалось войти на сайт, используйте команду yummy_remove_config для "
                        "очистки текущего конфига, проверьте логин и пароль на сайте, и попробуйтеповторно")
        return cookie.replace("yummy_token=", "")

    @staticmethod
    def get_dubbings(soup):
        return [i["value"] for i in soup.find("select", name="dubbings").find_all("option")]

    def get_series(self, retry=True):
        yummy_token = config["YUMMY"].get("token")
        if not yummy_token:
            asc_creeds()
            yummy_token = self.login()
            config["YUMMY"]["token"] = yummy_token
            save_config()
        response = requests.get(f'https://site.yummyani.me/catalog/edit-anime/{self.page_id}',
                                cookies={"yummy_token": yummy_token})
        soup = BeautifulSoup(response.content, "lxml")
        if soup.find("b", string="Ошибка доступа"):
            if retry:
                del config["YUMMY"]["token"]
                return self.get_series(retry=False)
            else:
                raise Exception("Ошибка авторизации, не удалось войти на сайт, используйте команду yummy_remove_config "
                                "для очистки текущего конфига, проверьте логин и пароль на сайте, и попробуйтеповторно")
        result = {}
        for ve in soup.find_all("li", class_="video-edit"):
            if "Kodik" in ve["data-player"]:
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
            all_quality = all_quality[::-1]
            max_quality = max([i for i in all_quality if i not in self.bad_quality])
            url = _url.format(quality=max_quality)
            tmp = join(TEMP, uuid.uuid4().hex)
            makedirs(tmp, exist_ok=True)
            try:
                m3u8_To_MP4.multithread_download(url, mp4_file_dir=self.folder, mp4_file_name=episode, tmpdir=tmp)
                rmtree(tmp)
            except ValueError:
                print(self.url)
                new_link = ask_new_data(f"ERROR: Enter m3u8 url manual, episode {episode}: ")
                if not new_link:
                    _, index = pick([i for i in all_quality if i not in self.bad_quality], "Исключить качество")
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
            selected = pick(["Все кроме выбранных"] + list(episodes.keys()), "Выберите серию",
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


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
        config.write(configfile)


def load_config():
    if exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8")
        if config.has_section("YUMMY"):
            return True
    return False


def remove_config():
    if load_config():
        config.remove_section("YUMMY")
        save_config()


def ask_new_data(message, validation=None):
    while True:
        data = input(message).strip()
        if data:
            if validation:
                if validation == "folder":
                    if isdir(data):
                        return data
                    else:
                        print(f"Папка по пути {data} не найдена, укажите путь к существующей папке!")
                else:
                    if re.findall(validation, data):
                        return data
                    else:
                        print("Ошибка валидации!")
            else:
                return data
        else:
            print("Вы отправили пустую строку!")


def execute():
    if not load_config():
        config["YUMMY"] = {
            "root_path": ask_new_data("Укажите путь на папку для скачивания: ", validation="folder")
        }
        save_config()
    global ROOT, DOWNLOADS, RESULT, TEMP
    ROOT = config["YUMMY"]["root_path"]
    RESULT = join(ROOT, "yummy")
    DOWNLOADS = join(RESULT, "downloads")
    TEMP = join(RESULT, "temp")
    a_link = ask_new_data("Укажите ссылку на страницу: ")
    if a_link:
        Yummy(a_link).run()
    else:
        name = ask_new_data("Название: ")
        if name:
            _sanitized_name = re.sub(invalid_chars, '_', name)
            _sanitized_name = _sanitized_name.strip(' .').strip()
            folder = join(DOWNLOADS, _sanitized_name)
            makedirs(folder, exist_ok=True)
            links = []
            while True:
                l = ask_new_data("Добавить ссылку на скачивание?: ")
                if l:
                    n = ask_new_data("Номер серии?: ")
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
