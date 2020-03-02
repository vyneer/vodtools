# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import gspread
import os
import sqlite3
import pathlib
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import requests
import time
import json
import sys
import datetime
import threading
import argparse
import m3u8
import re
import logging

logger = logging.getLogger(__name__)
logformat = logging.Formatter('[%(levelname)s][%(threadName)s][%(asctime)s] %(message)s')

fileHandler = logging.FileHandler("vodtools.log")
fileHandler.setFormatter(logformat)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logformat)
logger.addHandler(consoleHandler)

class ttvfunctions():
    def check_online(self, user_id, client_id, oauth_token):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/kraken/streams/' + user_id
        info = None
        status = 3
        try:
            r = requests.get(url, headers = {"Accept" : "application/vnd.twitchtv.v5+json", "Client-ID" : client_id, "Authorization" : "OAuth " + oauth_token}, timeout = 15)
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
    
    def find_anipreview(self, vod_id, client_id):
        url = 'https://api.twitch.tv/kraken/videos/' + vod_id
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info['animated_preview_url'] != [] or None:
                result = re.findall(r"(?<=\/)[^\/]+(?=\/)", info['animated_preview_url'])
                if result[1] != info['channel']['name']:
                    return result[1]
                else:
                    return ""
            else:
                return ""
        except requests.exceptions.RequestException as e:
            logger.debug("Error in find_anipreview: " + str(e))

    def get_id(self, username, client_id, oauth_token):
        url = 'https://api.twitch.tv/helix/users?login=' + username
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : client_id, "Authorization" : "Bearer " + oauth_token}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if info['data'] != [] or None:
                    logger.debug("Got userid from username - "+info["data"][0]["id"])
                    return info["data"][0]["id"]
            else:
                return None
        except requests.exceptions.RequestException as e:
            logger.debug("Error in get_id: " + str(e))

    def check_videos(self, user_id, client_id, oauth_token):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/helix/videos?user_id=' + user_id + "&first=100"
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : client_id, "Authorization" : "Bearer " + oauth_token}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info

    def get_m3u8(self, info, count, quality, client_id):
        secreturl = ttvfunctions().find_anipreview(info['data'][count]['id'], client_id)
        if secreturl != "" or None:
            if quality != "chunked":
                fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/" + quality + "/index-dvr.m3u8"
                if requests.head(fullurl).status_code == 403:
                    fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
            else:
                fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
            logger.debug("Found link "+ fullurl)
            if info['data'][count]['type'] == 'archive':
                values = [info['data'][count]['created_at'], info['data'][count]['title'], info['data'][count]['url'], fullurl, quality]
                return fullurl, values
            else:
                return "notarchive", None
        else:
            return None, None

