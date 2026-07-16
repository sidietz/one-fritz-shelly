import sys
import os
import json
import socket
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock
import pytest

# Add onefritzshelly directory to path so onefritzshelly-evcc can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module under test
import importlib.util
spec = importlib.util.spec_from_file_location("onefritzshelly", os.path.join(os.path.dirname(os.path.abspath(__file__)), "onefritzshelly.py"))
onefritzshelly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onefritzshelly)


@pytest.fixture(autouse=True)
def reset_shared_data():
    """Reset shared_data values before every test."""
    with onefritzshelly.data_lock:
        onefritzshelly.shared_data["power"] = 0.0
        onefritzshelly.shared_data["energy"] = 0.0
        onefritzshelly.shared_data["sid"] = "0000000000000000"


def test_get_shelly_device_info():
    info = onefritzshelly.dispatch_method("Shelly.GetDeviceInfo")
    assert info["model"] == "SPEM-003CEBEU"
    assert info["gen"] == 2
    assert info["profile"] == "triphase"
    assert info["app"] == "Pro3EM"
    assert "mac" in info
    assert "fw_id" in info


def test_em_get_status():
    with onefritzshelly.data_lock:
        onefritzshelly.shared_data["power"] = 1200.0

    status = onefritzshelly.dispatch_method("EM.GetStatus")
    assert status["id"] == 0
    assert status["a_voltage"] == 230.0
    assert status["a_act_power"] == 399.96
    assert status["b_act_power"] == 399.96
    assert status["c_act_power"] == 399.96
    assert status["total_act_power"] == 1199.88
    assert status["n_current"] is None
    assert isinstance(status["user_calibrated_phase"], list)


def test_emdata_get_status():
    with onefritzshelly.data_lock:
        onefritzshelly.shared_data["energy"] = 300.0

    status = onefritzshelly.dispatch_method("EMData.GetStatus")
    assert status["id"] == 0
    assert status["a_total_act_energy"] == 99.99
    assert status["b_total_act_energy"] == 99.99
    assert status["c_total_act_energy"] == 99.99
    assert status["total_act"] == 299.97
    assert status["total_act_ret"] == 0.0


def test_shelly_get_components():
    comp = onefritzshelly.dispatch_method("Shelly.GetComponents")
    assert comp["total"] == 2
    assert len(comp["components"]) == 2
    keys = [c["key"] for c in comp["components"]]
    assert "em:0" in keys
    assert "emdata:0" in keys


def test_shelly_get_config():
    cfg = onefritzshelly.dispatch_method("Shelly.GetConfig")
    assert "em:0" in cfg
    assert "sys" in cfg
    assert "wifi" in cfg


def test_shelly_get_status():
    status = onefritzshelly.dispatch_method("Shelly.GetStatus")
    assert "em:0" in status
    assert "emdata:0" in status
    assert "sys" in status
    assert "wifi" in status


def test_list_methods():
    methods = onefritzshelly.dispatch_method("Shelly.ListMethods")
    assert "methods" in methods
    assert "EM.GetStatus" in methods["methods"]
    assert "EMData.GetStatus" in methods["methods"]
    assert "Shelly.GetDeviceInfo" in methods["methods"]


def test_sys_get_config_and_status():
    sys_cfg = onefritzshelly.dispatch_method("Sys.GetConfig")
    assert sys_cfg["device"]["profile"] == "triphase"
    
    sys_status = onefritzshelly.dispatch_method("Sys.GetStatus")
    assert "uptime" in sys_status
    assert "ram_free" in sys_status


def test_wifi_get_status():
    wifi = onefritzshelly.dispatch_method("WiFi.GetStatus")
    assert wifi["ssid"] == "FritzBox"
    assert "sta_ip" in wifi


def test_script_methods():
    code = onefritzshelly.dispatch_method("Script.GetCode")
    assert code == {"data": "", "left": "0"}
    
    lst = onefritzshelly.dispatch_method("Script.List")
    assert lst == {"scripts": []}


def test_unknown_method():
    res = onefritzshelly.dispatch_method("Unknown.Method")
    assert res == {}


