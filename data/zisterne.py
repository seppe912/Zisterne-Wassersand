#!REPLACELBPBINDIR/venv/bin/python3
import RPi.GPIO as GPIO
import time
import configparser
import paho.mqtt.client as mqtt
import json
import logging
import sys
import requests
import signal

cfg_path = 'REPLACELBPCONFIGDIR' #### REPLACE LBPCONFIGDIR ####
log_path = 'REPLACELBPLOGDIR' #### REPLACE LBPLOGDIR ####
home_path = 'REPLACELBHOMEDIR' #### REPLACE LBHOMEDIR ####

# Miniserver Daten Laden
cfg = configparser.RawConfigParser()
cfg.read(cfg_path + '/zisterne.cfg')
try:
    DEBUG = cfg.get('default','DEBUG')
    Miniserver = cfg.get('default','MINISERVER')
    Trigger_GPIO = int(cfg.get('default','TRIGGER'))
    Echo_GPIO = int(cfg.get('default','ECHO'))
    global Abfrage
    Abfrage = int(cfg.get('default','ABFRAGE'))
except:
    sys.exit('wrong configuration, please set GPIO Ports')
    
_LOGGER = logging.getLogger("zisterne.py")
if DEBUG == "1":
   logging.basicConfig(level=logging.DEBUG, filename= log_path + '/zisterne-Wasserstand.log', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%d.%m %H:%M:%S')
   print("Debug is True")
   _LOGGER.debug("Debug is True")
else:
   logging.basicConfig(level=logging.INFO, filename= log_path + '/zisterne-Wasserstand.log', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%d.%m %H:%M:%S')


# Credentials to set Loxone Inputs over HTTP
cfg.read(home_path + '/config/system/general.cfg')
LoxIP = cfg.get(Miniserver,'IPADDRESS')
LoxPort = cfg.get(Miniserver,'PORT')
LoxPassword = cfg.get(Miniserver,'PASS')
LoxUser = cfg.get(Miniserver,'ADMIN')



class GracefulKiller:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True
        raise SleepInterruptException()
        
class SleepInterruptException(Exception):
    pass


## MQTT ##
# Ist ein Callback, der ausgeführt wird, wenn sich mit dem Broker verbunden wird
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        _LOGGER.info("MQTT: Verbindung akzeptiert")
        publish = client.publish('Zisterne/connection/status','connected',qos=2, retain=True)
        _LOGGER.debug("Publishing: MsgNum:%s: 'zisterne/connection/status','connected'" % (publish[1]))
    elif rc == 1:
        _LOGGER.error("MQTT: Falsche Protokollversion")
    elif rc == 2:
        _LOGGER.error("MQTT: Identifizierung fehlgeschlagen")
    elif rc == 3:
        _LOGGER.error("MQTT: Server nicht erreichbar")
    elif rc == 4:
        _LOGGER.error("MQTT: Falscher benutzername oder Passwort")
    elif rc == 5:
        _LOGGER.error("MQTT: Nicht autorisiert")
    else:
        _LOGGER.error("MQTT: Ungültiger Returncode")

def on_disconnect(client, userdata, flags, rc):
    publish = client.publish('Zisterne/connection/status','disconnected',qos=2, retain=True)
    _LOGGER.debug("Publishing: MsgNum:%s: 'zisterne/connection/status','disconnected'" % (publish[1]))

try: # check if MQTTgateway is installed or not and set MQTT Client settings
    with open(home_path + '/config/system/general.json') as jsonFile:
        jsonObject = json.load(jsonFile)
        jsonFile.close()
    MQTTuser = jsonObject["Mqtt"]["Brokeruser"]
    MQTTpass = jsonObject["Mqtt"]["Brokerpass"]
    MQTTport = jsonObject["Mqtt"]["Brokerport"]
    MQTThost = jsonObject["Mqtt"]["Brokerhost"]
    MQTTpsk = jsonObject["Mqtt"]["Brokerpsk"]
    client = mqtt.Client(client_id='zisterne')
    client.username_pw_set(MQTTuser, MQTTpass)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.will_set('Zisterne/connection/status','disconnected',qos=2, retain=True)
    _LOGGER.info('found MQTT Gateway Plugin - publish over MQTT')
    client.connect(MQTThost, int(MQTTport))
    client.loop_start()
    MQTT = 1
except:
    _LOGGER.debug('cant find MQTT Gateway use HTTP requests to set Loxone inputs')
    MQTT = 0


#GPIO Modus (BOARD / BCM)
GPIO.setmode(GPIO.BCM)
 
#GPIO Pins zuweisen
GPIO_TRIGGER = Trigger_GPIO
GPIO_ECHO = Echo_GPIO
 
#Richtung der GPIO-Pins festlegen (IN / OUT)
GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
GPIO.setup(GPIO_ECHO, GPIO.IN)

abstand = []

def distanz():
    count = 0
    abstand_list = []
    while count <= 100:
        # setze Trigger auf LOW --> Rauschunterdrückung
        GPIO.output(GPIO_TRIGGER, False)
        time.sleep(0.01)
        
        # setze Trigger auf HIGH
        GPIO.output(GPIO_TRIGGER, True)
     
        # setze Trigger nach 10ms auf LOW
        time.sleep(0.01)
        GPIO.output(GPIO_TRIGGER, False)
        StartZeit = time.time()
        StopZeit = time.time()
     
        # speichere Startzeit
        while GPIO.input(GPIO_ECHO) == 0:
            StartZeit = time.time()
     
        # speichere Ankunftszeit
        while GPIO.input(GPIO_ECHO) == 1:
            StopZeit = time.time()
     
        # Zeit Differenz zwischen Start und Ankunft
        TimeElapsed = StopZeit - StartZeit
        # mit der Schallgeschwindigkeit (34300 cm/s) multiplizieren
        # und durch 2 teilen, da hin und zurueck
        
        distanz = (TimeElapsed * 34300) / 2
        abstand_list.insert(0,round(distanz,1))
        count += 1

    abstand.insert(0,sorted(abstand_list)[int(len(abstand_list)/2)]) #Median aus n Messungen
        
    _LOGGER.debug("Gemessene Entfernung = %.1f cm" % abstand[0])
    if MQTT == 1:
        publish = client.publish('Zisterne/Wasserstand', abstand[0], qos=2, retain=True)
        _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserstand,%s" % (publish[1],abstand[0]))
    else:
        HTTPrequest = ("http://%s:%s@%s:%s/dev/sps/io/Zisterne_Wasserstand/%s" % (LoxUser, LoxPassword, LoxIP, LoxPort, abstand[0]))
        r = requests.get(HTTPrequest)
        if r.status_code != 200:
            _LOGGER.error("Error {} on set Loxone Input Midea_{}_online, please Check User PW and IP from Miniserver in Loxberry config and the Names of Loxone Inputs.".format(r.status_code, device.id))
    _LOGGER.debug('Anzahl Messungen in der Liste: %s' % len(abstand))
        
    return abstand
 
if __name__ == '__main__':
    try:
        _LOGGER.info('starte loop...')
        
        killer = GracefulKiller()
        while not killer.kill_now:
            abstand = distanz()

            try: # sleep abbrechen wenn killsignal kommt
                if max(abstand) - min(abstand) >0.5:
                    _LOGGER.info('Wasserstandsänderung erkannt')
                    publish = client.publish('Zisterne/Wasserentnahme', 1, qos=2, retain=True)
                    _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserentnahme,1" % (publish[1]))
                    while max(abstand) - min(abstand) >0.5:
                        _LOGGER.debug(max(abstand) - min(abstand))
                        if Abfrage > 5:
                            _LOGGER.info('Erhöhe Abfragefrequenz auf 5 Sekunden')
                            time.sleep(5) 
                        else:
                            time.sleep(Abfrage)
                        while len(abstand) >= 180/Abfrage:
                            abstand.pop()
                        abstand = distanz()
                    else:
                        _LOGGER.info('Abfragefrequenz auf %s Sekunden zurückgesetzt' % Abfrage)
                        publish = client.publish('Zisterne/Wasserentnahme', 0, qos=2, retain=True)
                        _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserentnahme,0" % (publish[1]))
                else:
                    time.sleep(Abfrage)
                    while len(abstand) >= 180/Abfrage:
                        abstand.pop()
            except SleepInterruptException:
                _LOGGER.info('wakeup from sleep, stopping process..')

        GPIO.cleanup()
        _LOGGER.info('... stopped')
    except:
        GPIO.cleanup()
        _LOGGER.error('cleanup after exception')
        _LOGGER.error(str(sys.exc_info()))
