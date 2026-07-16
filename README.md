# one-fritz-shelly
Solakon One adapter for a Fritz Dect 250 emulating a Shelly 3 EM

## Disclaimer
This piece of software was **entirely** vibecoded using Google Gemini 3.1 Pro. For API reference the Project [Energy2Shelly_ESP](https://github.com/TheRealMoeder/Energy2Shelly_ESP) was used. The authentication code was obtained from [a heise article](https://www.heise.de/hintergrund/Fritz-SmartEnergy-250-Mit-Emulation-zur-PV-Akku-Steuerung-11319322.html).

## Prompts
### Promt 1
You'll find an unfinished script called ctshelly-evcc.py. It emulates a Shelly 3 PM device. You'll find a working C++ implementation of the shelly product in Energy2Shelly_ESP in the ctshelly folder.
Fix the ctshelly-evcc.py script so that it implements the shelly protocol by reverse engineering the c++ implementation Energy2Shelly_ESP.

### Prompt 2
Lookup how Shelly's mdns advertisements are formatted and add a fake mdns advertisement that answers a (sniffed request) - request data obtained with [wireshark](https://www.wireshark.org/).

## Usage
1. Provide the Fritz Admin Password in pw.txt and the Fritz AIN in ain.txt (and change the Fritz user in the code, too). 
2. Create a python vitual env and load it
3. run onefritzshelly.py with python

Tip:
In order to use port 80, root rights are necessary.