class gensingle():
    def __init__(self, username):
        with open("settings.json") as f:
            stream_list = json.load(f)
        self.client_id = stream_list['client_id']
        self.oauth = stream_list['oauth_token']
        
        # user configuration
        self.username = username
        self.user_id = None
        self.user_id = ttvfunctions().get_id(self.username, self.client_id, self.oauth)

    def run(self):
        status, info = ttvfunctions().check_videos(self.user_id, self.client_id, self.oauth)
        if info != None and info['data'] != []:
            if status == 0:
                with open(datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")+"_"+self.username + ".txt", "wb") as memefile:
                    for x in range(len(info['data'])-1, -1, -1):
                        fullurl, values = ttvfunctions().get_m3u8(info, x, "chunked", self.client_id)
                        if fullurl != None and fullurl != "notarchive":
                            values_str = u' - '.join((values[0], values[1], values[2], fullurl, "\n")).encode('utf-8')
                            memefile.write(values_str)
                            logger.info("Added " + str(self.username) + "'s chunked VOD "+ info['data'][x]['url'] + " to the text file.")
                        elif fullurl == "notarchive":
                            logger.debug(info['data'][x]['url'] + " - VOD's type differs from 'archive'.")
                        else:
                            logger.debug("No animated preview available at the moment for "+ str(self.username) + "'s VOD - " + info['data'][x]['url'] + ".")
            else:
                 logger.error("HTTP error.")
                
class sheetmaker():
    def __init__(self, makesheet, gspread_client):
        self.client = gspread_client
        self.sheetname=makesheet[0]+" m3u8 VOD links"
        self.shareemail=makesheet[1]
        
    def run(self):
        kek = self.client.create(self.sheetname)
        kek.share(self.shareemail, perm_type='user', role='writer')
        logger.info("Created the spreadsheet. Check your email for the URL.")
    
class genmuted():
    def __init__(self, url):
        self.url=url
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

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
        clean_url = self.url[:-14]

        regex1 = re.findall(r"(?<=\/)[^\/]+(?=\/)", clean_url)

        rel_path = "muted playlists"
        abs_file_path = os.path.join(self.script_dir, rel_path)
        orig_rel_path = "muted playlists\\" + regex1[1] + ".m3u8"
        orig_abs_file_path = os.path.join(self.script_dir, orig_rel_path)
        buf_rel_path = "muted playlists\\buffer.txt"
        buf_abs_file_path = os.path.join(self.script_dir, buf_rel_path)
        mut_rel_path = "muted playlists\\muted_" + regex1[1] + ".m3u8"
        mut_abs_file_path = os.path.join(self.script_dir, mut_rel_path)

        r = requests.get(self.url, stream=True)
        if os.path.exists(abs_file_path) == False:
            os.mkdir(abs_file_path)
        open(orig_abs_file_path, "wb").write(r.content)
        logger.info("Downloaded the original/broken m3u8 to /muted playlists/" + regex1[1] + ".m3u8.")

        tslinks = self.loadM3u8(self.url)
        i=0

        with open(buf_abs_file_path, "w") as f:
            logger.debug("Created the buffer text file.")
            for tsurl in tslinks['videoUrls']:
                i+=1
                r = requests.head(tsurl)
                if r.status_code == 403:
                    tsurl = tsurl[:-3] + "-muted.ts"
                    logger.info("Found the muted version of this .ts file - " + tsurl + ".")
                    f.writelines(tsurl+'\n')
                elif r.status_code == 200:
                    logger.info("Found the unmuted version of this .ts file - " + tsurl + ".")
                    f.writelines(tsurl+'\n')

        a=9

        lines = open(orig_abs_file_path).read().splitlines()
        with open(buf_abs_file_path, "r") as f:
            for line in f:
                lines[a]=line.rstrip()
                a+=2
        open(mut_abs_file_path, "w").write('\n'.join(lines))
        logger.info("Created the muted m3u8 file at \\" + mut_rel_path + ".")
        os.remove(orig_abs_file_path)
        logger.debug("Removed the original m3u8 file.")
        os.remove(buf_abs_file_path)
        logger.debug("Removed the buffer text file.")

class vodthread(threading.Thread):
    def __init__(self, username, quality, refreshtime, twitch_id, twitch_oauth, gspread_client, gsheets_url):
        threading.Thread.__init__(self)
        # global configuration
        self.client_id = twitch_id
        self.oauth = twitch_oauth
        self.refresh = refreshtime
        
        # user configuration
        self.username = username
        self.quality = quality
        self.gsheets_url = gsheets_url
        self.client = gspread_client
        self.old_status = 0

    def run(self):
        self.loopcheck()

    def vodcheckerSheets(self):
        try:
            sheet = self.client.open_by_url(self.gsheets_url).sheet1
            status, info = ttvfunctions().check_videos(self.user_id, self.client_id, self.oauth)
            self.client.login()
            if status == 0:
                if info != None and info['data'] != [] and sheet.findall(info['data'][0]['url']) == [] or None:
                    for x in range(len(info['data'])-1, -1, -1):
                        time.sleep(1.5)
                        fullurl, values = ttvfunctions().get_m3u8(info, x, self.quality, self.client_id)
                        if fullurl != None and fullurl != "notarchive":
                            if sheet.findall(fullurl) == []:
                                sheet.append_row(values)
                                logger.info("Added " + str(self.username) + "'s "+ self.quality + " VOD "+ info['data'][x]['url'] + " to the spreadsheet.")
                        elif fullurl == "notarchive":
                            logger.debug(info['data'][x]['url'] + " - VOD's type differs from 'archive'.")
                        else:
                            logger.debug("No animated preview available at the moment for "+ str(self.username) + "'s VOD - " + info['data'][x]['url'] + ". Retrying later.")
                else:
                    logger.debug("No new VODs, checking again in " + str(self.refresh) + " seconds.")
            else:
                logger.error("HTTP error, trying again in " + str(self.refresh) + " seconds.")
        except gspread.exceptions.APIError as e:
            logger.error("GSpread error: APIError. Code: " + str(e))
        except gspread.exceptions.GSpreadException as e:
            logger.error("GSpread error: GSpreadException. Code: " + str(e))

    def vodcheckerLocal(self):
        try:
            path = pathlib.Path("voddb.db")
            if path.exists() != True:
                conn = sqlite3.connect("voddb.db")
                cursor=conn.cursor()
                sql_cmd = '''CREATE TABLE {} (timecode text, title text, twitchurl text, vodurl text, type text)'''.format(self.username)
                cursor.execute(sql_cmd)
            conn = sqlite3.connect("voddb.db")
            cursor=conn.cursor()
            sql_cmd = ''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='{}' '''.format(self.username)
            cursor.execute(sql_cmd)
            if cursor.fetchone()[0] == 0:
                sql_cmd = '''CREATE TABLE {} (timecode text, title text, twitchurl text, vodurl text, type text)'''.format(self.username)
                cursor.execute(sql_cmd)
            status, info = ttvfunctions().check_videos(self.user_id, self.client_id, self.oauth)
            if status == 0:
                if info != None and info['data'] != []:
                    sql_cmd = '''SELECT * FROM {} WHERE twitchurl=?'''.format(self.username)
                    cursor.execute(sql_cmd, (info['data'][0]['url'],))
                    if cursor.fetchone() is None:
                        for x in range(len(info['data'])-1, -1, -1):
                            fullurl, values = ttvfunctions().get_m3u8(info, x, self.quality, self.client_id)
                            if fullurl != None and fullurl != "notarchive":
                                sql_cmd = '''SELECT * FROM {} WHERE vodurl=?'''.format(self.username)
                                cursor.execute(sql_cmd, (fullurl,))
                                if cursor.fetchone() is None:
                                    sql_cmd = '''INSERT INTO {} VALUES (?,?,?,?,?)'''.format(self.username)
                                    cursor.execute(sql_cmd, (values))
                                    logger.info("Added " + str(self.username) + "'s "+ self.quality +" VOD "+ info['data'][x]['url'] + " to the database.")
                            elif fullurl == "notarchive":
                                logger.debug(info['data'][x]['url'] + " - VOD's type differs from 'archive'.")
                            else:
                                logger.debug("No animated preview available at the moment for "+ str(self.username) + "'s VOD - " + info['data'][x]['url'] + ". Retrying later.")
                            conn.commit()
                    else:
                        logger.debug("No new VODs, checking again in " + str(self.refresh) + " seconds.")
                else:
                    logger.debug("No VODs exist, checking again in " + str(self.refresh) + " seconds.")
            else:
                logger.error("HTTP error, trying again in " + str(self.refresh) + " seconds.")
        except TypeError as e:
            logger.error("Caugth a TypeError in vodthread: " + str(e))

    def loopcheck(self):
        banned_bool = False
        if self.gsheets_url:
            logger.info("Checking " + str(self.username) +  " every " + str(self.refresh) + " seconds. Adding links with " + str(self.quality) + " quality to the Google Spreadsheet.")
        else:
            logger.info("Checking " + str(self.username) +  " every " + str(self.refresh) + " seconds. Adding links with " + str(self.quality) + " quality to the local SQLite database.")
        while True:
            self.user_id = ttvfunctions().get_id(self.username, self.client_id, self.oauth)
            if self.user_id == None:
                if banned_bool == False:
                    logger.error("No ID found: check if " + self.username + " got banned.")
                banned_bool = True
                time.sleep(self.refresh)
            else:
                banned_bool = False
                status = ttvfunctions().check_online(self.user_id, self.client_id, self.oauth)
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
                    logger.debug(str(self.username)+" online. Fetching VODs.")
                    
                    # start streamlink process
                    if self.gsheets_url:
                        self.client.login()
                        self.vodcheckerSheets()
                    else:
                        self.vodcheckerLocal()

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)

class launcher():
    def __init__(self):
        self.scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        self.threads = []

    def run(self):
        with open("settings.json") as f:
            stream_list = json.load(f)
        i=0
        for stream in stream_list['list']:
            if stream['gsheets'] != "":
                i+=1
        if i>0:
            if pathlib.Path("client_secret.json").exists():
                creds = ServiceAccountCredentials.from_json_keyfile_name("client_secret.json", self.scope)
                client = gspread.authorize(creds)
            else:
                logger.error("No client_secret.json file in the directory.")
                sys.exit(0)
        username_str = ""
        i=0
        for stream in stream_list['list']:
            i+=1
        i_max = i
        i=0
        for stream in stream_list['list']:
            if not stream['refreshtime']:
                refreshtime = 60
            else:
                refreshtime = stream['refreshtime']
            i+=1
            if i==i_max:
                if stream['gsheets']:
                    username_str = username_str + stream['username'] + " (gs) " + "(" + str(refreshtime) + "s)"
                else:
                    username_str = username_str + stream['username'] + " (db) " + "(" + str(refreshtime) + "s)"
            else:
                if stream['gsheets']:
                    username_str = username_str + stream['username'] + " (gs) " + "(" + str(refreshtime) + "s), "
                else:
                    username_str = username_str + stream['username'] + " (db) " + "(" + str(refreshtime) + "s), "
        logger.info("Getting m3u8 links for: " + str(username_str))
        i=1
        for stream in stream_list['list']:
            if not stream['refreshtime']:
                refreshtime = 60
            else:
                refreshtime = stream['refreshtime']
            if int(refreshtime) < 15:
                logger.error("Refresh time < 15 not allowed.")
                sys.exit(0)
            if stream['gsheets']:
                thread = vodthread(stream['username'], stream['quality'], int(refreshtime), stream_list['client_id'], stream_list['oauth_token'], client, stream['gsheets'])                    
                thread.name =  str(i)+"-"+ stream['username'] + "-gs-thread"
            else:
                thread = vodthread(stream['username'], stream['quality'], int(refreshtime), stream_list['client_id'], stream_list['oauth_token'], None, None)              
                thread.name =  str(i)+"-"+ stream['username'] + "-db-thread"
            thread.daemon = True
            self.threads.append(thread)
            i+=1
            thread.start()
            time.sleep(2)
        while True:
            time.sleep(1)
            for t in self.threads:
                if t.is_alive() != True:
                    match = re.findall(r"^\d+", t.name)
                    n_in_list = int(match[0]) - 1
                    if stream_list['list'][n_in_list]['gsheets']:
                        thread = vodthread(stream_list['list'][n_in_list]['username'], stream_list['list'][n_in_list]['quality'], stream_list['list'][n_in_list]['refreshtime'], stream_list['list'][n_in_list]['client_id'], stream_list['list'][n_in_list]['oauth_token'], client, stream_list['list'][n_in_list]['gsheets'])
                    else:
                        thread = vodthread(stream_list['list'][n_in_list]['username'], stream_list['list'][n_in_list]['quality'], stream_list['list'][n_in_list]['refreshtime'], stream_list['list'][n_in_list]['client_id'], stream_list['list'][n_in_list]['oauth_token'], None, None)
                    thread.daemon = True
                    thread.name = t.name
                    self.threads.append(thread)
                    logger.error("Thread "+t.name+" has crashed unexpectedly. Relaunching.")
                    thread.start()
                    
def main(argv):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--genmuted", "-gm", help="Generates an m3u8 playlist, replacing links to dead .ts files with their muted counterparts. Useful for subonly vods.", type=str)
    group.add_argument("--crawl", "-c", help="Fetches vods every couple of seconds from a list of streamers and pastes them into a google spreadsheet.", action="store_true")
    group.add_argument("--single", "-s", help="Fetches vods once for a specific streamer and pastes them into a textfile.", type=str)
    group.add_argument("--makesheet", "-ms", nargs=2, metavar=('SHEET_NAME','SHARE_EMAIL'), help="Creates and shares a spreadsheet.", type=str)
    parser.add_argument("--verbose", "-v", help="Changes logging to verbose.", action="store_true")
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()
    if args.makesheet:
        if args.verbose:
            consoleHandler.setLevel(logging.DEBUG)
            fileHandler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            consoleHandler.setLevel(logging.INFO)
            fileHandler.setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
        logger.info("Launching makesheet mode.")
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        if pathlib.Path("client_secret.json").exists():
            creds = ServiceAccountCredentials.from_json_keyfile_name("client_secret.json", scope)
            client = gspread.authorize(creds)
            twitch_launcher = sheetmaker(args.makesheet, client)
            twitch_launcher.run()
        else:
            logger.error("No client_secret.json file in the directory.")
            sys.exit(0)
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
        twitch_launcher = launcher()
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