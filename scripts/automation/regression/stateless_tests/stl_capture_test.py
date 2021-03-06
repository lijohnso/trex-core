#!/router/bin/python
from .stl_general_test import CStlGeneral_Test, CTRexScenario
from trex_stl_lib.api import *
import os, sys
import pprint

def ip2num (ip_str):
    return struct.unpack('>L', socket.inet_pton(socket.AF_INET, ip_str))[0]
    
def num2ip (ip_num):
    return socket.inet_ntoa(struct.pack('>L', ip_num))

def ip_add (ip_str, cnt):
    return num2ip(ip2num(ip_str) + cnt)
    
    
class STLCapture_Test(CStlGeneral_Test):
    """Tests for capture packets"""

    def setUp(self):
        CStlGeneral_Test.setUp(self)

        if not self.is_loopback:
            self.skip('capture tests are skipped on a non-loopback machine')
            
        assert 'bi' in CTRexScenario.stl_ports_map

        self.c = CTRexScenario.stl_trex

        self.tx_port, self.rx_port = CTRexScenario.stl_ports_map['bi'][0]

        self.c.connect()
        self.c.reset(ports = [self.tx_port, self.rx_port])

        self.pkt = STLPktBuilder(pkt = Ether()/IP(src="16.0.0.1",dst="48.0.0.1")/UDP(dport=12,sport=1025)/IP()/'a_payload_example')

        self.percentage = 5 if self.is_virt_nics else 50


    @classmethod
    def tearDownClass(cls):
        if CTRexScenario.stl_init_error:
            return
        # connect back at end of tests
        if not cls.is_connected():
            CTRexScenario.stl_trex.connect()


    # a simple capture test - inject packets and see the packets arrived the same
    def test_basic_capture (self):
        pkt_count = 100
        
        try:
            # move to service mode
            self.c.set_service_mode(ports = self.rx_port)
            # start a capture
            rc = self.c.start_capture(rx_ports = [self.rx_port], limit = pkt_count)
            
            # inject few packets with a VM
            vm = STLScVmRaw( [STLVmFlowVar ( "ip_src",  min_value="16.0.0.0", max_value="16.255.255.255", size=4, step = 7, op = "inc"),
                              STLVmWrFlowVar (fv_name="ip_src", pkt_offset= "IP.src"),
                              STLVmFixIpv4(offset = "IP")
                              ]
                             );
              
            pkt = STLPktBuilder(pkt = Ether()/IP(src="16.0.0.1",dst="48.0.0.1")/UDP(dport=12,sport=1025)/IP()/'a_payload_example',
                                vm = vm)
            
            stream = STLStream(name = 'burst',
                               packet = pkt,
                               mode = STLTXSingleBurst(total_pkts = pkt_count,
                                                       percentage = self.percentage)
                               )
            
            self.c.add_streams(ports = self.tx_port, streams = [stream])
            
            self.c.start(ports = self.tx_port, force = True)
            self.c.wait_on_traffic(ports = self.tx_port)
            
            pkt_list = []
            self.c.stop_capture(rc['id'], output = pkt_list)
            
            assert (len(pkt_list) == pkt_count)
            
            # generate all the values that should be
            expected_src_ips = [ip_add('16.0.0.0', i * 7) for i in range(pkt_count)]
            
            for i, pkt in enumerate(pkt_list):
                pkt_scapy = Ether(pkt['binary'])
                pkt_ts    = pkt['ts']
                
                assert('IP' in pkt_scapy)
                assert(pkt_scapy['IP'].src in expected_src_ips)
                
                # remove the match
                del expected_src_ips[expected_src_ips.index(pkt_scapy['IP'].src)]
                
            
        except STLError as e:
            assert False , '{0}'.format(e)
            
        finally:
            self.c.remove_all_captures()
            self.c.set_service_mode(ports = self.rx_port, enabled = False)

            
    
            
    # in this test we apply captures under traffic multiple times
    def test_stress_capture (self):
        pkt_count = 100
        
        try:
            # move to service mode
            self.c.set_service_mode(ports = self.rx_port)
            
            # start heavy traffic
            pkt = STLPktBuilder(pkt = Ether()/IP(src="16.0.0.1",dst="48.0.0.1")/UDP(dport=12,sport=1025)/IP()/'a_payload_example')
            
            stream = STLStream(name = 'burst',
                               packet = pkt,
                               mode = STLTXCont(percentage = self.percentage)
                               )
            
            self.c.add_streams(ports = self.tx_port, streams = [stream])
            self.c.start(ports = self.tx_port, force = True)
            captures = [{'capture_id': None, 'limit': 50}, {'capture_id': None, 'limit': 80}, {'capture_id': None, 'limit': 100}]
            
            for i in range(0, 100):
                # start a few captures
                for capture in captures:
                    capture['capture_id'] = self.c.start_capture(rx_ports = [self.rx_port], limit = capture['limit'])['id']
                
                # a little time to wait for captures to be full
                wait_iterations = 0
                while True:
                    server_captures = self.c.get_capture_status()
                    counts = ([c['count'] for c in server_captures.values()])
                    if {50, 80, 100} == set(counts):
                        break
                        
                    time.sleep(0.1)
                    wait_iterations += 1
                    assert(wait_iterations <= 5)
                    
                
                for capture in captures:
                    capture_id = capture['capture_id']
                    
                    # make sure the server registers us and we are full
                    assert(capture['capture_id'] in server_captures.keys())
                    assert(server_captures[capture_id]['count'] == capture['limit'])
                    
                    # fetch packets
                    pkt_list = []
                    self.c.stop_capture(capture['capture_id'], pkt_list)
                    assert (len(pkt_list) == capture['limit'])
                
                    # a little sanity per packet
                    for pkt in pkt_list:
                        scapy_pkt = Ether(pkt['binary'])
                        assert(scapy_pkt['IP'].src == '16.0.0.1')
                        assert(scapy_pkt['IP'].dst == '48.0.0.1')
              
        except STLError as e:
            assert False , '{0}'.format(e)
            
        finally:
            self.c.remove_all_captures()
            self.c.set_service_mode(ports = self.rx_port, enabled = False)
            
    
    # in this test we capture and analyze the ARP request / response
    def test_arp_capture (self):
        if self.c.get_port_attr(self.tx_port)['layer_mode'] != 'IPv4':
            return self.skip('skipping ARP capture test for non-ipv4 config on port {0}'.format(self.tx_port))
            
        if self.c.get_port_attr(self.rx_port)['layer_mode'] != 'IPv4':
            return self.skip('skipping ARP capture test for non-ipv4 config on port {0}'.format(self.rx_port))
            
        try:
            # move to service mode
            self.c.set_service_mode(ports = [self.tx_port, self.rx_port])
                                                                        
            # start a capture
            capture_info = self.c.start_capture(rx_ports = [self.tx_port, self.rx_port], limit = 2)
         
            # generate an ARP request
            self.c.arp(ports = self.tx_port)
            
            pkts = []
            self.c.stop_capture(capture_info['id'], output = pkts)
        
            assert len(pkts) == 2
            
            # find the correct order
            if pkts[0]['port'] == self.rx_port:
                request  = pkts[0]
                response = pkts[1]
            else:
                request  = pkts[1]
                response = pkts[0]
            
            assert request['port']  == self.rx_port
            assert response['port'] == self.tx_port
            
            arp_request, arp_response = Ether(request['binary']), Ether(response['binary'])
            assert 'ARP' in arp_request
            assert 'ARP' in arp_response
            
            assert arp_request['ARP'].op  == 1
            assert arp_response['ARP'].op == 2
            
            assert arp_request['ARP'].pdst == arp_response['ARP'].psrc
            
            
        except STLError as e:
            assert False , '{0}'.format(e)
            
        finally:
             self.c.remove_all_captures()
             self.c.set_service_mode(ports = [self.tx_port, self.rx_port], enabled = False)

             
    # test PING
    def test_ping_capture (self):
        if self.c.get_port_attr(self.tx_port)['layer_mode'] != 'IPv4':
            return self.skip('skipping ARP capture test for non-ipv4 config on port {0}'.format(self.tx_port))
            
        if self.c.get_port_attr(self.rx_port)['layer_mode'] != 'IPv4':
            return self.skip('skipping ARP capture test for non-ipv4 config on port {0}'.format(self.rx_port))
            
        try:
            # move to service mode
            self.c.set_service_mode(ports = [self.tx_port, self.rx_port])

            # start a capture
            capture_info = self.c.start_capture(rx_ports = [self.tx_port, self.rx_port], limit = 100)

            # generate an ARP request
            tx_ipv4 = self.c.get_port_attr(port = self.tx_port)['src_ipv4']
            rx_ipv4 = self.c.get_port_attr(port = self.rx_port)['src_ipv4']
            
            count = 50
            
            self.c.ping_ip(src_port = self.tx_port, dst_ip = rx_ipv4, pkt_size = 1500, count = count, interval_sec = 0.01)

            pkts = []
            self.c.stop_capture(capture_info['id'], output = pkts)

            req_pkts = [Ether(pkt['binary']) for pkt in pkts if pkt['port'] == self.rx_port]
            res_pkts = [Ether(pkt['binary']) for pkt in pkts if pkt['port'] == self.tx_port]
            assert len(req_pkts) == count
            assert len(res_pkts) == count
            
            for req_pkt in req_pkts:
                assert 'ICMP' in req_pkt
                assert req_pkt['IP'].src == tx_ipv4
                assert req_pkt['IP'].dst == rx_ipv4
                assert req_pkt['ICMP'].type == 8
                assert len(req_pkt) == 1500
                
            for res_pkt in res_pkts:
                assert 'ICMP' in res_pkt
                assert res_pkt['IP'].src == rx_ipv4
                assert res_pkt['IP'].dst == tx_ipv4
                assert res_pkt['ICMP'].type == 0
                assert len(res_pkt) == 1500

                
        except STLError as e:
            assert False , '{0}'.format(e)

        finally:
             self.c.remove_all_captures()
             self.c.set_service_mode(ports = [self.tx_port, self.rx_port], enabled = False)


