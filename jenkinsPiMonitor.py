from jenkinsapi.jenkins import Jenkins
from jenkinsapi.custom_exceptions import NoBuildData
from sense_hat import SenseHat
from evdev import InputDevice, list_devices, ecodes

import sys
import threading
import time
import copy
import datetime
import getopt
import ConfigParser

sense = SenseHat()
sense.clear([0,0,0])

viewURL = ""
username = ""
password = ""

msleep = lambda x: time.sleep(x / 1000.0)

def log(x):
     print datetime.datetime.now().isoformat(), x

class State:
    failed = 16
    unstable = 8
    stable = 4
    disabled = 2
    running = 1

class Colours:
    failed = [255,0,0] #red
    unstable = [255,192,0] #yellow
    stable = [0,255,0] #green


running_pulse_rate = 15000
min_brightness = 0.2
brightness_step = 0.05

overall_state = 0
brightness = 0.6

running_pulse_scale = 0.4

def screenupdate():
    while(True):
        running_pulse_delta = brightness - (brightness*running_pulse_scale)
        colourtouse = [0,0,0]
        if (overall_state & State.failed) == State.failed:
            colourtouse = copy.copy(Colours.failed)
        if (overall_state & State.unstable) == State.unstable:
           colourtouse = copy.copy(Colours.unstable)
        if(overall_state & State.stable) == State.stable:
           colourtouse = copy.copy(Colours.stable)
        #pulsate on build
        if(overall_state & State.running) == State.running:
            #calculate pulse brightness
            pulseBrightness = running_pulse_scale + ((((datetime.datetime.now().microsecond/1000) % running_pulse_rate)) * running_pulse_delta )/256
            #print "pulse brightness:",pulseBrightness
            for colour in xrange(len(colourtouse)):
                colourtouse[colour] = int(round(colourtouse[colour] * min(pulseBrightness,1)))

        for colour in xrange(len(colourtouse)):
            if colourtouse[colour] != 0:
                colourtouse[colour] = max(int(round(colourtouse[colour] * brightness)),int (round(min_brightness*255)))
        #print "setting colour:", colourtouse, "from state", overall_state
        sense.clear(colourtouse)
        msleep(50)


def get_current_state(job):
    if (not job.is_enabled()):
        return State.disabled
    try:
        lastcompletedbuildnum = job.get_last_completed_buildnumber()
    except NoBuildData:
        log ("NoBuildData:complete")
        return State.disabled
    try:
        if(lastcompletedbuildnum == job.get_last_stable_buildnumber()):
            return State.stable
    except NoBuildData:
        log ("NoBuildData:stable")
        pass
    try:
        if(lastcompletedbuildnum == job.get_last_failed_buildnumber()):
            return State.failed
    except NoBuildData:
        log ("NoBuildData:failed")
        pass
    try:
        if(lastcompletedbuildnum == job.get_last_good_buildnumber()):
            return State.unstable
    except NoBuildData:
        log ("NoBuildDatar:unstable")
        pass
    return 2

def get_overall_state(jobs):
    global server
    try:

        log ("Getting current State.")
    	if server is None:
            log ("server undefined. reconnecting")
    	    server = Jenkins(viewURL,username,password)

        running = False
        current_state = State.disabled
        for job in jobs:
            log("checking job")
            log(job[0])
            jobinstance = server.get_job(job[0])
            if(jobinstance.is_running()):
                running = True
            jobstate = get_current_state(jobinstance)
            if current_state < jobstate:
                current_state = jobstate
        return running + current_state

    except:
        server = None
        log("Connection Error.")
    return overall_state

def handle_code(code):
    global brightness
    global running_pulse_scale
    if code == ecodes.KEY_RIGHT:
        brightness = max(0,brightness - brightness_step)
    elif code == ecodes.KEY_LEFT:
        brightness = min(1,brightness + brightness_step)
    elif code == ecodes.KEY_UP:
        running_pulse_scale = min(1,running_pulse_scale + brightness_step)
    elif code == ecodes.KEY_DOWN:
        running_pulse_scale = max(0,running_pulse_scale - brightness_step)
    elif code == ecodes.KEY_ENTER:
        msleep(200)


def joystickupdate():
    found = False;
    devices = [InputDevice(fn) for fn in list_devices()]
    for dev in devices:
        if dev.name == 'Raspberry Pi Sense HAT Joystick':
            found = True;
            break

    if not(found):
        log('Raspberry Pi Sense HAT Joystick not found. Aborting ...')
        sys.exit()
    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY:
            if event.value == 0:  # key up
                handle_code(event.code)
def checkJobs():
    global overall_state
    global server
    jobs = server.get_jobs()
    while True:
        try:
            if server is None:
                try:
                    server = Jenkins(viewURL,username,password)
                    log ( "reconnected." )
                except:
                    log ("failed to reconnect")
                    msleep(5000)
            if server != None:
                jobs = server.get_jobs()
                overall_state = get_overall_state(jobs)
                #log ("state:" + overall_state)
        except:
            log("failed somewhere... going to loop again anyway.")

def processConfig(filePath):

    global username
    global password
    global viewURL

    config = ConfigParser.SafeConfigParser()
    config.read(filePath)
    username = config.get("authentication","user")
    password = config.get("authentication","password")
    viewURL = config.get("authentication","view")
    print "username:",username
    print "password:",password
    print "url:",viewURL

def main(argv):
    global username
    global password
    global viewURL
    try:
        opts, args = getopt.getopt(argv,"u:p:c:h:",["config=","user=","password=","host="])
    except getopt.GetoptError:
        sys.exit(2)

    print str(opts)
    print str(args)
    for opt,arg in opts:
        print opt, ":", arg
        if opt in ("-c","--config"):
            print "have config file"
            processConfig(arg)
            break
        elif opt in ("-u","--user"):
            username = arg
        elif opt in ("-p","--password"):
            password = arg
        elif opt in ("-h","--host"):
            viewURL = arg

    global server
    server = Jenkins(viewURL,username,password)
    try:
        screenthread = threading.Thread(target=screenupdate)
        screenthread.start()

        joystickThread = threading.Thread(target = joystickupdate)
        joystickThread.start()

        jobThread = threading.Thread(target = checkJobs)
        jobThread.start()

    except KeyboardInterrupt:
        log ("ShuttingDown maybe...")
        screenthread.stop()
        joystickThread.stop()
        jobThread.stop()
        sys.exit()

if __name__ == "__main__":
    main(sys.argv[1:])
