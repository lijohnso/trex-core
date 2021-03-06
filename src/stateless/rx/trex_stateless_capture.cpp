/*
 Itay Marom
 Cisco Systems, Inc.
*/

/*
Copyright (c) 2015-2016 Cisco Systems, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
#include "trex_stateless_capture.h"
#include "trex_exception.h"

/**************************************
 * Capture
 *  
 * A single instance of a capture
 *************************************/
TrexStatelessCapture::TrexStatelessCapture(capture_id_t id,
                                           uint64_t limit,
                                           const CaptureFilter &filter,
                                           TrexPktBuffer::mode_e mode) {
    m_id         = id;
    m_pkt_buffer = new TrexPktBuffer(limit, mode);
    m_filter     = filter;
    m_state      = STATE_ACTIVE;
    m_start_ts   = now_sec();
    m_pkt_index  = 0;
}

TrexStatelessCapture::~TrexStatelessCapture() {
    if (m_pkt_buffer) {
        delete m_pkt_buffer;
    }
}

void
TrexStatelessCapture::handle_pkt_tx(const TrexPkt *pkt) {

    if (m_state != STATE_ACTIVE) {
        return;
    }
    
    /* if not in filter - back off */
    if (!m_filter.in_filter(pkt)) {
        return;
    }
    
    if (pkt->get_ts() < m_start_ts) {
        return;
    }
    
    m_pkt_buffer->push(pkt, ++m_pkt_index);
}

void
TrexStatelessCapture::handle_pkt_rx(const rte_mbuf_t *m, int port) {

    if (m_state != STATE_ACTIVE) {
        return;
    }
    
    if (!m_filter.in_rx(port)) {
        return;
    }
    
    m_pkt_buffer->push(m, port, TrexPkt::ORIGIN_RX, ++m_pkt_index);
}


Json::Value
TrexStatelessCapture::to_json() const {
    Json::Value output = Json::objectValue;

    output["id"]     = Json::UInt64(m_id);
    output["filter"] = m_filter.to_json();
    output["count"]  = m_pkt_buffer->get_element_count();
    output["bytes"]  = m_pkt_buffer->get_bytes();
    output["limit"]  = m_pkt_buffer->get_capacity();
    
    switch (m_state) {
    case STATE_ACTIVE:
        output["state"]  = "ACTIVE";
        break;
        
    case STATE_STOPPED:
        output["state"]  = "STOPPED";
        break;
        
    default:
        assert(0);
    }
    
    return output;
}

/**
 * fetch up to 'pkt_limit' from the capture
 * 
 */
TrexPktBuffer *
TrexStatelessCapture::fetch(uint32_t pkt_limit, uint32_t &pending) {

    /* if the total sum of packets is within the limit range - take it */
    if (m_pkt_buffer->get_element_count() <= pkt_limit) {
        TrexPktBuffer *current = m_pkt_buffer;
        m_pkt_buffer = new TrexPktBuffer(m_pkt_buffer->get_capacity(), m_pkt_buffer->get_mode());
        pending = 0;
        return current;
    }
    
    /* partial fetch - take a partial list */
    TrexPktBuffer *partial = m_pkt_buffer->pop_n(pkt_limit);
    pending  = m_pkt_buffer->get_element_count();
    
    return partial;
}


/**************************************
 * Capture Manager 
 * handles all the captures 
 * in the system 
 *************************************/

/**
 * holds the global filter in the capture manager 
 * which ports in the entire system are monitored 
 */
void
TrexStatelessCaptureMngr::update_global_filter() {
    CaptureFilter new_filter;
    
    /* recalculates the global filter */
    for (TrexStatelessCapture *capture : m_captures) {
        new_filter += capture->get_filter();
    }
    
    m_global_filter = new_filter;
}


/**
 * lookup a specific capture by ID
 */
