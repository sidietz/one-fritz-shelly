#!/usr/bin/python3
import threading
import time
import json
import socket
import logging
import requests
import hashlib
import binascii
import xml.etree.ElementTree as ET
import urllib.parse
import os
import struct

try:
    from zeroconf import Zeroconf, ServiceInfo
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

# --- KONFIGURATION ---
FRITZ_IP = '192.168.168.1'
FRITZ_USER = 'SimonDietz'

FRITZ_PW = ""
with open('pw.txt', 'r') as file:
    FRITZ_PW = file.read().strip()

FRITZ_BASE_AIN = ""
with open('ain.txt', 'r') as file:
    FRITZ_BASE_AIN = file.read().strip()


LISTEN_PORT = 80

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

data_lock = threading.Lock()
shared_data = {"power": 0.0, "energy": 0.0, "sid": "0000000000000000", "gateway_addr": None}

class FritzCollector:
    def __init__(self):
        self.ain_base = FRITZ_BASE_AIN.replace(' ', '%20')

    def update(self):
        try:
            if shared_data["sid"] == "0000000000000000":
                r = requests.get(f"http://{FRITZ_IP}/login_sid.lua", timeout=5)
                ch = ET.fromstring(r.text).findtext('Challenge')
                res = f"{ch}-{hashlib.md5(f'{ch}-{FRITZ_PW}'.encode('utf-16le')).hexdigest()}"
                resp = requests.get(f"http://{FRITZ_IP}/login_sid.lua?username={FRITZ_USER}&response={res}", timeout=10).text
                shared_data["sid"] = ET.fromstring(resp).findtext('SID')

            url = f"http://{FRITZ_IP}/webservices/homeautoswitch.lua?ain={self.ain_base}&sid={shared_data['sid']}&switchcmd=getdeviceinfos&refresh=1"
            req = requests.get(url, timeout=5)
            root = ET.fromstring(req.text)
            
            power_elem = root.find(".//power")
            if power_elem is not None and power_elem.text is not None:
                power = round(float(power_elem.text) / 1000.0, 2)
            else:
                power = 0.0

            energy_elem = root.find(".//energy")
            if energy_elem is not None and energy_elem.text is not None:
                energy = round(float(energy_elem.text), 2)
            else:
                energy = shared_data.get("energy", 0.0)

            with data_lock:
                shared_data["power"] = power
                shared_data["energy"] = energy
            logging.info(f"FritzBox Update: {power} W, {energy} Wh")
        except Exception as e:
            logging.error(f"Fritz-Fehler: {e}")
            shared_data["sid"] = "0000000000000000"

def collector_loop():
    collector = FritzCollector()
    while True:
        collector.update()
        time.sleep(10)

START_TIME = time.time()
SHELLY_MAC = "E682E89C1724"
SHELLY_NAME = f"shellypro3em-{SHELLY_MAC.lower()}"
SHELLY_FW_ID = "20241011-114455/1.4.4-g6d2a586"
SHELLY_GEN = 2

def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def get_shelly_device_info():
    return {
        "id": SHELLY_NAME,
        "mac": SHELLY_MAC,
        "slot": 1,
        "model": "SPEM-003CEBEU",
        "gen": SHELLY_GEN,
        "fw_id": SHELLY_FW_ID,
        "ver": "1.4.4",
        "app": "Pro3EM",
        "auth_en": False,
        "auth_domain": None,
        "profile": "triphase"
    }

def get_em_status():
    with data_lock:
        p = shared_data.get("power", 0.0)
    phase_power = round(p * 0.3333, 2)
    voltage = 230.0
    current = round(phase_power / voltage, 2)
    aprt_power = phase_power
    pf = 1.0
    freq = 50.0
    total_act_power = round(phase_power * 3, 2)
    total_aprt_power = round(aprt_power * 3, 2)
    total_current = round(total_act_power / voltage, 2)
    return {
        "id": 0,
        "a_current": current,
        "a_voltage": voltage,
        "a_act_power": phase_power,
        "a_aprt_power": aprt_power,
        "a_pf": pf,
        "a_freq": freq,
        "b_current": current,
        "b_voltage": voltage,
        "b_act_power": phase_power,
        "b_aprt_power": aprt_power,
        "b_pf": pf,
        "b_freq": freq,
        "c_current": current,
        "c_voltage": voltage,
        "c_act_power": phase_power,
        "c_aprt_power": aprt_power,
        "c_pf": pf,
        "c_freq": freq,
        "n_current": None,
        "total_current": total_current,
        "total_act_power": total_act_power,
        "total_aprt_power": total_aprt_power,
        "user_calibrated_phase": []
    }

