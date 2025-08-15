import re
import socket
import time
from os import makedirs, remove
from os.path import join, dirname, exists, isdir
from HdRezkaApi import HdRezkaApi, TVSeries
from tqdm import tqdm
import urllib.request
from pick import pick
import configparser
import json

socket.setdefaulttimeout(10)

DIRNAME = dirname(__file__)
CONFIG_FILE = join(DIRNAME, "config.ini")
ROOT = ""
FOLDER = ""

invalid_chars = r'[\\/:*?"<>|]'
config = configparser.ConfigParser()

quality_suffix_priority = {
    'ultra': 3,
    'hdr': 2,
    'high': 1,
    '': 0
}


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
        config.write(configfile)


class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, t_size=None):
        if t_size is not None:
            self.total = t_size
        self.update(b * bsize - self.n)


class Rezka:
    translator = None
    season = None
    episodes = [None]

    def __init__(self, url):
        self.url = url
        self.rezka = HdRezkaApi(url, cookies=json.loads(config["REZKA"].get("cookies", "{}")))
        if not self.rezka.ok:
            if self.rezka.exception:
                if str(self.rezka.exception) == "401: Unauthorized":
                    if not config["REZKA"].get("email") and not config["REZKA"].get("pwd"):
                        config["REZKA"]["email"] = ask_new_data(
                            "Отправьте ваш email для авторизации: ",
                            validation=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,7}$')
                        config["REZKA"]["pwd"] = ask_new_data("Отправьте ваш пароль для авторизации: ")
                        save_config()
                    self.rezka = HdRezkaApi(url)
                    self.rezka.login(config["REZKA"]["email"], config["REZKA"]["pwd"], raise_exception=True)
                    config["REZKA"]["cookies"] = json.dumps(self.rezka.cookies)
                    save_config()
                    assert self.rezka.ok, self.rezka.exception
            else:
                raise self.rezka.exception

    def run(self):
        self.pick_translators()
        if self.rezka.type == TVSeries:
            self.pick_season()
            self.pick_episodes()
        self.download()

    def parse_quality(self, q):
        num_match = re.search(r'(\d+)', q)
        num = int(num_match.group(1)) if num_match else 0
        suffix = q.lower().replace('p', '').replace(str(num), '').strip()
        suffix_priority = quality_suffix_priority.get(suffix, 0)
        return num, suffix_priority

    def pick_translators(self):
        translators_ids, options = [], []
        if self.rezka.type == TVSeries:
            for k, v in self.rezka.seriesInfo.items():
                translators_ids.append(k)
                options.append(f"{v['translator_name']} [{' ,'.join([f'Сезон {kk} ({len(list(
                    vv.keys()))})' for kk, vv in v['episodes'].items()])}]")
            _, index = pick(options, "Выберите озвучку")
            self.translator = translators_ids[index]
        else:
            _, index = pick([i["name"] for i in self.rezka.translators.values()], "Выберите озвучку")
            self.translator = list(self.rezka.translators.keys())[index]

    def pick_season(self):
        _, index = pick(list(self.rezka.seriesInfo[self.translator]["seasons"].values()), "Выберите сезон")
        self.season = list(self.rezka.seriesInfo[self.translator]["seasons"].keys())[index]

    def pick_episodes(self):
        option, index = pick(["Все", "Выбрать"], "Выберите серию")
        series = self.rezka.seriesInfo[self.translator]["episodes"][self.season]
        if option == "Все":
            self.episodes = list(series.keys())
        else:
            selected = pick(["Все кроме выбранных"] + list(series.values()), "Выберите серию", multiselect=True,
                            min_selection_count=1)
            all_except = False
            data = []
            for i, _ in selected:
                if i == 'Все кроме выбранных':
                    all_except = True
                else:
                    data.append(i)
            if all_except is False:
                self.episodes = [k for k, v in series.items() if v in data]
            else:
                self.episodes = [k for k, v in series.items() if v not in data]

    def get_episode_link(self):
        def make_call(seria, retry=True):
            try:
                stream = self.rezka.getStream(self.season, seria, self.translator)
                return stream
            except Exception as e:
                if retry:
                    time.sleep(1)
                    return make_call(seria, retry=False)
                ex_name = e.__class__.__name__
                ex_desc = e
                print(f"{ex_name} > ep:{episode}: {ex_desc}")

        for episode in self.episodes:
            yield episode, make_call(episode)

    def download(self):
        sanitized_name = re.sub(invalid_chars, '', self.rezka.name)
        sanitized_name = sanitized_name.strip(' .').strip()
        season_path = join(FOLDER, sanitized_name)
        for a, i in self.get_episode_link():
            best_quality = max(i.videos.keys(), key=self.parse_quality)
            best_links = i.videos[best_quality]
            filename = f"S{self.season}E{a:02d}.mp4" if self.rezka.type == TVSeries else f"{sanitized_name}.mp4"
            episode_path = join(season_path, filename)
            makedirs(season_path, exist_ok=True)
            for links in best_links:
                try:
                    with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=filename) as t:
                        urllib.request.urlretrieve(links, filename=episode_path, reporthook=t.update_to)
                        break
                except:
                    pass
        print("SUCCESS")
        print(season_path)
        print(self.url)


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


def load_config():
    if exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8")
        if config.has_section("REZKA"):
            config.read(CONFIG_FILE, encoding="utf-8")
            return True
    return False


def execute():
    if not load_config():
        config["REZKA"] = {
            "root_path": ask_new_data("Укажите путь к папке для скачивания: ", validation="folder")
        }
        save_config()
    global ROOT, FOLDER
    ROOT = config["REZKA"]["root_path"]
    FOLDER = join(ROOT, "hdrezka")
    Rezka(ask_new_data("url: ")).run()


def remove_config():
    if load_config():
        config.remove_section("REZKA")
        save_config()


def run():
    try:
        execute()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    run()
