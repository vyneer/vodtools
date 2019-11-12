# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

#import parser_module
import gspread
import streamlink
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import requests
import time
import json
import sys
import datetime
import config
import client_twitch_oauth
import threading
import argparse
import m3u8

streaml = streamlink.Streamlink()
scope = ["https://spreadsheets.google.com/feeds"]
creds = ServiceAccountCredentials.from_json_keyfile_name("client_secret.json", scope)
client = gspread.authorize(creds)

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
    def __init__(self, username, quality, subonly, gsheets_url):
        threading.Thread.__init__(self)
        # global configuration
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        self.refresh = config.refresh_time
        
        # user configuration
        self.username = username
        self.quality = quality
        self.subonly = subonly
        self.gsheets_url = gsheets_url
        self.mode = config.debug_mode
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
        url = 'https://api.twitch.tv/helix/videos?user_id=' + self.user_id
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info  

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
                if self.mode == 1:
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Got userid from username - "+info["data"][0]["id"])
            else:
                return None
        except requests.exceptions.RequestException:
            if self.mode == 1:
                print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Error in get_id.")
        
        return info["data"][0]["id"]

    def vodchecker(self):
        try:
            sheet = client.open_by_url(self.gsheets_url).sheet1
            status, info = self.check_videos()
            client.login()
            try:
                if info['data'] != [] and sheet.findall(info['data'][0]['url']) == [] or None:
                    if status == 0:
                        for x in range(len(info['data'])-1, -1, -1):
                            m3u8check = False
                            time.sleep(1.5)
                            if self.subonly == False:
                                try:
                                    streams = streaml.streams(info['data'][x]['url'])
                                    if self.quality not in streams:
                                        self.quality = "best"
                                    if sheet.findall(streams[self.quality].url) == []:
                                        m3u8check = True
                                    if self.mode == 1:
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Found link "+ streams[self.quality].url)
                                    if m3u8check and "muted" not in streams[self.quality].url and info['data'][x]['type'] == 'archive':
                                        values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[self.quality].url, 'clean']
                                        sheet.append_row(values)
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added " + str(self.username) + "'s clean VOD "+ info['data'][x]['url'] + " to the list.")
                                    if m3u8check and "muted" in streams[self.quality].url and info['data'][x]['type'] == 'archive':
                                        values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[self.quality].url, 'muted']
                                        sheet.append_row(values)
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added " + str(self.username) + "'s muted VOD "+ info['data'][x]['url'] + " to the list.")
                                except streamlink.exceptions.PluginError:
                                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Streamlink error.")
                            else:
                                secreturl = info['data'][x]['thumbnail_url'][37:88]
                                if secreturl != "":
                                    fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
                                    if sheet.findall(fullurl) == []:
                                        m3u8check = True
                                    if self.mode == 1:
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Found link "+ fullurl)
                                    if m3u8check and info['data'][x]['type'] == 'archive':
                                        values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], fullurl, 'subonly']
                                        sheet.append_row(values)
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added " + str(self.username) + "'s subonly VOD "+ info['data'][x]['url'] + " to the list.")
                                else:
                                    if self.mode==1:
                                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"No thumbnail available at the moment for "+ str(self.username) + ". Retrying.")
                        else:
                            print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] HTTP error, trying again in " + str(self.refresh) + " seconds.")
                else:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] No new VODs, checking again in " + str(self.refresh) + " seconds.")
            except gspread.exceptions.APIError as e:
                print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] GSpread error: The service is currently unavailable. Code: " + str(e))
        except gspread.exceptions.APIError as e:
            print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] GSpread error: The service is currently unavailable. Code: " + str(e))

    def loopcheck(self):
        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking " + str(self.username) + " (" + str(self.user_id) + ")" + " every " + str(self.refresh) + " seconds. Get links with " + str(self.quality) + " quality.")
        while True:
            status = self.check_online()
            if self.subonly == False:
                if status == 2:
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Username not found. Invalid username or typo.")
                    time.sleep(self.refresh)
                elif status == 3:
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Unexpected error.")
                    time.sleep(self.refresh)
                elif status == 1:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " currently offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 0:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username)+" online. Fetching vods.")
                
                    # start streamlink process
                    client.login()
                    self.vodchecker()

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)
            else:
                if status == 2:
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Username not found. Invalid username or typo.")
                    time.sleep(self.refresh)
                elif status == 3:
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Unexpected error.")
                    time.sleep(self.refresh)
                elif status == 0:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " currently online, checking again in " + str(self.refresh) + " seconds.")
                    self.old_status = status
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 1:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " is still offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 0:
                    if self.mode == 1:
                        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username)+" went offline. Fetching vods.")
                
                    # start streamlink process
                    client.login()
                    self.vodchecker()
                    self.old_status = status

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)

class launcher():
    def __init__(self):
        self.refresh = config.refresh_time
        self.mode = config.debug_mode
        self.threads = []

    def run(self):
        # make sure the interval to check user availability is not less than 15 seconds
        if(self.refresh < 15):
            print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Check interval should not be lower than 15 seconds.")
            self.refresh = 15
            print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"System set check interval to 15 seconds.")
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
        print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking " + str(username_str) + " every " + str(self.refresh) + " seconds.")
        i=1
        for stream in stream_list['list']:
            thread = vodthread(stream['username'], stream['quality'], stream['subonly'], stream['gsheets'])
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
                    thread = vodthread(stream_list['list'][n_in_list]['username'], stream_list['list'][n_in_list]['quality'], stream_list['list'][n_in_list]['subonly'], stream_list['list'][n_in_list]['gsheets'])
                    thread.daemon = True
                    thread.name = t.name
                    self.threads.append(thread)
                    print("["+threading.current_thread().name+"]"+"["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Thread "+t.name+" has crashed unexpectedly. Relaunching.")
                    thread.start()
                    
def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--genmuted", "-gm", help="Generates an m3u8 playlist, replacing links to dead .ts files with their muted counterparts. Useful for subonly vods.", type=str)
    parser.add_argument("--crawl", "-c", help="Fetches vods every couple of seconds from a list of streamers and pastes them into a google spreadsheet.", action="store_true")
    args = parser.parse_args()
    if args.crawl == True:
        twitch_launcher = launcher()
        twitch_launcher.run()
    if args.genmuted:
        twitch_launcher = genmuted(args.genmuted)
        twitch_launcher.run()

if __name__ == "__main__":
    main(sys.argv[1:])