def get_emdata_status():
    with data_lock:
        e = shared_data.get("energy", 0.0)
    phase_energy = round(e * 0.3333, 2)
    total_act = round(phase_energy * 3, 2)
    return {
        "id": 0,
        "a_total_act_energy": phase_energy,
        "a_total_act_ret_energy": 0.0,
        "b_total_act_energy": phase_energy,
        "b_total_act_ret_energy": 0.0,
        "c_total_act_energy": phase_energy,
        "c_total_act_ret_energy": 0.0,
        "total_act": total_act,
        "total_act_ret": 0.0
    }

def get_em_config():
    return {
        "id": 0,
        "name": None,
        "blink_mode_selector": "active_energy",
        "phase_selector": "a",
        "monitor_phase_sequence": True,
        "reverse": {},
        "ct_type": "120A"
    }

def get_sys_config():
    local_ip = get_local_ip()
    return {
        "device": {
            "name": SHELLY_NAME,
            "mac": SHELLY_MAC,
            "fw_id": SHELLY_FW_ID,
            "eco_mode": False,
            "profile": "triphase",
            "discoverable": False
        },
        "location": {
            "tz": "Europe/Berlin",
            "lat": 54.306,
            "lon": 9.663
        },
        "debug": {
            "mqtt": {"enable": False},
            "websocket": {"enable": False},
            "udp": {"addr": None}
        },
        "ui_data": {},
        "rpc_udp": {
            "dst_addr": local_ip,
            "listen_port": LISTEN_PORT
        },
        "sntp": {
            "server": None
        },
        "cfg_rev": 10
    }

def get_sys_status():
    now = int(time.time())
    time_str = time.strftime("%H:%M", time.localtime(now))
    uptime = int(now - START_TIME)
    return {
        "mac": SHELLY_MAC,
        "restart_required": False,
        "time": time_str,
        "unixtime": now,
        "last_sync_ts": now,
        "uptime": uptime,
        "ram_size": 327680,
        "ram_free": 163840,
        "fs_size": 4194304,
        "fs_free": 2097152,
        "cfg_rev": 10,
        "kvs_rev": 2725,
        "schedule_rev": 0,
        "webhook_rev": 0,
        "btrelay_rev": 0,
        "available_updates": {
            "beta": {
                "version": "1.7.5-beta1"
            }
        }
    }

def get_shelly_config():
    local_ip = get_local_ip()
    return {
        "ble": {"enable": False},
        "cloud": {"enable": False, "server": None},
        "em:0": get_em_config(),
        "sys": get_sys_config(),
        "wifi": {
            "sta": {
                "ssid": "FritzBox",
                "is_open": False,
                "enable": True,
                "ipv4mode": "dhcp",
                "ip": local_ip,
                "netmask": "255.255.255.0",
                "gw": FRITZ_IP,
                "nameserver": FRITZ_IP
            },
            "ws": {
                "enable": False,
                "server": None,
                "ssl_ca": "ca.pem"
            }
        }
    }

def get_shelly_components():
    return {
        "components": [
            {
                "key": "em:0",
                "status": get_em_status(),
                "config": get_em_config()
            },
            {
                "key": "emdata:0",
                "status": get_emdata_status(),
                "config": {}
            }
        ],
        "cfg_rev": 1,
        "offset": 0,
        "total": 2
    }

def get_shelly_status():
    local_ip = get_local_ip()
    return {
        "ble": {},
        "bthome": {},
        "cloud": {"connected": False},
        "em:0": get_em_status(),
        "emdata:0": get_emdata_status(),
        "eth": {"ip": None, "ip6": None},
        "modbus": {},
        "mqtt": {"connected": False},
        "sys": get_sys_status(),
        "temperature:0": {
            "id": 0,
            "tC": 26.55,
            "tF": 79.79
        },
        "wifi": {
            "sta_ip": local_ip,
            "status": "got ip",
            "ssid": "FritzBox",
            "bssid": "00:00:00:00:00:00",
            "rssi": -60,
            "sta_ip6": []
        },
        "ws": {"connected": False}
    }

def get_wifi_status():
    local_ip = get_local_ip()
    return {
        "sta_ip": local_ip,
        "status": "got ip",
        "ssid": "FritzBox",
        "bssid": "00:00:00:00:00:00",
        "rssi": -60,
        "ap_client_count": 0
    }

def get_shelly_list_methods():
    return {
        "methods": [
            "EM.GetStatus",
            "EM.GetConfig",
            "EMData.GetStatus",
            "Shelly.GetComponents",
            "Shelly.GetConfig",
            "Shelly.GetDeviceInfo",
            "Shelly.GetStatus",
            "Sys.GetConfig",
            "Sys.GetStatus",
            "WiFi.GetStatus"
        ]
    }