TrexStatelessCapture *
TrexStatelessCaptureMngr::lookup(capture_id_t capture_id) {
    
    for (int i = 0; i < m_captures.size(); i++) {
        if (m_captures[i]->get_id() == capture_id) {
            return m_captures[i];
        }
    }
    
    /* does not exist */
    return nullptr;
}


int
TrexStatelessCaptureMngr::lookup_index(capture_id_t capture_id) {
    for (int i = 0; i < m_captures.size(); i++) {
        if (m_captures[i]->get_id() == capture_id) {
            return i;
        }
    }
    return -1;
}


/**
 * starts a new capture
 * 
 */
void
TrexStatelessCaptureMngr::start(const CaptureFilter &filter,
                                uint64_t limit,
                                TrexPktBuffer::mode_e mode,
                                TrexCaptureRCStart &rc) {

    /* check for maximum active captures */
    if (m_captures.size() >= MAX_CAPTURE_SIZE) {
        rc.set_err(TrexCaptureRC::RC_CAPTURE_LIMIT_REACHED);
        return;
    }
    
    /* create a new capture*/
    int new_id = m_id_counter++;
    TrexStatelessCapture *new_capture = new TrexStatelessCapture(new_id, limit, filter, mode);
    m_captures.push_back(new_capture);
 
    /* update global filter */
    update_global_filter();
    
    /* result */
    rc.set_rc(new_id, new_capture->get_start_ts());
}

void
TrexStatelessCaptureMngr::stop(capture_id_t capture_id, TrexCaptureRCStop &rc) {
    TrexStatelessCapture *capture = lookup(capture_id);
    if (!capture) {
        rc.set_err(TrexCaptureRC::RC_CAPTURE_NOT_FOUND);
        return;
    }
    
    capture->stop();
    rc.set_rc(capture->get_pkt_count());
}


void
TrexStatelessCaptureMngr::fetch(capture_id_t capture_id, uint32_t pkt_limit, TrexCaptureRCFetch &rc) {
    TrexStatelessCapture *capture = lookup(capture_id);
    if (!capture) {
        rc.set_err(TrexCaptureRC::RC_CAPTURE_NOT_FOUND);
        return;
    }
    
    uint32_t pending = 0;
    TrexPktBuffer *pkt_buffer = capture->fetch(pkt_limit, pending);
    
    rc.set_rc(pkt_buffer, pending, capture->get_start_ts());
}

void
TrexStatelessCaptureMngr::remove(capture_id_t capture_id, TrexCaptureRCRemove &rc) {
    
    /* lookup index */
    int index = lookup_index(capture_id);
    if (index == -1) {
        rc.set_err(TrexCaptureRC::RC_CAPTURE_NOT_FOUND);
        return;
    }
    
    TrexStatelessCapture *capture =  m_captures[index];
    m_captures.erase(m_captures.begin() + index);
    
    /* free memory */
    delete capture;
    
    /* update global filter */
    update_global_filter();
    
    rc.set_rc();
}

void
TrexStatelessCaptureMngr::reset() {
    TrexCaptureRCRemove dummy;
    
    while (m_captures.size() > 0) {
        remove(m_captures[0]->get_id(), dummy);
        assert(!!dummy);
    }
}

void 
TrexStatelessCaptureMngr::handle_pkt_tx_slow_path(const TrexPkt *pkt) {
    for (TrexStatelessCapture *capture : m_captures) {
        capture->handle_pkt_tx(pkt);
    }
}

void 
TrexStatelessCaptureMngr::handle_pkt_rx_slow_path(const rte_mbuf_t *m, int port) {
    for (TrexStatelessCapture *capture : m_captures) {
        capture->handle_pkt_rx(m, port);
    }
}

Json::Value
TrexStatelessCaptureMngr::to_json() const {
    Json::Value lst = Json::arrayValue;

    for (TrexStatelessCapture *capture : m_captures) {
        lst.append(capture->to_json());
    }

    return lst;
}

