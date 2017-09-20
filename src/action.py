# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Carry out voice commands by recognising keywords."""

import datetime
import logging
import subprocess
import vlc
import time
import feedparser
import random
import threading
import RPi.GPIO as gpio

import actionbase

# =============================================================================
#
# Hey, Makers!
#
# This file contains some examples of voice commands that are handled locally,
# right on your Raspberry Pi.
#
# Do you want to add a new voice command? Check out the instructions at:
# https://aiyprojects.withgoogle.com/voice/#makers-guide-3-3--create-a-new-voice-command-or-action
# (MagPi readers - watch out! You should switch to the instructions in the link
#  above, since there's a mistake in the MagPi instructions.)
#
# In order to make a new voice command, you need to do two things. First, make a
# new action where it says:
#   "Implement your own actions here"
# Secondly, add your new voice command to the actor near the bottom of the file,
# where it says:
#   "Add your own voice commands here"
#
# =============================================================================

# Actions might not use the user's command. pylint: disable=unused-argument


# Example: Say a simple response
# ================================
#
# This example will respond to the user by saying something. You choose what it
# says when you add the command below - look for SpeakAction at the bottom of
# the file.
#
# There are two functions:
# __init__ is called when the voice commands are configured, and stores
# information about how the action should work:
#   - self.say is a function that says some text aloud.
#   - self.words are the words to use as the response.
# run is called when the voice command is used. It gets the user's exact voice
# command as a parameter.

class SpeakAction(object):

    """Says the given text via TTS."""

    def __init__(self, say, words):
        self.say = say
        self.words = words

    def run(self, voice_command):
        self.say(self.words)


# Example: Tell the current time
# ==============================
#
# This example will tell the time aloud. The to_str function will turn the time
# into helpful text (for example, "It is twenty past four."). The run function
# uses to_str say it aloud.

