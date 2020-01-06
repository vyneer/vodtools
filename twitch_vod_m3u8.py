# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import streamlink
import pytz
import requests
import time
import json
import sys
import datetime
import client_twitch_oauth
import threading
import argparse
import m3u8
import re
import sqlite3
import pathlib
import logging

logger = logging.getLogger(__name__)
logformat = logging.Formatter('[%(levelname)s][%(threadName)s][%(asctime)s] %(message)s')

fileHandler = logging.FileHandler("vodtools-local.log")
fileHandler.setFormatter(logformat)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logformat)
logger.addHandler(consoleHandler)

class gensingle():
    def __init__(self, username):
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        
        # user configuration
        self.username = username
        self.user_id = None
        self.user_id = self.get_id()

    def find_anipreview(self, vod_id):
        url = 'https://api.twitch.tv/kraken/videos/' + vod_id
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1
        result = re.findall(r"(?<=\/)[^\/]+(?=\/)", info['animated_preview_url'])
        return result[1]

    def get_id(self):
        url = 'https://api.twitch.tv/helix/users?login=' + self.username
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info['data'] != []:
                logger.debug("Got userid from username - "+info["data"][0]["id"])
            else:
                return "banned"
        except requests.exceptions.RequestException as e:
            logger.debug("Error in get_id: " + str(e))
        
        return info["data"][0]["id"]

    def check_videos(self):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/helix/videos?user_id=' + self.user_id + "&first=100"
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info

    def run(self):
        status, info = self.check_videos()
        if info != None and info['data'] != []:
            if status == 0:
                with open(datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")+"_"+self.username + ".txt", "w") as memefile:
                    for x in range(len(info['data'])-1, -1, -1):
                        secreturl = self.find_anipreview(info['data'][x]['id'])
                        if secreturl != "":
                            fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
                            logger.debug("Found link "+ fullurl)
                            if info['data'][x]['type'] == 'archive':
                                values = info['data'][x]['created_at'] + " - " + info['data'][x]['title'] + " - " + info['data'][x]['url'] + " - " + fullurl + "\n"
                                memefile.write(values)
                                logger.info("Added " + str(self.username) + "'s VOD "+ info['data'][x]['url'] + " to the file.")
                        else:
                            logger.debug("No animated preview available at the moment for "+ str(self.username) + ".")
            else:
                 logger.error("HTTP error.")
                
class genmuted():
    def __init__(self, url):
        self.url=url

    def loadM3u8(self, m3u8url):
        def load_m3u8(url):
            urls = []
            m = m3u8.load(url)
            for seg in m.segments:
                urls.append(seg.absolute_uri)
            return urls
        try:
            videoUrls = load_m3u8(m3u8url)
        except Exception as e:
            return {'reason': 'load_m3u8 {}'.format(e)} 
        else:
            return {'videoUrls': videoUrls}
    
    def run(self):
        yourl = self.url[:-14]

        r = requests.get(self.url, stream=True)
        open("index-dvr.m3u8", "wb").write(r.content)

        tslinks = self.loadM3u8("index-dvr.m3u8")
        i=0

        with open("buffer.txt", "w") as f:
            for tsurl in tslinks['videoUrls']:
                i+=1
                r = requests.head(yourl + tsurl)
                if r.status_code == 403:
                    tsurl = yourl + tsurl[:-3] + "-muted.ts"
                    print('\nfixed\n')
                    print(tsurl)
                    f.writelines(tsurl+'\n')
                elif r.status_code == 200:
                    tsurl = yourl + tsurl
                    print('\nskipped\n')
                    print(tsurl)
                    f.writelines(tsurl+'\n')

        a=9

        lines = open("index-dvr.m3u8").read().splitlines()
        with open("buffer.txt", "r") as f:
            for line in f:
                lines[a]=line.rstrip()
                a+=2
        open('index-dvr-muted.m3u8','w').write('\n'.join(lines))

class vodthread(threading.Thread):
    def __init__(self, username, quality, subonly, refreshtime):
        threading.Thread.__init__(self)
        # global configuration
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        self.refresh = refreshtime
        
        # user configuration
        self.username = username
        self.quality = quality
        self.subonly = subonly
        self.old_status = 0
        self.user_id = None
        self.user_id = self.get_id()
        streaml.set_plugin_option("twitch", "twitch_oauth_token", self.oauth_token)

    def run(self):
        self.loopcheck()

    def check_videos(self):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/helix/videos?user_id=' + self.user_id + "&first=100"
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info

    def find_anipreview(self, vod_id):
        url = 'https://api.twitch.tv/kraken/videos/' + vod_id
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        result = re.findall(r"(?<=\/)[^\/]+(?=\/)", info['animated_preview_url'])
        return result[1]

    def check_online(self):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/kraken/streams/' + self.username
        info = None
        status = 3
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info['stream'] == None:
                status = 1
            else:
                status = 0
        except requests.exceptions.RequestException as e:
            if e.response:
                if e.response.reason == 'Not Found' or e.response.reason == 'Unprocessable Entity':
                    status = 2

        return status

    def get_id(self):
        url = 'https://api.twitch.tv/helix/users?login=' + self.username
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info['data'] != []:
                logger.debug("Got userid from username - "+info["data"][0]["id"])
            else:
                return "banned"
        except requests.exceptions.RequestException as e:
            logger.debug("Error in get_id: " + str(e))
        
        return info["data"][0]["id"]

    def vodchecker(self):
        path = pathlib.Path(self.username + "_vods.db")
        if path.exists() != True:
            conn = sqlite3.connect(self.username + "_vods.db")
            cursor=conn.cursor()
            cursor.execute("""CREATE TABLE vods (timecode text, title text, twitchurl text, vodurl text, type text)""")
        conn = sqlite3.connect(self.username + "_vods.db")
        status, info = self.check_videos()
        cursor=conn.cursor()
        cursor.execute('SELECT * FROM vods WHERE twitchurl=?', (info['data'][0]['url'],))
        if info != None and info['data'] != [] and cursor.fetchone() is None:
            if status == 0:
                for x in range(len(info['data'])-1, -1, -1):
                    m3u8check = False
                    if self.subonly == False:
                        try:
                            streams = streaml.streams(info['data'][x]['url'])
                            if self.quality not in streams:
                                self.quality = "best"
                            cursor.execute('SELECT * FROM vods WHERE vodurl=?', (streams[self.quality].url,))
                            if cursor.fetchone() is None:
                                m3u8check = True
                            logger.debug("Found link "+ streams[self.quality].url)
                            if m3u8check and "muted" not in streams[self.quality].url and info['data'][x]['type'] == 'archive':
                                values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[self.quality].url, 'clean']
                                cursor.execute("INSERT INTO vods VALUES (?,?,?,?,?)", values)
                                logger.info("Added " + str(self.username) + "'s clean VOD "+ info['data'][x]['url'] + " to the list.")
                            if m3u8check and "muted" in streams[self.quality].url and info['data'][x]['type'] == 'archive':
                                values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[self.quality].url, 'muted']
                                cursor.execute("INSERT INTO vods VALUES (?,?,?,?,?)", values)
                                logger.info("Added " + str(self.username) + "'s muted VOD "+ info['data'][x]['url'] + " to the list.")
                        except streamlink.exceptions.PluginError as e:
                            logger.error("Streamlink error: "+str(e))
                    else:
                        secreturl = self.find_anipreview(info['data'][x]['id'])
                        if secreturl != "":
                            fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
                            cursor.execute('SELECT * FROM vods WHERE vodurl=?', (fullurl,))
                            if cursor.fetchone() is None:
                                m3u8check = True
                            logger.debug("Found link "+ fullurl)
                            if m3u8check and info['data'][x]['type'] == 'archive':
                                values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], fullurl, 'subonly']
                                cursor.execute("INSERT INTO vods VALUES (?,?,?,?,?)", values)
                                logger.info("Added " + str(self.username) + "'s subonly VOD "+ info['data'][x]['url'] + " to the list.")
                        else:
                            logger.debug("No animated preview available at the moment for "+ str(self.username) + ". Retrying.")
                    conn.commit()
            else:
                logger.error("HTTP error, trying again in " + str(self.refresh) + " seconds.")
        else:
            logger.debug("No new VODs, checking again in " + str(self.refresh) + " seconds.")

    def loopcheck(self):
        logger.info("Checking " + str(self.username) + " (" + str(self.user_id) + ")" + " every " + str(self.refresh) + " seconds. Get links with " + str(self.quality) + " quality.")
        while True:
            status = self.check_online()
            if status == 2:
                logger.error("Username not found. Invalid username or typo.")
                time.sleep(self.refresh)
            elif status == 3:
                logger.error("Unexpected error.")
                time.sleep(self.refresh)
            elif status == 1:
                logger.debug(str(self.username) + " currently offline, checking again in " + str(self.refresh) + " seconds.")
                time.sleep(self.refresh)
            elif status == 0:
                logger.debug(str(self.username)+" online. Fetching vods.")
                
                # start streamlink process
                self.vodchecker()

                #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                time.sleep(self.refresh)

