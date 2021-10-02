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
DEBUG = cfg.get('default','DEBUG')

#LOGGING
_LOGGER = logging.getLogger("zisterne.py")
if DEBUG == "1":
   logging.basicConfig(level=logging.DEBUG, filename= log_path + '/zisterne-Wasserstand.log', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%d.%m %H:%M:%S')
   _LOGGER.debug("Debug is True")
else:
   logging.basicConfig(level=logging.INFO, filename= log_path + '/zisterne-Wasserstand.log', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%d.%m %H:%M:%S')

# Konfiguration einlesen
try:
    Miniserver = cfg.get('default','MINISERVER')
    GPIO_TRIGGER = int(cfg.get('default','TRIGGER'))
    GPIO_ECHO = int(cfg.get('default','ECHO'))
    abfrage = int(cfg.get('default','abfrage'))
    max_abstand = int(cfg.get('default','max_abstand'))
    
    # Credentials to set Loxone Inputs over HTTP
    cfg.read(home_path + '/config/system/general.cfg')
    LoxIP = cfg.get(Miniserver,'IPADDRESS')
    LoxPort = cfg.get(Miniserver,'PORT')
    LoxPassword = cfg.get(Miniserver,'PASS')
    LoxUser = cfg.get(Miniserver,'ADMIN')
except:
    _LOGGER.error(traceback.format_exc())
    _LOGGER.error('Kann nicht starten, bitte erst alle Konfigurationsoptionen setzen')
    sys.exit()


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

def init(GPIO_TRIGGER, GPIO_ECHO):
    #GPIO Modus (BOARD / BCM)
    GPIO.setmode(GPIO.BCM)
     
    #Richtung der GPIO-Pins festlegen (IN / OUT)
    GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
    GPIO.setup(GPIO_ECHO, GPIO.IN)
    
    GPIO.output(GPIO_TRIGGER, False)
    time.sleep(0.06)

def send_to_loxone(abstand):
    if MQTT == 1:
        publish = client.publish('Zisterne/Wasserstand', abstand[0], qos=2, retain=True)
        _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserstand,%s'" % (publish[1],abstand[0]))
    else:
        HTTPrequest = ("http://%s:%s@%s:%s/dev/sps/io/Zisterne_Wasserstand/%s" % (LoxUser, LoxPassword, LoxIP, LoxPort, abstand[0]))
        r = requests.get(HTTPrequest)
        if r.status_code != 200:
            _LOGGER.error("Error {} on set Loxone Zisterne_Wasserstand, please Check User PW and IP from Miniserver in Loxberry config and the Names of Loxone Inputs.".format(r.status_code, device.id))

def distanz():
    count = 0
    n = 0
    fehlmessungen = 0
    messungen = 20 # Messergebnisse übrig nach korrektur zur Bildung vom Median
    korrektur = 10 # alle 20+n Messungen n größte und n kleinste Messwerte aus der Liste entfernen
    abstand_list = []
        
    while count < messungen + int(messungen/20)*2*korrektur:
        try:
            triggertimer = time.time()
            # setze Trigger auf HIGH
            GPIO.output(GPIO_TRIGGER, True)
            
            # setze Trigger nach 10ms auf LOW
            time.sleep(0.015)
            GPIO.output(GPIO_TRIGGER, False)

            # speichere Startzeit
            echo_low_time = time.time()
            while GPIO.input(GPIO_ECHO) == 0:
                StartZeit = time.time()
                if StartZeit - echo_low_time >= 0.001:
                    _LOGGER.error('Low Signal ist mit %.7f Sekunden zu lange, starte neue Messung' % (StartZeit - echo_low_time))
                    break

            # speichere Ankunftszeit
            echo_high_time = time.time()
            while GPIO.input(GPIO_ECHO) == 1:
                StopZeit = time.time()
                if StopZeit - echo_high_time >= 0.03: #0.03 = 5,145m
                    LOGGER.error('High Signal ist mit %.4f Sekunden zu lange, starte neue Messung' % (StopZeit - echo_high_time))
                    break

            if StartZeit - echo_low_time >= 0.001 or StopZeit - echo_high_time >= 0.03:
                fehlmessungen += 1
                _LOGGER.error('Fehlmessungen: %s, continue' % fehlmessungen)
                if fehlmessungen > 10:
                    time.sleep(1)
                continue
                
            # Zeit Differenz zwischen Start und Ankunft
            TimeElapsed = round((StopZeit - StartZeit),7)
            
            # mit der Schallgeschwindigkeit (34300 cm/s) multiplizieren
            # und durch 2 teilen, da hin und zurueck
            distanz = (TimeElapsed * 34300) / 2
            
            if distanz > max_abstand:
                fehlmessungen += 1
                _LOGGER.error('Messwert mit %.1fcm zu hoch. Messe erneut' % distanz)
                if fehlmessungen > 10:
                    time.sleep(1)
                continue
                
            abstand_list.insert(0,round(distanz,1))
            count += 1

            #aussortieren der größten und kleinsten Werte
            if count in range(20 + 2*korrektur, messungen + 1 + int(messungen/20)*2*korrektur, 20 + 2*korrektur):
                for i in range(korrektur):
                    abstand_list.remove(min(abstand_list[0:20 + 2*korrektur-i-n]))
                    abstand_list.remove(max(abstand_list[0:20 + 2*korrektur-1-i-n]))
                    if n == korrektur-1:
                        n = 0
                    else:
                        n += 1

                _LOGGER.debug('min:%s Max:%s Median:%s Range:%.1f Anzahl:%s count: %s Fehlmessungen: %s' % (min(abstand_list[0:20]),max(abstand_list[0:20]), round(statistics.median(abstand_list[0:20]),1),max(abstand_list[0:20]) - min(abstand_list[0:20]), len(abstand_list),count, fehlmessungen))
                _LOGGER.debug(sorted(abstand_list[0:20]))
                
        except Exception as error:
            fehlmessungen += 1
            _LOGGER.error(traceback.format_exc())
            _LOGGER.warn('Messungsliste: %s , Anzahl der Messungen: %s, count: %s Fehlmessungen: %s' % (sorted(abstand_list),len(abstand_list),count, fehlmessungen))
            # if fehlmessungen < messungen:
                # _LOGGER.error('error:%s, starte Messung neu. Fehlmessungen: %s' % (error,fehlmessungen))
                # time.sleep(1)
                # continue
            # else:
                # raise Exception('zuviele Fehlmessungen, beende Script. Bitte auf Fehlersuche begeben')
            continue

    # if fehlmessungen < messungen:
        # abstand.insert(0,statistics.median(abstand_list)) #Median aus n Messungen
        # return abstand
    # else:
        # raise Exception('zuviele Fehlmessungen, beende Script. Bitte auf Fehlersuche begeben')
    abstand.insert(0,round(statistics.median(abstand_list),1)) #Median aus n Messungen
    change = round((max(abstand) - min(abstand)),1)
    return abstand, change
 
 
            
######## Scriptstart #####
if __name__ == '__main__':
    try:
        _LOGGER.info('Starte Abfrageschleife...')
        # timestamp = time.time()
        killer = GracefulKiller()
        init(GPIO_TRIGGER, GPIO_ECHO)
        abstand = []
        while not killer.kill_now:
            # if time.time() - timestamp > 1800:
                # _LOGGER.info('restart')
                # GPIO.cleanup()
                # init(GPIO_TRIGGER, GPIO_ECHO)
                # timestamp = time.time()
            abstand, change = distanz()
            _LOGGER.debug('Gemessene Entfernung = %scm. Letzte %s Messungen gespeichert.' % (abstand[0],len(abstand)))
            
            #sende nur veränderte Messwerte (Cache)
            if len(abstand) == 1: 
                send_to_loxone(abstand)
            elif abstand[0] != abstand[1]:
                send_to_loxone(abstand)
            
            #Wasserstandsänderung.
            if change > 0.1: #Wasserstandsänderung erkannt, erhöhe abfragefrequenz
                _LOGGER.info('Wasserstandsänderung von %scm erkannt' % change)
                publish = client.publish('Zisterne/Wasserentnahme', 1, qos=2, retain=True)
                _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserentnahme,1'" % (publish[1]))
                if abfrage > 5:
                    _LOGGER.info('Erhöhe Abfragefrequenz auf 5 Sekunden')
                while change > 0.1:
                    if abfrage > 5:
                        time.sleep(5) 
                        while len(abstand) >= 36: #Überwachter Zeitraum 3 Minuten
                            abstand.pop()
                    else:
                        time.sleep(abfrage)
                        while len(abstand) >= 180/abfrage: #Überwachter Zeitraum 3 Minuten
                            abstand.pop()
                    abstand, change = distanz()                    
                    _LOGGER.debug('Gemessene Entfernung = %scm. Letzte %s Messungen gespeichert. Wasserstandsänderung mit %scm erkannt.' % (abstand[0],len(abstand),change))
                    #sende nur veränderte Messwerte (Cache)
                    if abstand[0] != abstand[1]:
                        send_to_loxone(abstand)
                else:
                    _LOGGER.info('Abfragefrequenz auf %s Sekunden zurückgesetzt' % abfrage)
                    publish = client.publish('Zisterne/Wasserentnahme', 0, qos=2, retain=True)
                    _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserentnahme,0'" % (publish[1]))
            else: #keine Änderung erkannt, warte..      
                time.sleep(abfrage)
                while len(abstand) >= 180/abfrage and len(abstand) >= 5: #Überwachter Zeitraum 3 Minuten, aber mindestens 5 abfrageabstände
                    abstand.pop()

    except SleepInterruptException:
        _LOGGER.info('wakeup from sleep, and finally..')
    except:
        _LOGGER.error(traceback.format_exc())
    
    finally:
        GPIO.cleanup()
        publish = client.publish('Zisterne/Wasserentnahme', 0, qos=2, retain=True)
        _LOGGER.debug("Publishing msg %s: 'Zisterne/Wasserentnahme,0'" % (publish[1]))
        publish.wait_for_publish()
        _LOGGER.info('... stopped')
