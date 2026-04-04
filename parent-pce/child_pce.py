#!/usr/bin/env python3
"""
child_pce.py — Child PCE for Multi-Domain SR Testbed
=====================================================
Research: Privacy-Preserving Dynamic Re-computation for Multi-Domain SR

One instance of this script runs per domain (A, B, or C).
It reads IS-IS topology from FRR via vtysh, computes ADSO abstract metrics,
applies threshold triggering logic, and sends ADSO notifications to the
Parent PCE over a real TCP socket.

This replaces OpenDaylight as the Child PCE. No ODL required.

Usage (run inside each Mininet node's network namespace, or on the host):
  # Domain A — using a_asbr1 as the monitoring node
  python3 child_pce.py --domain A --asbr a_asbr1 --parent-host 127.0.0.1 --parent-port 9100

  # Domain B
  python3 child_pce.py --domain B --asbr b_asbr1 --parent-host 127.0.0.1 --parent-port 9100

  # Domain C
  python3 child_pce.py --domain C --asbr c_asbr1 --parent-host 127.0.0.1 --parent-port 9100

Architecture:
  FRR (vtysh) ──poll──► ChildPCE ──ADSO/TCP──► ParentPCE (parent_pce_server.py)

Inside Mininet, run from the host with:
  mininet> a_asbr1 python3 child_pce.py --domain A --asbr a_asbr1 &
"""

import argparse
import json
import logging
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)


def get_logger(domain: str):
    logger = logging.getLogger(f'ChildPCE-{domain}')
    return logger


# ─────────────────────────────────────────────
#  ADSO Wire Format
#  Simple binary TLV over TCP, 40 bytes fixed header
#
#  Offset  Size  Field
#  0       4     Magic (0xADSO = 0xAD500001)
#  4       1     Domain ID (ASCII: 'A', 'B', 'C')
#  5       3     Reserved (padding)
#  8       8     Timestamp (double, seconds since epoch)
#  16      4     min_delay_ms (float)
#  20      4     max_bandwidth_mbps (float)
#  24      4     max_sid_depth (uint32)
#  28      4     packet_loss_rate (float, 0.0–1.0)
#  32      1     asbr_reachable (uint8, 0 or 1)
#  33      7     Reserved
#  Total: 40 bytes
# ─────────────────────────────────────────────

ADSO_MAGIC  = 0xAD500001
ADSO_FORMAT = '!I c 3x d f f I f B 7x'   # network byte order
ADSO_SIZE   = struct.calcsize(ADSO_FORMAT) # should be 40


def encode_adso(domain_id: str, min_delay_ms: float, max_bw_mbps: float,
                max_sid_depth: int, loss_rate: float, asbr_reachable: bool) -> bytes:
    """Encode ADSO metrics into a 40-byte binary message."""
    return struct.pack(
        ADSO_FORMAT,
        ADSO_MAGIC,
        domain_id.encode('ascii'),
        time.time(),
        float(min_delay_ms),
        float(max_bw_mbps),
        int(max_sid_depth),
        float(loss_rate),
        int(asbr_reachable),
    )


