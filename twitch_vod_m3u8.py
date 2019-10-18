# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import parser_module
import gspread
import streamlink
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import requests
import os
import time
import json
import sys
import subprocess
import datetime
import getopt
import config
import client_twitch_oauth
import threading

streaml = streamlink.Streamlink()
scope = ["https://spreadsheets.google.com/feeds"]
creds = ServiceAccountCredentials.from_json_keyfile_name("client_secret.json", scope)

class launcher:
    def __init__(self):
        # global configuration
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        self.refresh = config.refresh_time
        
        # user configuration
        self.mode = config.debug_mode
        self.old_status = 0
        streaml.set_plugin_option("twitch", "twitch_oauth_token", self.oauth_token)

    def run(self):
        # make sure the interval to check user availability is not less than 15 seconds
        if(self.refresh < 15):
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Check interval should not be lower than 15 seconds.")
            self.refresh = 15
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"System set check interval to 15 seconds.")
        with open("stream_list.json") as f:
            stream_list = json.load(f)
        username_str = ""
        for stream in stream_list['list']:
            username_str = username_str + stream['username'] + "/"
        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking for " + str(username_str) + " every " + str(self.refresh) + " seconds.")
        for stream in stream_list['list']:
            test = threading.Thread(target=self.loopcheck, args=(stream['username'], stream['quality'], stream['subonly'], stream['gsheets'],))
            test.start()

    def check_online(self, username):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/kraken/streams/' + username
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

    def check_vods(self, user_id):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/helix/videos?user_id=' + user_id
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info

    def get_id(self, username):
        url = 'https://api.twitch.tv/helix/users?login=' + username
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            if self.mode == 1:
                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Got userid from username - "+info["data"][0]["id"])
        except requests.exceptions.RequestException as e:
            if self.mode == 1:
                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Error in get_id.")
        
        return info["data"][0]["id"]

    '''def vodchecker(self, mode, user_id, quality, subonly, sheet):
        status, info = self.check_vods(user_id)
        client.login()
        try:
            if info['data'] != [] and sheet.findall(info['data'][0]['url']) == [] or None:
                if status == 0:
                    for x in range(len(info['data'])-1, -1, -1):
                        m3u8check = False
                        time.sleep(1.5)
                        if subonly == False:
                            try:
                                streams = streaml.streams(info['data'][x]['url'])
                            except streamlink.exceptions.PluginError:
                                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Streamlink error.")
                            if quality not in streams:
                                quality = "best"
                            if sheet.findall(streams[quality].url) == []:
                                m3u8check = True
                            if mode == 1:
                                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Found link "+ streams[quality].url)
                            if m3u8check and "muted" not in streams[quality].url and info['data'][x]['type'] == 'archive':
                                values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[quality].url, 'clean']
                                sheet.append_row(values)
                                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added clean VOD "+ info['data'][x]['url'] + " to the list.")
                            if m3u8check and "muted" in streams[quality].url and info['data'][x]['type'] == 'archive':
                                values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[quality].url, 'muted']
                                sheet.append_row(values)
                                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added muted VOD "+ info['data'][x]['url'] + " to the list.")
                        else:
                            secreturl = info['data'][x]['thumbnail_url'][37:88]
                            if secreturl != "":
                                fullurl = "https://vod-secure.twitch.tv/" + secreturl + "/chunked/index-dvr.m3u8"
                                if sheet.findall(fullurl) == []:
                                    m3u8check = True
                                if mode == 1:
                                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Found link "+ fullurl)
                                if m3u8check and info['data'][x]['type'] == 'archive':
                                    values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], fullurl, 'subonly']
                                    sheet.append_row(values)
                                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added subonly VOD "+ info['data'][x]['url'] + " to the list.")
                            else:
                                if mode==1:
                                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"No thumbnail available at the moment. Retrying.")

                else:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] HTTP error, trying again in " + str(self.refresh) + " seconds.")
            else:
                if mode == 1:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] No new VODs, checking again in " + str(self.refresh) + " seconds.")
        except gspread.exceptions.APIError as e:
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] GSpread error: The service is currently unavailable.")
'''

    def loopcheck(self, username, quality, subonly, gsheets_url):
        vodchecker = parser_module.twitchvodparser()
        user_id = self.get_id(username)
        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking " + str(user_id) + " every " + str(self.refresh) + " seconds. Get links with " + str(quality) + " quality.")
        while True:
            status = self.check_online(username)
            if subonly == False:
                if status == 2:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Username not found. Invalid username or typo.")
                    time.sleep(self.refresh)
                elif status == 3:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Unexpected error.")
                    time.sleep(self.refresh)
                elif status == 1:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(username) + " currently offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 0:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(username)+" online. Fetching vods.")
                
                    # start streamlink process
                    vodchecker.run(mode=self.mode, user_id=user_id, quality=quality, subonly=subonly, gsheets_url=gsheets_url)

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)
            else:
                if status == 2:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Username not found. Invalid username or typo.")
                    time.sleep(self.refresh)
                elif status == 3:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Unexpected error.")
                    time.sleep(self.refresh)
                elif status == 0:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(username) + " currently online, checking again in " + str(self.refresh) + " seconds.")
                    self.old_status = status
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 1:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(username) + " is still offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 0:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(username)+" went offline. Fetching vods.")
                
                    # start streamlink process
                    vodchecker.run(mode=self.mode, user_id=user_id, quality=quality, subonly=subonly, gsheets_url=gsheets_url)
                    self.old_status = status

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)

    
                    
def main(argv):
    twitch_launcher = launcher()
    twitch_launcher.run()

if __name__ == "__main__":
    main(sys.argv[1:])