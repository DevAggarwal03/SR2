#!/usr/bin/env python3
"""
start_frr.py — Start FRR daemons on all Mininet nodes
======================================================
Run this INSIDE Mininet after topology.py is running:
  mininet> py exec(open('/root/sr-testbed/scripts/start_frr.py').read())

Or call start_frr(net) from topology.py directly.
"""

import os
import time

FRR_CONFIGS = {
    'a_pe1':   'a_pe1',
    'a_r1':    'a_r1',
    'a_r2':    'a_r2',
    'a_asbr1': 'a_asbr1',
    'a_asbr2': 'a_asbr2',
    'b_r1':    'b_r1',
    'b_r2':    'b_r2',
    'b_r3':    'b_r3',
    'b_asbr1': 'b_asbr1',
    'b_asbr2': 'b_asbr2',
    'b_asbr3': 'b_asbr3',
    'b_asbr4': 'b_asbr4',
    'c_pe1':   'c_pe1',
    'c_r1':    'c_r1',
    'c_r2':    'c_r2',
    'c_asbr1': 'c_asbr1',
    'c_asbr2': 'c_asbr2',
}

CONFIGS_DIR = '/root/sr-testbed/configs/frr'
RUN_DIR     = '/tmp/frr'
LOG_DIR     = '/tmp/frr_logs'
FRR_MGMT    = '/usr/lib/frr/mgmtd'
FRR_ZEBRA   = '/usr/lib/frr/zebra'
FRR_ISIS    = '/usr/lib/frr/isisd'
FRR_BGP     = '/usr/lib/frr/bgpd'
VTYSH       = '/usr/bin/vtysh'

ASBR_NODES = {
    'a_asbr1', 'a_asbr2',
    'b_asbr1', 'b_asbr2', 'b_asbr3', 'b_asbr4',
    'c_asbr1', 'c_asbr2',
}


def start_frr(net):
    """Start FRR daemons on all nodes."""

    print('\n*** Starting FRR daemons on all nodes')
    print('    Config dir:', CONFIGS_DIR)

    for node_name, config_dir in FRR_CONFIGS.items():
        node = net.get(node_name)
        cfg = os.path.join(CONFIGS_DIR, config_dir, 'frr.conf')

        if not os.path.exists(cfg):
            print(f'  [SKIP] {node_name}: config not found at {cfg}')
            continue

        node_run = f'{RUN_DIR}/{node_name}'
        node_log = f'{LOG_DIR}/{node_name}'
        node.cmd(f'mkdir -p {node_run} {node_log}')

        # mgmtd (must start first in FRR 10.x)
        node.cmd(
            f'{FRR_MGMT} -f {cfg} '
            f'-u root -g root '
            f'-i {node_run}/mgmtd.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/mgmtd.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.5)

        # Zebra
        node.cmd(
            f'{FRR_ZEBRA} -f {cfg} '
            f'-u root -g root '
            f'-i {node_run}/zebra.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/zebra.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.3)

        # IS-IS
        node.cmd(
            f'{FRR_ISIS} -f {cfg} '
            f'-u root -g root '
            f'-i {node_run}/isisd.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/isisd.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.5)

        # BGP (ASBRs only)
        if node_name in ASBR_NODES:
            node.cmd(
                f'{FRR_BGP} -f {cfg} '
                f'-u root -g root '
                f'-i {node_run}/bgpd.pid '
                f'-z {node_run}/zserv.api '
                f'--vty_socket {node_run} '
                f'--log file:{node_log}/bgpd.log '
                f'--log-level informational -d 2>/dev/null'
            )
        time.sleep(0.3)

        # Push config via vtysh
        node.cmd(
            f'{VTYSH} --vty_socket {node_run}/ '
            f'-f {cfg} 2>/dev/null'
        )
        print(f'  [OK] {node_name}')

    print('\n*** Waiting 30s for IS-IS convergence...')
    time.sleep(30)
    print('*** FRR startup complete\n')


def verify_isis(net):
    """Check IS-IS adjacency on all nodes."""
    print('\n*** Verifying IS-IS adjacencies')
    for node_name in FRR_CONFIGS.keys():
        node = net.get(node_name)
        result = node.cmd(
            f'{VTYSH} --vty_socket {RUN_DIR}/{node_name}/ '
            f'-c "show isis neighbor" 2>/dev/null'
        )
        adj_count = result.count('Up')
        status = '✓' if adj_count > 0 else '✗'
        print(f'  {status} {node_name}: {adj_count} IS-IS adjacency(ies) Up')


def verify_bgp(net):
    """Check eBGP sessions on ASBR nodes."""
    print('\n*** Verifying eBGP sessions')
    for node_name in ASBR_NODES:
        node = net.get(node_name)
        result = node.cmd(
            f'{VTYSH} --vty_socket {RUN_DIR}/{node_name}/ '
            f'-c "show bgp summary" 2>/dev/null'
        )
        established = 'Estab' in result or 'Established' in result
        status = '✓' if established else '✗'
        print(f'  {status} {node_name}: {"Established" if established else "not established"}')


if __name__ == '__main__':
    print('Run this from inside Mininet or import start_frr(net)')
