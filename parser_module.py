# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import gspread
import streamlink
import m3u8
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

streaml = streamlink.Streamlink()
scope = ["https://spreadsheets.google.com/feeds"]
creds = ServiceAccountCredentials.from_json_keyfile_name("client_secret.json", scope)
client = gspread.authorize(creds)

sheet = client.open_by_url(config.doc_url).sheet1

class twitchvodparser:
    def __init__(self):
        # global configuration
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        self.refresh = config.refresh_time

        # user configuration
        self.userid = ""
        self.quality = ""
        self.subonly = False
        streaml.set_plugin_option("twitch", "twitch_oauth_token", self.oauth_token)

    def run(self, mode=0):
        # make sure the interval to check user availability is not less than 15 seconds
        if(self.refresh < 15):
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Check interval should not be lower than 15 seconds.")
            self.refresh = 15
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"System set check interval to 15 seconds.")

        info = self.check_user()[1]
        client.login()
        try:
            if info['data'] != [] and sheet.findall(info['data'][0]['url']) == [] or None:
                self.loopcheck(mode=mode)
            else:
                if mode == 1:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] No new VODs, checking again in " + str(self.refresh) + " seconds.")
        except gspread.exceptions.APIError as e:
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] GSpread error: The service is currently unavailable.")

    def check_user(self):
        # 0: online, 
        # 1: offline, 
        # 2: not found, 
        # 3: error
        url = 'https://api.twitch.tv/helix/videos?user_id=' + self.userid
        info = None
        try:
            r = requests.get(url, headers = {"Client-ID" : self.client_id}, timeout = 15)
            r.raise_for_status()
            info = r.json()
            status = 0
        except requests.exceptions.RequestException:
            status = 1

        return status, info

    def loopcheck(self, mode=0):
        status, info = self.check_user()
        client.login()
        if status == 0:
            for x in range(len(info['data'])-1, -1, -1):
                memesquality = self.quality
                m3u8check = False
                time.sleep(1.5)
                if self.subonly == False:
                    try:
                        streams = streaml.streams(info['data'][x]['url'])
                    except streamlink.exceptions.PluginError:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Streamlink error.")
                    if memesquality not in streams:
                        memesquality = "best"
                    if sheet.findall(streams[memesquality].url) == []:
                        m3u8check = True
                    if mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Found link "+ streams[memesquality].url)
                    if m3u8check and "muted" not in streams[memesquality].url and info['data'][x]['type'] == 'archive':
                        values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[memesquality].url, 'clean']
                        sheet.append_row(values)
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Added clean VOD "+ info['data'][x]['url'] + " to the list.")
                    if m3u8check and "muted" in streams[memesquality].url and info['data'][x]['type'] == 'archive':
                        values = [info['data'][x]['created_at'], info['data'][x]['title'], info['data'][x]['url'], streams[memesquality].url, 'muted']
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
                    
def main(argv):
    twitch_vod_parser = twitchvodparser()
    twitch_vod_parser.run()

if __name__ == "__main__":
    main(sys.argv[1:])