def dispatch_method(method, params=None):
    if method in ("Shelly.GetDeviceInfo", "shelly"):
        return get_shelly_device_info()
    elif method in ("Shelly.GetStatus", "status"):
        return get_shelly_status()
    elif method == "Shelly.GetComponents":
        return get_shelly_components()
    elif method == "Shelly.GetConfig":
        return get_shelly_config()
    elif method == "Shelly.ListMethods":
        return get_shelly_list_methods()
    elif method == "EM.GetStatus":
        return get_em_status()
    elif method == "EM.GetConfig":
        return get_em_config()
    elif method == "EMData.GetStatus":
        return get_emdata_status()
    elif method == "Sys.GetConfig":
        return get_sys_config()
    elif method == "Sys.GetStatus":
        return get_sys_status()
    elif method == "WiFi.GetStatus":
        return get_wifi_status()
    elif method == "Script.GetCode":
        return {"data": "", "left": "0"}
    elif method == "Script.List":
        return {"scripts": []}
    else:
        return {}

from http.server import BaseHTTPRequestHandler, HTTPServer

class ShellyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f"<html><body><h1>{SHELLY_NAME}</h1><p>Shelly Pro 3EM Emulator running.</p></body></html>"
            self.wfile.write(html.encode('utf-8'))
            return

        method_name = None
        if path in ('/shelly', '/status'):
            method_name = path.lstrip('/')
        elif path.startswith('/rpc/'):
            method_name = path[len('/rpc/'):]
        elif path == '/rpc':
            query = urllib.parse.parse_qs(parsed_path.query)
            if 'method' in query:
                method_name = query['method'][0]

        if method_name:
            result = dispatch_method(method_name)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        req_json = {}
        if body:
            try:
                req_json = json.loads(body)
            except Exception:
                pass

        if path == '/rpc':
            req_id = req_json.get("id", 0)
            req_method = req_json.get("method", "")
            req_src = req_json.get("src", None)
            req_params = req_json.get("params", {})

            result = dispatch_method(req_method, req_params)
            resp = {
                "id": req_id,
                "src": SHELLY_NAME,
                "result": result
            }
            if req_src is not None and req_src != "EMPTY":
                resp["dst"] = req_src

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
        else:
            method_name = None
            if path in ('/shelly', '/status'):
                method_name = path.lstrip('/')
            elif path.startswith('/rpc/'):
                method_name = path[len('/rpc/'):]

            if method_name:
                if "method" in req_json and "id" in req_json:
                    result = dispatch_method(req_json["method"], req_json.get("params", {}))
                    resp = {
                        "id": req_json["id"],
                        "src": SHELLY_NAME,
                        "result": result
                    }
                    if req_json.get("src") and req_json.get("src") != "EMPTY":
                        resp["dst"] = req_json["src"]
                else:
                    resp = dispatch_method(method_name, req_json)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()

    def log_message(self, format, *args):
        logging.info(f"HTTP {format % args} von {self.client_address[0]}")

def udp_rpc_server(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        logging.info(f"UDP RPC Server aktiv auf Port {port}")
        while True:
            try:
                data, addr = s.recvfrom(2048)
                if not data:
                    continue
                req_json = json.loads(data.decode('utf-8'))
                if "method" in req_json:
                    req_id = req_json.get("id", 0)
                    req_method = req_json.get("method", "")
                    req_src = req_json.get("src", None)
                    req_params = req_json.get("params", {})

                    result = dispatch_method(req_method, req_params)
                    resp = {
                        "id": req_id,
                        "src": SHELLY_NAME,
                        "result": result
                    }
                    if req_src is not None and req_src != "EMPTY":
                        resp["dst"] = req_src

                    s.sendto(json.dumps(resp).encode('utf-8'), addr)
            except Exception as e:
                logging.debug(f"UDP RPC Error: {e}")
    except Exception as e:
        logging.error(f"Konnte UDP Server auf Port {port} nicht starten: {e}")

def setup_zeroconf():
    if not HAS_ZEROCONF:
        return None
    try:
        zc = Zeroconf()
        local_ip = get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)
        txt_dict = {
            "arch": "esp8266",
            "gen": str(SHELLY_GEN),
            "fw_id": SHELLY_FW_ID,
            "id": SHELLY_NAME
        }
        for st in ("_shelly._tcp.local.", "_http._tcp.local.", "_TLStcp._tcp.local."):
            info = ServiceInfo(
                st,
                f"{SHELLY_NAME}.{st}",
                addresses=[ip_bytes],
                port=LISTEN_PORT,
                properties=txt_dict,
                server=f"{SHELLY_NAME}.local."
            )
            zc.register_service(info)
        logging.info(f"Zeroconf mDNS Advertisements aktiv ({local_ip}:{LISTEN_PORT} -> _shelly, _http, _TLStcp)")
        return zc
    except Exception as e:
        logging.warning(f"Zeroconf mDNS Registrierung fehlgeschlagen: {e}")
        return None