class launcher():
    def __init__(self, refreshtime):
        self.refresh = refreshtime
        self.threads = []

    def run(self):
        # make sure the interval to check user availability is not less than 15 seconds
        if(self.refresh < 15):
            logger.warning("Check interval should not be lower than 15 seconds.")
            self.refresh = 15
            logger.warning("System set check interval to 15 seconds.")
        with open("stream_list.json") as f:
            stream_list = json.load(f)
        username_str = ""
        i=0
        for stream in stream_list['list']:
            i+=1
        i_max = i
        i=0
        for stream in stream_list['list']:
            i+=1
            if i==i_max:
                username_str = username_str + stream['username']
            else:
                username_str = username_str + stream['username'] + ", "
        logger.info("Checking " + str(username_str) + " every " + str(self.refresh) + " seconds.")
        i=1
        for stream in stream_list['list']:
            thread = vodthread(stream['username'], stream['quality'], stream['subonly'], self.refresh)
            thread.daemon = True
            thread.name =  str(i)+"-"+ stream['username'] + "-thread"
            self.threads.append(thread)
            i+=1
            thread.start()
            time.sleep(2)
        while True:
            time.sleep(1)
            for t in self.threads:
                if t.is_alive() != True:
                    n_in_list = t.name[:1]
                    n_in_list = int(n_in_list) - 1
                    thread = vodthread(stream_list['list'][n_in_list]['username'], stream_list['list'][n_in_list]['quality'], stream_list['list'][n_in_list]['subonly'], self.refresh)
                    thread.daemon = True
                    thread.name = t.name
                    self.threads.append(thread)
                    logger.warning("Thread "+t.name+" has crashed unexpectedly. Relaunching.")
                    thread.start()
                    
