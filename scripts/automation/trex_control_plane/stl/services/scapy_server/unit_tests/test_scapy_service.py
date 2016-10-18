#
# run with 'nosetests' utility

import tempfile
from basetest import *

TEST_MAC_1 = "10:10:10:10:10:10"
# Test scapy structure
TEST_PKT = Ether(dst=TEST_MAC_1)/IP(src='127.0.0.1')/TCP(sport=443)

# Corresponding JSON-like structure
TEST_PKT_DEF = [
        layer_def("Ether", dst=TEST_MAC_1),
        layer_def("IP", dst="127.0.0.1"),
        layer_def("TCP", sport="443")
        ]

def test_build_pkt():
    pkt = build_pkt_get_scapy(TEST_PKT_DEF)
    assert(pkt[TCP].sport == 443)

def test_build_invalid_structure_pkt():
    ether_fields = {"dst": TEST_MAC_1, "type": "LOOP"}
    pkt = build_pkt_get_scapy([
        layer_def("Ether", **ether_fields),
        layer_def("IP"),
        layer_def("TCP", sport=8080)
        ])
    assert(pkt[Ether].dst == TEST_MAC_1)
    assert(isinstance(pkt[Ether].payload, Raw))

def test_reconstruct_pkt():
    res = reconstruct_pkt(base64.b64encode(bytes(TEST_PKT)), None)
    pkt = build_pkt_to_scapy(res)
    assert(pkt[TCP].sport == 443)

def test_layer_del():
    modif = [
            {"id": "Ether"},
            {"id": "IP"},
            {"id": "TCP", "delete": True},
    ]
    res = reconstruct_pkt(base64.b64encode(bytes(TEST_PKT)), modif)
    pkt = build_pkt_to_scapy(res)
    assert(not pkt[IP].payload)

def test_layer_field_edit():
    modif = [
            {"id": "Ether"},
            {"id": "IP"},
            {"id": "TCP", "fields": [{"id": "dport", "value": 777}]},
    ]
    res = reconstruct_pkt(base64.b64encode(bytes(TEST_PKT)), modif)
    pkt = build_pkt_to_scapy(res)
    assert(pkt[TCP].dport == 777)
    assert(pkt[TCP].sport == 443)

def test_layer_add():
    modif = [
            {"id": "Ether"},
            {"id": "IP"},
            {"id": "TCP"},
            {"id": "Raw", "fields": [{"id": "load", "value": "GET /helloworld HTTP/1.0\n\n"}]},
    ]
    res = reconstruct_pkt(base64.b64encode(bytes(TEST_PKT)), modif)
    pkt = build_pkt_to_scapy(res)
    assert("GET /helloworld" in str(pkt[TCP].payload.load))

def test_build_Raw():
    pkt = build_pkt_get_scapy([
        layer_def("Ether"),
        layer_def("IP"),
        layer_def("TCP"),
        layer_def("Raw", load={"vtype": "BYTES", "base64": bytes_to_b64(b"hi")})
        ])
    assert(str(pkt[Raw].load == "hi"))

def test_get_all():
    service.get_all(v_handler)

def test_get_definitions_all():
    get_definitions(None)
    def_classnames = [pdef['id'] for pdef in get_definitions(None)['protocols']]
    assert("IP" in def_classnames)
    assert("Dot1Q" in def_classnames)
    assert("TCP" in def_classnames)

def test_get_definitions_ether():
    res = get_definitions(["Ether"])
    assert(len(res) == 1)
    assert(res['protocols'][0]['id'] == "Ether")

def test_get_payload_classes():
    eth_payloads = get_payload_classes([{"id":"Ether"}])
    assert("IP" in eth_payloads)
    assert("Dot1Q" in eth_payloads)
    assert("TCP" not in eth_payloads)

def test_pcap_read_and_write():
    pkts_to_write = [bytes_to_b64(bytes(TEST_PKT))]
    pcap_b64 = service.write_pcap(v_handler, pkts_to_write)
    array_pkt = service.read_pcap(v_handler, pcap_b64)
    pkt = build_pkt_to_scapy(array_pkt[0])
    assert(pkt[Ether].dst == TEST_MAC_1)