def encode_dns_name(name):
    parts = name.strip('.').split('.')
    encoded = b""
    for part in parts:
        encoded += bytes([len(part)]) + part.encode('utf-8')
    encoded += b"\x00"
    return encoded

def build_mdns_response(tx_id, service_type):
    local_ip = get_local_ip()
    instance_name = f"{SHELLY_NAME}.{service_type}"
    host_name = f"{SHELLY_NAME}.local."

    header = tx_id + b"\x84\x00\x00\x00\x00\x01\x00\x00\x00\x03"

    ptr_name = encode_dns_name(service_type)
    ptr_rdata = encode_dns_name(instance_name)
    ptr_rr = ptr_name + struct.pack('>HHIH', 12, 1, 120, len(ptr_rdata)) + ptr_rdata

    srv_name = encode_dns_name(instance_name)
    srv_target = encode_dns_name(host_name)
    srv_rdata = struct.pack('>HHH', 0, 0, LISTEN_PORT) + srv_target
    srv_rr = srv_name + struct.pack('>HHIH', 33, 0x8001, 120, len(srv_rdata)) + srv_rdata

    txt_name = encode_dns_name(instance_name)
    txt_items = [
        b"arch=esp8266",
        f"gen={SHELLY_GEN}".encode('utf-8'),
        f"fw_id={SHELLY_FW_ID}".encode('utf-8'),
        f"id={SHELLY_NAME}".encode('utf-8')
    ]
    txt_rdata = b"".join(bytes([len(item)]) + item for item in txt_items)
    txt_rr = txt_name + struct.pack('>HHIH', 16, 0x8001, 120, len(txt_rdata)) + txt_rdata

    a_name = encode_dns_name(host_name)
    a_rdata = socket.inet_aton(local_ip)
    a_rr = a_name + struct.pack('>HHIH', 1, 0x8001, 120, len(a_rdata)) + a_rdata

    return header + ptr_rr + srv_rr + txt_rr + a_rr

def mdns_raw_server():
    MCAST_GRP = '224.0.0.251'
    MCAST_PORT = 5353
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
        sock.bind(('', MCAST_PORT))
        
        mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        logging.info(f"Fallback mDNS Server aktiv auf {MCAST_GRP}:{MCAST_PORT}")
        
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                if not data or len(data) < 12:
                    continue
                flags = struct.unpack('>H', data[2:4])[0]
                if (flags & 0x8000) != 0:
                    continue

                tx_id = data[:2]
                query_str = data[12:].decode('latin1', errors='ignore')

                service_types = []
                if "_TLStcp" in query_str:
                    service_types.append("_TLStcp._tcp.local.")
                if "_shelly" in query_str:
                    service_types.append("_shelly._tcp.local.")
                if "_http" in query_str:
                    service_types.append("_http._tcp.local.")
                if SHELLY_NAME in query_str or "_services._dns-sd._udp" in query_str:
                    service_types.extend(["_shelly._tcp.local.", "_http._tcp.local.", "_TLStcp._tcp.local."])

                seen = set()
                service_types = [s for s in service_types if not (s in seen or seen.add(s))]

                for st in service_types:
                    resp_packet = build_mdns_response(tx_id, st)
                    try:
                        sock.sendto(resp_packet, addr)
                    except Exception:
                        pass
                    try:
                        sock.sendto(resp_packet, (MCAST_GRP, MCAST_PORT))
                    except Exception:
                        pass
                    logging.info(f"mDNS Antwort gesendet für {st} an {addr[0]}")
            except Exception as e:
                logging.debug(f"mDNS Loop Error: {e}")
    except Exception as e:
        logging.error(f"Konnte Fallback mDNS Server nicht starten: {e}")

def http_server():
    server_address = ('0.0.0.0', LISTEN_PORT)
    httpd = HTTPServer(server_address, ShellyHandler)
    logging.info(f"HTTP Server aktiv auf Port {LISTEN_PORT}")
    httpd.serve_forever()

if __name__ == "__main__":
    # Korrekter Start der Threads
    threading.Thread(target=collector_loop, daemon=True).start()
    threading.Thread(target=udp_rpc_server, args=(LISTEN_PORT,), daemon=True).start()
    zc = setup_zeroconf()
    if not zc:
        threading.Thread(target=mdns_raw_server, daemon=True).start()
    http_server()