class SpeakTime(object):

    """Says the current local time with TTS."""

    def __init__(self, say):
        self.say = say

    def run(self, voice_command):
        time_str = self.to_str(datetime.datetime.now())
        self.say(time_str)

    def to_str(self, dt):
        """Convert a datetime to a human-readable string."""
        HRS_TEXT = ['midnight', 'one', 'two', 'three', 'four', 'five', 'six',
                    'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
        MINS_TEXT = ["five", "ten", "quarter", "twenty", "twenty-five", "half"]
        hour = dt.hour
        minute = dt.minute

        # convert to units of five minutes to the nearest hour
        minute_rounded = (minute + 2) // 5
        minute_is_inverted = minute_rounded > 6
        if minute_is_inverted:
            minute_rounded = 12 - minute_rounded
            hour = (hour + 1) % 24

        # convert time from 24-hour to 12-hour
        if hour > 12:
            hour -= 12

        if minute_rounded == 0:
            if hour == 0:
                return 'It is midnight.'
            return "It is %s o'clock." % HRS_TEXT[hour]

        if minute_is_inverted:
            return 'It is %s to %s.' % (MINS_TEXT[minute_rounded - 1], HRS_TEXT[hour])
        return 'It is %s past %s.' % (MINS_TEXT[minute_rounded - 1], HRS_TEXT[hour])


# Example: Run a shell command and say its output
# ===============================================
#
# This example will use a shell command to work out what to say. You choose the
# shell command when you add the voice command below - look for the example
# below where it says the IP address of the Raspberry Pi.

class SpeakShellCommandOutput(object):

    """Speaks out the output of a shell command."""

    def __init__(self, say, shell_command, failure_text):
        self.say = say
        self.shell_command = shell_command
        self.failure_text = failure_text

    def run(self, voice_command):
        output = subprocess.check_output(self.shell_command, shell=True).strip()
        if output:
            self.say(output)
        elif self.failure_text:
            self.say(self.failure_text)


# Example: Change the volume
# ==========================
#
# This example will can change the speaker volume of the Raspberry Pi. It uses
# the shell command SET_VOLUME to change the volume, and then GET_VOLUME gets
# the new volume. The example says the new volume aloud after changing the
# volume.

class VolumeControl(object):

    """Changes the volume and says the new level."""

    GET_VOLUME = r'amixer get Master | grep "Front Left:" | sed "s/.*\[\([0-9]\+\)%\].*/\1/"'
    SET_VOLUME = 'amixer -q set Master %d%%'

    def __init__(self, say, change):
        self.say = say
        self.change = change

    def run(self, voice_command):
        res = subprocess.check_output(VolumeControl.GET_VOLUME, shell=True).strip()
        try:
            logging.info("volume: %s", res)
            vol = int(res) + self.change
            vol = max(0, min(100, vol))
            subprocess.call(VolumeControl.SET_VOLUME % vol, shell=True)
            self.say(_('Volume at %d %%.') % vol)
        except (ValueError, subprocess.CalledProcessError):
            logging.exception("Error using amixer to adjust volume.")


# Example: Repeat after me
# ========================
#
# This example will repeat what the user said. It shows how you can access what
# the user said, and change what you do or how you respond.

class RepeatAfterMe(object):

    """Repeats the user's command."""

    def __init__(self, say, keyword):
        self.say = say
        self.keyword = keyword

    def run(self, voice_command):
        # The command still has the 'repeat after me' keyword, so we need to
        # remove it before saying whatever is left.
        to_repeat = voice_command.replace(self.keyword, '', 1)
        self.say(to_repeat)


# Power: Shutdown or reboot the pi
# ================================
# Shuts down the pi or reboots with a response
#

class PowerCommand(object):
    """Shutdown or reboot the pi"""

    def __init__(self, say, command):
        self.say = say
        self.command = command

    def run(self, voice_command):
        if self.command == "shutdown":
            self.say("Shutting down, goodbye")
            subprocess.call("sudo shutdown now", shell=True)
        elif self.command == "reboot":
            self.say("Rebooting")
            subprocess.call("sudo shutdown -r now", shell=True)
        else:
            logging.error("Error identifying power command.")
            self.say("Sorry I didn't identify that command")


# Power: Play Podcast
# ================================
# Plays, pauses and resumes podcasts
#

class playPodcast(object):

    def __init__(self, say, keyword):
        self.say = say
        self.keyword = keyword
        self.instance = vlc.Instance()
        global podcastPlayer
        podcastPlayer = self.instance.media_player_new()
        self.set_state("stopped")

    def set_state(self, new_state):
        logging.info("setting podcast state " + new_state)
        global podcastState
        podcastState = new_state

    def get_state():
        return podcastState

    def get_url(self, podcast_name):
        # add the rss feeds for the podcasts
        urls = {
            'friday night comedy': 'http://www.bbc.co.uk/programmes/p02pc9pj/episodes/downloads.rss',
            'tech news today': 'http://feeds.twit.tv/tnt.xml',
            'twig': 'http://feeds.twit.tv/twig.xml',
            'this week in tech': 'http://feeds.twit.tv/twit.xml',
            'theory of everything': 'https://www.npr.org/rss/podcast.php?id=510061',
            'this american life': 'http://feed.thisamericanlife.org/talpodcast',
            'android authority': 'http://androidauthority.libsyn.com/rss',
            }
        return urls[podcast_name]

    def stop(self):
        podcastPlayer.stop()
        self.set_state("stopped")

    def wait_for_button(self):
        logging.info("waiting for button press to resume")
        gpio.setmode(gpio.BCM)
        gpio.setup(23, gpio.IN)
        while True:
            if gpio.input(23):
                self.stop()
                break
            time.sleep(0.1)

    def run(self, voice_command):

        voice_command = ((voice_command.lower()).replace(self.keyword, '', 1)).strip()

        logging.info("podcast command:" + voice_command)

        if (voice_command == "stop") or (voice_command == "off"):
            self.stop()
            return

        if voice_command == "pause":
            logging.info("podcast pausing")
            try:
                self.set_state("paused")
                #podcastPlayer.pause()
            except NameError:
                logging.info("error pausing")
                return
            return

        if voice_command == "resume":
            logging.info("podcast resuming")
            try:
                podcastPlayer.play()
                self.set_state("playing")
            except NameError:
                logging.info("error resuming")
                return
            return

        if "random" in voice_command:
            random_podcast = True
            voice_command = (voice_command.replace("random", '', 1)).strip()
        else:
            random_podcast = False

        self.set_state("stopped")
        global podcast_url
        podcast_url = None

        logging.info("looking for podcast: " + voice_command)

        try:
            feedUrl = self.get_url(voice_command)
        except KeyError:
            self.say("Sorry podcast not found")
            return
        logging.info("podcast feed: " + feedUrl)

        feed = feedparser.parse( feedUrl )

        if random_podcast:
            number_of_podcasts = len(feed['entries'])
            logging.info("podcast feed length: " + str(number_of_podcasts))
            podcast_number = random.randint(0,number_of_podcasts)
        else:
            podcast_number = 0


        for link in feed.entries[podcast_number].links:
            href = link.href
            if ".mp3" in href:
                podcast_url = href
                break

        logging.info("podcast url: " + podcast_url)

        media = self.instance.media_new(podcast_url)
        podcastPlayer.set_media(media)
        podcastPlayer.play()
        time.sleep(1)
        playing = set([1,2,3,4])
        state = podcastPlayer.get_state()
        self.set_state("starting")
        if state not in playing:
           logging.info("error playing podcast " + podcast_url)
           self.say("Sorry error playing " + podcast)
           self.set_state("stopped")
        self.set_state("playing")

        # Uncomment the following line if you want to use a voice trigger to start the radio and the button to stop it, radio will not pause and resume
        # self.wait_for_button()

    def pause():
        podcastState = playPodcast.get_state()
        logging.info("pausing podcast state is " + podcastState)
        if podcastState == "playing":
            try:
                podcastPlayer.pause()
            except NameError:
                return

    def resume():
        podcastState = playPodcast.get_state()
        logging.info("resume podcast state is " + podcastState)
        if podcastState == "playing":
            podcastPlayer.play()


# =========================================
# Makers! Implement your own actions here.
# =========================================


def make_actor(say):
    """Create an actor to carry out the user's commands."""

    actor = actionbase.Actor()

    actor.add_keyword(
        _('ip address'), SpeakShellCommandOutput(
            say, "ip -4 route get 1 | head -1 | cut -d' ' -f8",
            _('I do not have an ip address assigned to me.')))

    actor.add_keyword(_('volume up'), VolumeControl(say, 10))
    actor.add_keyword(_('volume down'), VolumeControl(say, -10))
    actor.add_keyword(_('max volume'), VolumeControl(say, 100))

    actor.add_keyword(_('repeat after me'),
                      RepeatAfterMe(say, _('repeat after me')))

# =========================================
# Makers! Add your own voice commands here.
# =========================================

    actor.add_keyword(_('power off'), PowerCommand(say, 'shutdown'))
    actor.add_keyword(_('reboot'), PowerCommand(say, 'reboot'))
    actor.add_keyword(_('podcast'), playPodcast(say, _('podcast')))

    return actor


def add_commands_just_for_cloud_speech_api(actor, say):
    """Add simple commands that are only used with the Cloud Speech API."""
    def simple_command(keyword, response):
        actor.add_keyword(keyword, SpeakAction(say, response))

    simple_command('alexa', _("We've been friends since we were both starter projects"))
    simple_command(
        'beatbox',
        'pv zk pv pv zk pv zk kz zk pv pv pv zk pv zk zk pzk pzk pvzkpkzvpvzk kkkkkk bsch')
    simple_command(_('clap'), _('clap clap'))
    simple_command('google home', _('She taught me everything I know.'))
    simple_command(_('hello'), _('hello to you too'))
    simple_command(_('tell me a joke'),
                   _('What do you call an alligator in a vest? An investigator.'))
    simple_command(_('three laws of robotics'),
                   _("""The laws of robotics are
0: A robot may not injure a human being or, through inaction, allow a human
being to come to harm.
1: A robot must obey orders given it by human beings except where such orders
would conflict with the First Law.
2: A robot must protect its own existence as long as such protection does not
conflict with the First or Second Law."""))
    simple_command(_('where are you from'), _("A galaxy far, far, just kidding. I'm from Seattle."))
    simple_command(_('your name'), _('A machine has no name'))

    actor.add_keyword(_('time'), SpeakTime(say))


# =========================================
# Makers! Add commands to pause and resume your actions here
# =========================================

def pauseActors():
    """add your pause actions here"""
    playPodcast.pause()

def resumeActors():
    """add your resume actions here"""
    playPodcast.resume()
