# This code is based on tutorial by slicktechies modified as needed to use oauth token from Twitch.
# You can read more details at: https://www.junian.net/2017/01/how-to-record-twitch-streams.html
# original code is from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import parser_module
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

class launcher:
    def __init__(self):
        # global configuration
        self.client_id = "jzkbprff40iqj646a697cyrvl0zt2m6" # don't change this
        # get oauth token value by typing `streamlink --twitch-oauth-authenticate` in terminal
        self.oauth_token = client_twitch_oauth.token
        self.refresh = config.refresh_time
        
        # user configuration
        self.vodchecker = parser_module.twitchvodparser()
        self.username = config.streamer
        self.vodchecker.quality = config.quality
        self.vodchecker.subonly = config.subonly
        self.mode = config.debug_mode
        self.old_status = 0

    def run(self):
        # make sure the interval to check user availability is not less than 15 seconds
        if(self.refresh < 15):
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Check interval should not be lower than 15 seconds.")
            self.refresh = 15
            print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"System set check interval to 15 seconds.")
        
        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking for " + str(self.username) + " every " + str(self.refresh) + " seconds.")
        self.get_id()
        self.loopcheck()

    def check_user(self):
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
            if self.mode == 1:
                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] Got userid from username - "+info["data"][0]["id"])
            self.vodchecker.userid = info["data"][0]["id"]
        except requests.exceptions.RequestException:
            if self.mode == 1:
                print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Error in get_id.")


    def loopcheck(self):
        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Checking " + str(self.vodchecker.userid) + " every " + str(self.vodchecker.refresh) + " seconds. Get links with " + str(self.vodchecker.quality) + " quality.")
        while True:
            status = self.check_user()
            if self.vodchecker.subonly == False:
                if status == 2:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Username not found. Invalid username or typo.")
                    time.sleep(self.refresh)
                elif status == 3:
                    print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Unexpected error.")
                    time.sleep(self.refresh)
                elif status == 1:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " currently offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 0:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username)+" online. Fetching vods.")
                
                    # start streamlink process
                    self.vodchecker.run(mode=self.mode)

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
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " currently online, checking again in " + str(self.refresh) + " seconds.")
                    self.old_status = status
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 1:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username) + " is still offline, checking again in " + str(self.refresh) + " seconds.")
                    time.sleep(self.refresh)
                elif status == 1 and self.old_status == 0:
                    if self.mode == 1:
                        print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+str(self.username)+" went offline. Fetching vods.")
                
                    # start streamlink process
                    self.vodchecker.run(mode=self.mode)
                    self.old_status = status

                    #print("["+datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+"] "+"Done fetching.")
                    time.sleep(self.refresh)
                    
def main(argv):
    twitch_launcher = launcher()
    twitch_launcher.run()

if __name__ == "__main__":
    main(sys.argv[1:])