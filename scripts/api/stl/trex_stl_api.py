import os
import sys
import time


# update the import path to include the stateless client
root_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(root_path, '../../automation/trex_control_plane/'))
sys.path.insert(0, os.path.join(root_path, '../../stl/'))

# aliasing
import common.trex_streams
from client_utils.packet_builder import CTRexPktBuilder
import common.trex_stl_exceptions
import client.trex_stateless_client
import client.trex_stateless_sim

# client and errors
STLClient              = client.trex_stateless_client.STLClient
STLError               = common.trex_stl_exceptions.STLError

# streams
STLStream              = common.trex_streams.STLStream
STLTXCont              = common.trex_streams.STLTXCont
STLTXSingleBurst       = common.trex_streams.STLTXSingleBurst
STLTXMultiBurst        = common.trex_streams.STLTXMultiBurst

# packet builder
STLPktBuilder          = CTRexPktBuilder

# simulator
STLSim                 = client.trex_stateless_sim.STLSim


