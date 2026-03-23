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

# Map each Mininet node name to its FRR config directory
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
FRR_ZEBRA   = '/usr/lib/frr/zebra'
FRR_ISIS    = '/usr/lib/frr/isisd'
FRR_BGP     = '/usr/lib/frr/bgpd'


def start_frr(net):
    """Start FRR daemons on all nodes."""

    print('\n*** Starting FRR daemons on all nodes')
    print('    Config dir:', CONFIGS_DIR)

    for node_name, config_dir in FRR_CONFIGS.items():
        node = net.get(node_name)
        cfg_path = os.path.join(CONFIGS_DIR, config_dir, 'frr.conf')

        if not os.path.exists(cfg_path):
            print(f'  [SKIP] {node_name}: config not found at {cfg_path}')
            continue

        # Runtime dirs per node
        run_dir  = f'/tmp/frr/{node_name}'
        log_dir  = f'/tmp/frr_logs/{node_name}'
        node.cmd(f'mkdir -p {run_dir} {log_dir}')

        # ── Zebra (must start first) ──────────────────────────
        node.cmd(
            f'{FRR_ZEBRA} '
            f'--config_file {cfg_path} '
            f'--pid_file {run_dir}/zebra.pid '
            f'--socket {run_dir}/zserv.api '
            f'--log file:{log_dir}/zebra.log '
            f'-d'
        )

        # ── IS-IS ─────────────────────────────────────────────
        node.cmd(
            f'{FRR_ISIS} '
            f'--config_file {cfg_path} '
            f'--pid_file {run_dir}/isisd.pid '
            f'--socket {run_dir}/zserv.api '
            f'--log file:{log_dir}/isisd.log '
            f'-d'
        )

        # ── BGP (only on ASBR nodes) ──────────────────────────
        if 'asbr' in node_name:
            node.cmd(
                f'{FRR_BGP} '
                f'--config_file {cfg_path} '
                f'--pid_file {run_dir}/bgpd.pid '
                f'--socket {run_dir}/zserv.api '
                f'--log file:{log_dir}/bgpd.log '
                f'-d'
            )

        print(f'  [OK] {node_name}')

    print('\n*** Waiting 15s for IS-IS adjacencies to form...')
    time.sleep(15)
    print('*** FRR startup complete\n')


def verify_isis(net):
    """Check IS-IS adjacency on key nodes."""
    print('\n*** Verifying IS-IS adjacencies')
    check_nodes = ['a_r1', 'b_r2', 'c_r1']
    for node_name in check_nodes:
        node = net.get(node_name)
        result = node.cmd(
            f'vtysh -N {node_name} '
            f'--socket /tmp/frr/{node_name}/zserv.api '
            f'-c "show isis neighbor"'
        )
        adj_count = result.count('Up')
        print(f'  {node_name}: {adj_count} IS-IS adjacency(ies) Up')
        if adj_count == 0:
            print(f'    WARNING: No adjacencies on {node_name}')


def verify_bgp(net):
    """Check eBGP sessions on ASBR nodes."""
    print('\n*** Verifying eBGP sessions')
    asbr_nodes = ['a_asbr1', 'a_asbr2', 'b_asbr1', 'b_asbr2',
                  'b_asbr3', 'b_asbr4', 'c_asbr1', 'c_asbr2']
    for node_name in asbr_nodes:
        node = net.get(node_name)
        result = node.cmd(
            f'vtysh -N {node_name} '
            f'--socket /tmp/frr/{node_name}/zserv.api '
            f'-c "show bgp summary"'
        )
        established = result.count('Established')
        print(f'  {node_name}: {established} BGP session(s) Established')


if __name__ == '__main__':
    print('Run this from inside Mininet or import start_frr(net)')