def decode_adso(data: bytes) -> Optional[dict]:
    """Decode a 40-byte ADSO message. Returns None on error."""
    if len(data) < ADSO_SIZE:
        return None
    try:
        fields = struct.unpack(ADSO_FORMAT, data[:ADSO_SIZE])
        magic, domain_b, ts, delay, bw, sid, loss, reachable = fields
        if magic != ADSO_MAGIC:
            return None
        return {
            'domain_id':         domain_b.decode('ascii'),
            'timestamp':         ts,
            'min_delay_ms':      delay,
            'max_bandwidth_mbps': bw,
            'max_sid_depth':     sid,
            'packet_loss_rate':  loss,
            'asbr_reachable':    bool(reachable),
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  FRR Query Layer
#  Reads real topology state from FRR via vtysh
# ─────────────────────────────────────────────

# Vtysh socket paths per node — matches workAround.py RUN_DIR layout
RUN_DIR = '/tmp/frr'


def vtysh_cmd(node_name: str, command: str) -> str:
    """
    Run a vtysh command on a given FRR node.
    Uses the per-node socket created by workAround.py.
    Falls back to system vtysh if no per-node socket found.
    """
    socket_dir = f'{RUN_DIR}/{node_name}/'
    try:
        result = subprocess.run(
            ['vtysh', '--vty_socket', socket_dir, '-c', command],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback: try system vtysh directly (works if running inside the namespace)
        try:
            result = subprocess.run(
                ['vtysh', '-c', command],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout
        except Exception:
            return ''


def get_isis_neighbors(node_name: str) -> list:
    """
    Query IS-IS neighbor state from FRR.
    Returns list of neighbor dicts: {system_id, state, interface}
    """
    output = vtysh_cmd(node_name, 'show isis neighbor detail')
    neighbors = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('System Id:') or line.startswith('Area Address'):
            if current:
                neighbors.append(current)
                current = {}
        if 'State:' in line:
            state = 'Up' if 'Up' in line else 'Down'
            current['state'] = state
        if 'Interface:' in line:
            parts = line.split()
            if len(parts) >= 2:
                current['interface'] = parts[1]
        if 'Metric:' in line:
            parts = line.split()
            try:
                current['metric'] = int(parts[1])
            except (ValueError, IndexError):
                current['metric'] = 10
    if current:
        neighbors.append(current)
    return neighbors


def get_isis_topology(node_name: str) -> dict:
    """
    Query IS-IS LSDB to extract topology metrics.
    Returns dict with computed abstract metrics.
    """
    output = vtysh_cmd(node_name, 'show isis topology')
    # Count reachable prefixes and extract hop counts
    reachable = 0
    min_metric = 9999
    for line in output.splitlines():
        if '10.0.' in line or '10.1.' in line or '10.2.' in line or '10.3.' in line:
            reachable += 1
            parts = line.split()
            for part in parts:
                try:
                    m = int(part)
                    if 1 <= m <= 1000:
                        min_metric = min(min_metric, m)
                except ValueError:
                    pass
    return {
        'reachable_prefixes': reachable,
        'min_metric':         min_metric if min_metric < 9999 else 10,
    }


def get_bgp_neighbor_state(node_name: str, peer_ip: str) -> str:
    """
    Query eBGP session state for a specific peer.
    Returns 'Established', 'Active', 'Idle', or 'Unknown'.
    """
    output = vtysh_cmd(node_name, f'show bgp neighbor {peer_ip}')
    if 'BGP state = Established' in output:
        return 'Established'
    for state in ['Active', 'Idle', 'Connect', 'OpenSent', 'OpenConfirm']:
        if f'BGP state = {state}' in output:
            return state
    return 'Unknown'


def get_interface_stats(node_name: str, interface: str) -> dict:
    """
    Query interface counters via ip command.
    Returns dict with rx_bytes, tx_bytes, rx_errors, tx_errors.
    """
    try:
        result = subprocess.run(
            ['ip', '-s', 'link', 'show', interface],
            capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.splitlines()
        stats = {'rx_bytes': 0, 'tx_bytes': 0, 'rx_errors': 0, 'tx_errors': 0}
        # ip -s link output: RX line then numbers, TX line then numbers
        for i, line in enumerate(lines):
            if 'RX:' in line and i + 1 < len(lines):
                parts = lines[i + 1].split()
                if len(parts) >= 3:
                    try:
                        stats['rx_bytes']  = int(parts[0])
                        stats['rx_errors'] = int(parts[2])
                    except ValueError:
                        pass
            if 'TX:' in line and i + 1 < len(lines):
                parts = lines[i + 1].split()
                if len(parts) >= 3:
                    try:
                        stats['tx_bytes']  = int(parts[0])
                        stats['tx_errors'] = int(parts[2])
                    except ValueError:
                        pass
        return stats
    except Exception:
        return {'rx_bytes': 0, 'tx_bytes': 0, 'rx_errors': 0, 'tx_errors': 0}


def measure_link_delay(node_name: str, peer_ip: str, count: int = 3) -> float:
    """
    Measure round-trip delay to a peer using ping.
    Returns average RTT/2 in ms (one-way estimate).
    """
    try:
        result = subprocess.run(
            ['ping', '-c', str(count), '-W', '1', '-q', peer_ip],
            capture_output=True, text=True, timeout=10
        )
        # Parse: rtt min/avg/max/mdev = 0.123/0.456/0.789/0.100 ms
        for line in result.stdout.splitlines():
            if 'rtt min/avg/max' in line or 'round-trip' in line:
                parts = line.split('=')
                if len(parts) >= 2:
                    vals = parts[1].strip().split('/')
                    try:
                        avg_rtt = float(vals[1])
                        return avg_rtt / 2.0  # one-way estimate
                    except (ValueError, IndexError):
                        pass
        return 2.0  # default: 2ms (intra-domain link baseline)
    except Exception:
        return 2.0


# ─────────────────────────────────────────────
#  Abstract Metric Computation
#  Derives ADSO 5 metrics from real FRR data
#  WITHOUT exposing internal topology details
# ─────────────────────────────────────────────

# Domain-specific ASBR nodes and their eBGP peers
DOMAIN_CONFIG = {
    'A': {
        'asbr_nodes':  ['a_asbr1', 'a_asbr2'],
        'asbr_peers':  {'a_asbr1': '10.100.12.2', 'a_asbr2': '10.100.12.6'},
        'ebgp_intfs':  {'a_asbr1': 'a_asbr1-eth1', 'a_asbr2': 'a_asbr2-eth1'},
        'srgb_base':   16000,
        'max_sid_depth': 8,
    },
    'B': {
        'asbr_nodes':  ['b_asbr1', 'b_asbr2', 'b_asbr3', 'b_asbr4'],
        'asbr_peers':  {
            'b_asbr1': '10.100.12.1', 'b_asbr2': '10.100.12.5',
            'b_asbr3': '10.100.23.2', 'b_asbr4': '10.100.23.6',
        },
        'ebgp_intfs': {
            'b_asbr1': 'b_asbr1-eth1', 'b_asbr2': 'b_asbr2-eth1',
            'b_asbr3': 'b_asbr3-eth1', 'b_asbr4': 'b_asbr4-eth1',
        },
        'srgb_base':   17000,
        'max_sid_depth': 8,
    },
    'C': {
        'asbr_nodes':  ['c_asbr1', 'c_asbr2'],
        'asbr_peers':  {'c_asbr1': '10.100.23.1', 'c_asbr2': '10.100.23.5'},
        'ebgp_intfs':  {'c_asbr1': 'c_asbr1-eth1', 'c_asbr2': 'c_asbr2-eth1'},
        'srgb_base':   18000,
        'max_sid_depth': 8,
    },
}


def compute_abstract_metrics(domain_id: str, primary_asbr: str, log) -> dict:
    """
    Compute the 5 ADSO abstract metrics from live FRR data.

    The key privacy property: these metrics summarise domain health
    without revealing which specific link, node, or prefix caused the change.

    Metric 1 — min_delay_ms:
        Measured as the minimum RTT/2 to the eBGP peer across all ASBRs.
        Reflects domain transit delay without exposing internal hops.

    Metric 2 — max_bandwidth_mbps:
        Estimated from IS-IS metric and interface capacity.
        500 Mbps baseline (inter-AS link capacity) reduced by congestion proxy.

    Metric 3 — max_sid_depth:
        Fixed at 8 unless IS-IS SR MSD changes (from 'show isis segment-routing node').

    Metric 4 — packet_loss_rate:
        Derived from interface error counters on the eBGP-facing interface.
        Ratio of errors to total frames in the last sample window.

    Metric 5 — asbr_reachable:
        True if at least one eBGP session is Established.
        Binary — only discloses up/down state, never internal cause.
    """
    cfg  = DOMAIN_CONFIG[domain_id]
    log.debug(f'Computing abstract metrics for domain {domain_id}')

    # ── Metric 5: ASBR reachability (binary) ──────────────────────────
    bgp_states = {}
    for node, peer in cfg['asbr_peers'].items():
        state = get_bgp_neighbor_state(node, peer)
        bgp_states[node] = state
        log.debug(f'  {node} → {peer}: {state}')

    asbr_reachable = any(s == 'Established' for s in bgp_states.values())

    # ── Metric 1: min_delay_ms ────────────────────────────────────────
    delays = []
    for node, peer in cfg['asbr_peers'].items():
        if bgp_states.get(node) == 'Established':
            d = measure_link_delay(node, peer, count=2)
            delays.append(d)

    if delays:
        min_delay_ms = min(delays)
    else:
        # No established session → use a high delay to signal degradation
        min_delay_ms = 50.0

    # ── Metric 2: max_bandwidth_mbps ──────────────────────────────────
    # Use interface error rate as a congestion proxy
    # Bandwidth = nominal_bw × (1 - error_fraction)
    nominal_bw  = 500.0  # Mbps — inter-AS link capacity from topology
    error_fracs = []
    for node, intf in cfg['ebgp_intfs'].items():
        stats = get_interface_stats(node, intf)
        total = stats['rx_bytes'] + stats['tx_bytes']
        errs  = stats['rx_errors'] + stats['tx_errors']
        if total > 0:
            error_fracs.append(errs / max(total, 1))

    if error_fracs:
        avg_error_frac = sum(error_fracs) / len(error_fracs)
    else:
        avg_error_frac = 0.0

    # Also reduce bandwidth if BGP sessions are down
    active_fraction = sum(1 for s in bgp_states.values() if s == 'Established') / max(len(bgp_states), 1)
    max_bandwidth_mbps = nominal_bw * active_fraction * (1.0 - min(avg_error_frac * 100, 0.9))

    # ── Metric 3: max_sid_depth ────────────────────────────────────────
    # Read from IS-IS SR node MSD — uses primary ASBR node
    sid_output = vtysh_cmd(primary_asbr, 'show isis segment-routing node')
    max_sid_depth = cfg['max_sid_depth']  # default
    for line in sid_output.splitlines():
        if 'MSD' in line or 'Node MSD' in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p in ('MSD:', 'MSD') and i + 1 < len(parts):
                    try:
                        max_sid_depth = int(parts[i + 1])
                    except ValueError:
                        pass

    # ── Metric 4: packet_loss_rate ────────────────────────────────────
    # Derived from interface error counters (same data as bw, different view)
    # Expressed as a fraction 0.0–1.0
    if error_fracs:
        packet_loss_rate = min(sum(error_fracs) / len(error_fracs), 1.0)
    elif not asbr_reachable:
        packet_loss_rate = 1.0
    else:
        packet_loss_rate = 0.0

    return {
        'domain_id':          domain_id,
        'timestamp':          time.time(),
        'min_delay_ms':       round(min_delay_ms, 2),
        'max_bandwidth_mbps': round(max_bandwidth_mbps, 1),
        'max_sid_depth':      max_sid_depth,
        'packet_loss_rate':   round(packet_loss_rate, 4),
        'asbr_reachable':     asbr_reachable,
        # Internal diagnostics — NEVER sent to Parent PCE
        '_bgp_states':        bgp_states,
        '_active_fraction':   active_fraction,
    }


# ─────────────────────────────────────────────
#  ADSO Triggering Logic (Child PCE side)
#  Mirrors the ADSOTrigger class in parent_pce.py
#  Decision is made here — Parent PCE only sees
#  notifications that crossed a threshold.
# ─────────────────────────────────────────────

class ChildTrigger:
    DELAY_ABSOLUTE_MS  = 8.0    # ms
    BW_RELATIVE_DROP   = 0.20   # 20%
    LOSS_ABSOLUTE      = 0.05   # 5%
    RATE_LIMIT_S       = 0.500  # 500ms

    def __init__(self, domain_id: str, log):
        self.domain_id  = domain_id
        self.log        = log
        self.last_sent  = 0.0
        self.last_m     = None

    def check(self, m: dict) -> tuple:
        """
        Returns (should_send: bool, reasons: list[str])
        """
        now     = time.time()
        reasons = []

        # Rate limiter
        if now - self.last_sent < self.RATE_LIMIT_S:
            return False, ['rate_limited']

        prev = self.last_m

        # Threshold 1: absolute delay
        if m['min_delay_ms'] > self.DELAY_ABSOLUTE_MS:
            reasons.append(
                f"delay_threshold:{m['min_delay_ms']:.1f}ms>{self.DELAY_ABSOLUTE_MS}ms"
            )

        # Threshold 2a: relative bandwidth DROP
        if prev and prev['max_bandwidth_mbps'] > 0:
            drop = (prev['max_bandwidth_mbps'] - m['max_bandwidth_mbps']) / prev['max_bandwidth_mbps']
            if drop > self.BW_RELATIVE_DROP:
                reasons.append(
                    f"bw_drop:{drop*100:.1f}%"
                    f"({prev['max_bandwidth_mbps']:.0f}→{m['max_bandwidth_mbps']:.0f}Mbps)"
                )

        # Threshold 2b: relative bandwidth RECOVERY (S4 scenario)
        if prev and prev['max_bandwidth_mbps'] > 0:
            recovery = (m['max_bandwidth_mbps'] - prev['max_bandwidth_mbps']) / prev['max_bandwidth_mbps']
            if recovery > self.BW_RELATIVE_DROP:
                reasons.append(
                    f"bw_recovery:{recovery*100:.1f}%"
                    f"({prev['max_bandwidth_mbps']:.0f}→{m['max_bandwidth_mbps']:.0f}Mbps)"
                )

        # Threshold 3: absolute loss
        if m['packet_loss_rate'] > self.LOSS_ABSOLUTE:
            reasons.append(
                f"loss_threshold:{m['packet_loss_rate']*100:.1f}%>{self.LOSS_ABSOLUTE*100:.1f}%"
            )

        # Threshold 3b: loss RECOVERY
        if prev and prev['packet_loss_rate'] > self.LOSS_ABSOLUTE and m['packet_loss_rate'] <= self.LOSS_ABSOLUTE:
            reasons.append(
                f"loss_recovery:{prev['packet_loss_rate']*100:.1f}%→{m['packet_loss_rate']*100:.1f}%"
            )

        # Threshold 1b: delay RECOVERY
        if prev and prev.get('min_delay_ms', 0) > self.DELAY_ABSOLUTE_MS and m['min_delay_ms'] <= self.DELAY_ABSOLUTE_MS:
            reasons.append(
                f"delay_recovery:{prev['min_delay_ms']:.1f}ms→{m['min_delay_ms']:.1f}ms"
            )

        # Threshold 4: ASBR binary state change
        if prev and prev['asbr_reachable'] != m['asbr_reachable']:
            state = 'DOWN' if not m['asbr_reachable'] else 'UP'
            reasons.append(f"asbr_state_change:ASBR now {state}")

        if reasons:
            self.last_sent = now
            self.last_m    = m
            return True, reasons

        self.last_m = m
        return False, []


# ─────────────────────────────────────────────
#  TCP Connection to Parent PCE
# ─────────────────────────────────────────────

class ParentPCEConnection:
    """
    Persistent TCP connection to the Parent PCE.
    Reconnects automatically on failure.
    """

    def __init__(self, host: str, port: int, log):
        self.host   = host
        self.port   = port
        self.log    = log
        self.sock   = None
        self._connect()

    def _connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                self.log.info(f'Connected to Parent PCE at {self.host}:{self.port}')
                return
            except ConnectionRefusedError:
                self.log.warning(f'Parent PCE not ready at {self.host}:{self.port} — retrying in 2s')
                time.sleep(2)
            except Exception as e:
                self.log.error(f'Connection error: {e} — retrying in 3s')
                time.sleep(3)

    def send_adso(self, metrics: dict) -> bool:
        """
        Send an ADSO notification to the Parent PCE.
        Returns True on success, False on failure (caller should retry).
        """
        payload = encode_adso(
            domain_id     = metrics['domain_id'],
            min_delay_ms  = metrics['min_delay_ms'],
            max_bw_mbps   = metrics['max_bandwidth_mbps'],
            max_sid_depth = metrics['max_sid_depth'],
            loss_rate     = metrics['packet_loss_rate'],
            asbr_reachable= metrics['asbr_reachable'],
        )
        try:
            self.sock.sendall(payload)
            self.log.info(
                f'ADSO sent to Parent PCE: '
                f"delay={metrics['min_delay_ms']}ms "
                f"bw={metrics['max_bandwidth_mbps']}Mbps "
                f"loss={metrics['packet_loss_rate']*100:.1f}% "
                f"asbr={'UP' if metrics['asbr_reachable'] else 'DOWN'}"
            )
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            self.log.warning(f'Send failed ({e}), reconnecting...')
            self._connect()
            return False

    def close(self):
        if self.sock:
            self.sock.close()


# ─────────────────────────────────────────────
#  Child PCE Main Loop
# ─────────────────────────────────────────────

class ChildPCE:

    POLL_INTERVAL_S = 0.5   # Poll FRR every 500ms

    def __init__(self, domain_id: str, primary_asbr: str,
                 parent_host: str, parent_port: int):
        self.domain_id    = domain_id
        self.primary_asbr = primary_asbr
        self.log          = get_logger(domain_id)
        self.trigger      = ChildTrigger(domain_id, self.log)
        self.conn         = ParentPCEConnection(parent_host, parent_port, self.log)
        self.running      = False

        # Stats
        self.polls_done    = 0
        self.notifs_sent   = 0
        self.notifs_blocked= 0

    def run(self):
        """
        Main polling loop.
        Polls FRR every POLL_INTERVAL_S seconds, computes abstract metrics,
        applies threshold logic, sends ADSO to Parent PCE if needed.
        """
        self.running = True
        self.log.info(
            f'Child PCE started — domain={self.domain_id} '
            f'asbr={self.primary_asbr} '
            f'poll={self.POLL_INTERVAL_S}s'
        )

        while self.running:
            t_poll_start = time.time()

            try:
                # Step 1: Read real FRR state
                metrics = compute_abstract_metrics(
                    self.domain_id, self.primary_asbr, self.log
                )
                self.polls_done += 1

                # Step 2: Apply threshold logic
                should_send, reasons = self.trigger.check(metrics)

                if should_send:
                    # Step 3: Send ADSO notification (stripping internal diagnostics)
                    clean_metrics = {k: v for k, v in metrics.items() if not k.startswith('_')}
                    self.conn.send_adso(clean_metrics)
                    self.notifs_sent += 1
                    self.log.warning(
                        f'ADSO NOTIFICATION SENT — reasons: {"; ".join(reasons)}'
                    )
                elif reasons == ['rate_limited']:
                    self.notifs_blocked += 1
                    self.log.debug('Notification suppressed by rate limiter')

                # Log stats every 20 polls
                if self.polls_done % 20 == 0:
                    self.log.info(
                        f'Stats: polls={self.polls_done} '
                        f'sent={self.notifs_sent} '
                        f'blocked={self.notifs_blocked}'
                    )

            except Exception as e:
                self.log.error(f'Poll error: {e}')

            # Sleep to maintain poll interval
            elapsed = time.time() - t_poll_start
            sleep_s = max(0, self.POLL_INTERVAL_S - elapsed)
            time.sleep(sleep_s)

    def stop(self):
        self.running = False
        self.conn.close()
        self.log.info(
            f'Child PCE stopped. '
            f'polls={self.polls_done} '
            f'notifs_sent={self.notifs_sent} '
            f'notifs_blocked={self.notifs_blocked}'
        )


# ─────────────────────────────────────────────
#  Failure Injection (for experiments)
#  Simulates link failures by temporarily
#  adding a static bad-metric route or taking
#  down an interface — gives Child PCE real
#  data to detect rather than fake metrics.
# ─────────────────────────────────────────────

def inject_failure_on_node(node_name: str, interface: str, failure_type: str):
    """
    Inject a real failure on a Mininet node by manipulating its network state.
    This causes the Child PCE to detect the failure through real FRR polling.

    failure_type:
      'link_down'   — bring interface down (ASBR unreachable)
      'delay_inject'— add 10ms delay via TC netem
      'bw_limit'    — throttle to 100Mbps via TC tbf
      'restore'     — remove all TC rules and bring interface back up
    """
    if failure_type == 'link_down':
        subprocess.run(['ip', 'link', 'set', interface, 'down'], check=False)

    elif failure_type == 'delay_inject':
        # Add 10ms delay to simulate a congested path
        subprocess.run(
            ['tc', 'qdisc', 'add', 'dev', interface, 'root',
             'netem', 'delay', '10ms'],
            check=False
        )

    elif failure_type == 'bw_limit':
        # Limit to 100Mbps (20% of 500Mbps nominal — triggers relative threshold)
        subprocess.run(
            ['tc', 'qdisc', 'add', 'dev', interface, 'root',
             'tbf', 'rate', '100mbit', 'burst', '32kbit', 'latency', '400ms'],
            check=False
        )

    elif failure_type == 'restore':
        subprocess.run(['tc', 'qdisc', 'del', 'dev', interface, 'root'], check=False)
        subprocess.run(['ip', 'link', 'set', interface, 'up'], check=False)


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Child PCE — reads FRR, sends ADSO to Parent PCE'
    )
    parser.add_argument('--domain',      required=True, choices=['A', 'B', 'C'],
                        help='Domain ID')
    parser.add_argument('--asbr',        required=True,
                        help='Primary ASBR node name (e.g. a_asbr1)')
    parser.add_argument('--parent-host', default='127.0.0.1',
                        help='Parent PCE IP address')
    parser.add_argument('--parent-port', type=int, default=9100,
                        help='Parent PCE TCP port')
    parser.add_argument('--poll',        type=float, default=0.5,
                        help='Poll interval in seconds (default 0.5)')
    parser.add_argument('--inject',      choices=['link_down', 'delay_inject', 'bw_limit', 'restore'],
                        help='Inject a test failure immediately on start')
    parser.add_argument('--inject-intf', default=None,
                        help='Interface to inject failure on (e.g. a_asbr1-eth1)')
    args = parser.parse_args()

    # Optional immediate failure injection (for scripted experiments)
    if args.inject:
        if not args.inject_intf:
            print(f'ERROR: --inject-intf required for --inject {args.inject}')
            sys.exit(1)
        inject_failure_on_node(args.asbr, args.inject_intf, args.inject)
        print(f'Injected {args.inject} on {args.inject_intf}')

    pce = ChildPCE(
        domain_id   = args.domain,
        primary_asbr= args.asbr,
        parent_host = args.parent_host,
        parent_port = args.parent_port,
    )
    pce.POLL_INTERVAL_S = args.poll

    try:
        pce.run()
    except KeyboardInterrupt:
        print('\nShutting down...')
        pce.stop()


if __name__ == '__main__':
    main()