def main(argv):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--genmuted", "-gm", help="Generates an m3u8 playlist, replacing links to dead .ts files with their muted counterparts. Useful for subonly vods.", type=str)
    group.add_argument("--crawl", "-c", help="Fetches vods every couple of seconds from a list of streamers and pastes them into a sqlite db. Default refresh time is 60 seconds.", nargs='?',type=int, const=60)
    parser.add_argument("--verbose", "-v", help="Changes logging to verbose.", action="store_true")
    group.add_argument("--single", "-s", help="Fetches vods once for a specific streamer and pastes them into a textfile.", type=str)
    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()
    if args.crawl:
        if args.verbose:
            consoleHandler.setLevel(logging.DEBUG)
            fileHandler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            consoleHandler.setLevel(logging.INFO)
            fileHandler.setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
        logger.info("Launching crawl mode.")
        global streaml
        streaml = streamlink.Streamlink()
        twitch_launcher = launcher(args.crawl)
        twitch_launcher.run()
    if args.single:
        if args.verbose:
            consoleHandler.setLevel(logging.DEBUG)
            fileHandler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            consoleHandler.setLevel(logging.INFO)
            fileHandler.setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
        logger.info("Launching single mode.")
        twitch_launcher = gensingle(args.single)
        twitch_launcher.run()
    if args.genmuted:
        if args.verbose:
            consoleHandler.setLevel(logging.DEBUG)
            fileHandler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            consoleHandler.setLevel(logging.INFO)
            fileHandler.setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
        logger.info("Launching genmuted mode.")
        twitch_launcher = genmuted(args.genmuted)
        twitch_launcher.run()

if __name__ == "__main__":
    main(sys.argv[1:])