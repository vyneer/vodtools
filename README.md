# vodtools
twitch vod tool suite written in python

## Why?

1. It's a fun project!
2. I like archiving things.
3. While big streamers usually have people that download/link deleted vods manually, smaller streamers don't, so I wanted to automate the process.

## How to install

Either do ```git clone https://github.com/vyneer/vodtools``` or download the zipped version, 
install the dependencies using ```pip3 install -r req.txt``` and you're done!

Don't forget to edit the settings.json file with channels, your Client ID and OAuth token.
If you're going to be pasting the VOD data into a Google Spreadsheet, you need to get a client_secret.json file.

## Twitch Client ID and OAuth token setup

Since [May 1st 2020 Twitch](https://discuss.dev.twitch.tv/t/requiring-oauth-for-helix-twitch-api-endpoints/23916) 
requires OAuth for all their Helix API calls. Here's how you can get one:

1. Go to this page on [Twitch's dev website](https://dev.twitch.tv/dashboard/apps/create).

2. Name it whatever you want, set OAuth Redirect URL to http://localhost, category is whatever.

3. Select "Manage" next to your app on the next page.

4. Copy your Client ID and paste it both into your settings.json and into this URL - https://id.twitch.tv/oauth2/authorize?response_type=token&client_id=CLIENTID&redirect_uri=http://localhost&scope= (replace the CLIENTID, of course).

5. Open the URL, login. In your address bar there should be a URL with your access (OAuth) token.

## Google Sheets API / client_secret.json

I'm too lazy to type out a whole guide for that (since I don't remember how to do it), but you can get info in this video - https://www.youtube.com/watch?v=vISRn5qFrkM.

## Features

### -c, --crawl

```python3 vodtools.py -c```

Continuosly fetches links to .m3u8 files and pastes them into either a local SQLite database or to a Google Spreadsheet.
Setup the list of channels in settings.json. Username and quality are required parameters, refreshtime is optional (default is 60 sec.).
Paste the Google Spreadsheet URL into the gsheets parameter to paste the data into, well, a Google Spreadsheet.

### -s <user_name>, --single <user_name>

```python3 vodtools.py -s destiny```

Fetches all vods once for a specific streamer and pastes them into a .txt file.

### -gm <m3u8_url>, --genmuted <m3u8_url>

```python3 vodtools.py -gm http://thedankestmeme.com/foobar.m3u8```

Downloads the .m3u8 file and replaces (dead) links to unmuted fragments with (alive) links to muted fragments. 
Useful in case of a muted deleted VOD. Also, it takes awhile to go through the file.

### -ms <sheet_name> <share_email>, --makesheet <sheet_name> <share_email>

```python3 vodtools.py -ms xqc foo@bar.gg```

Creates a Google Spreadsheet and sends an invite to the email you specified.

### -v, --verbose

```
python3 vodtools.py -vc
python3 vodtools.py -vs destiny
python3 vodtools.py -vgm http://thedankestmeme.com/foobar.m3u8
python3 vodtools.py -vms xqc foo@bar.gg
```

Self-explainatory.