def test_encode_dns_name():
    encoded = onefritzshelly.encode_dns_name("_shelly._tcp.local.")
    assert encoded == b"\x07_shelly\x04_tcp\x05local\x00"


def test_build_mdns_response():
    tx_id = b"\x12\x34"
    pkt = onefritzshelly.build_mdns_response(tx_id, "_TLStcp._tcp.local.")
    # Verify transaction ID and flags (QR + AA)
    assert pkt[:2] == tx_id
    assert pkt[2:4] == b"\x84\x00"
    # Verify service and TXT content are embedded
    assert b"_TLStcp" in pkt
    assert b"arch=esp8266" in pkt


@patch("requests.get")
def test_fritz_collector_update_success(mock_get):
    # First call: login challenge
    challenge_xml = "<SessionInfo><Challenge>12345678</Challenge><SID>0000000000000000</SID></SessionInfo>"
    # Second call: login response with SID
    sid_xml = "<SessionInfo><SID>1111222233334444</SID></SessionInfo>"
    # Third call: device info XML
    device_xml = "<device><power>1500000</power><energy>12345</energy></device>"

    mock_get.side_effect = [
        MagicMock(text=challenge_xml),
        MagicMock(text=sid_xml),
        MagicMock(text=device_xml)
    ]

    collector = onefritzshelly.FritzCollector()
    collector.update()

    with onefritzshelly.data_lock:
        assert onefritzshelly.shared_data["sid"] == "1111222233334444"
        assert onefritzshelly.shared_data["power"] == 1500.0
        assert onefritzshelly.shared_data["energy"] == 12345.0


@patch("requests.get")
def test_fritz_collector_update_exception(mock_get):
    mock_get.side_effect = Exception("Network error")
    collector = onefritzshelly.FritzCollector()
    collector.update()
    with onefritzshelly.data_lock:
        assert onefritzshelly.shared_data["sid"] == "0000000000000000"


@pytest.fixture
def http_server_port():
    """Start an ephemeral HTTP server for testing."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = onefritzshelly.HTTPServer(("127.0.0.1", port), onefritzshelly.ShellyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)
    yield port
    server.shutdown()


def test_http_get_endpoints(http_server_port):
    # Root page
    with urllib.request.urlopen(f"http://127.0.0.1:{http_server_port}/") as resp:
        assert resp.status == 200
        assert b"Shelly Pro 3EM Emulator running" in resp.read()

    # /shelly direct endpoint
    with urllib.request.urlopen(f"http://127.0.0.1:{http_server_port}/shelly") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["model"] == "SPEM-003CEBEU"

    # GET /rpc/EM.GetStatus?id=0
    with urllib.request.urlopen(f"http://127.0.0.1:{http_server_port}/rpc/EM.GetStatus?id=0") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["id"] == 0
        assert "total_act_power" in data

    # 404 handler
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"http://127.0.0.1:{http_server_port}/nonexistent_path")
    assert exc_info.value.code == 404


def test_http_post_rpc(http_server_port):
    with onefritzshelly.data_lock:
        onefritzshelly.shared_data["power"] = 900.0

    payload = json.dumps({
        "id": 99,
        "method": "EM.GetStatus",
        "params": {"id": 0}
    }).encode("utf-8")

    req = urllib.request.Request(
        f"http://127.0.0.1:{http_server_port}/rpc",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["id"] == 99
        assert data["src"] == onefritzshelly.SHELLY_NAME
        assert data["result"]["total_act_power"] == 899.91


def test_udp_rpc_server():
    """Test UDP RPC communication."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    t = threading.Thread(target=onefritzshelly.udp_rpc_server, args=(port,), daemon=True)
    t.start()
    time.sleep(0.1)

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.settimeout(2.0)
    
    req_json = json.dumps({"id": 1234, "method": "Shelly.GetDeviceInfo"}).encode("utf-8")
    client_sock.sendto(req_json, ("127.0.0.1", port))
    
    data, _ = client_sock.recvfrom(2048)
    resp = json.loads(data.decode("utf-8"))
    assert resp["id"] == 1234
    assert resp["src"] == onefritzshelly.SHELLY_NAME
    assert resp["result"]["model"] == "SPEM-003CEBEU"
    client_sock.close()

