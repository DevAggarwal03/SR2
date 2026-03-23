#!/usr/bin/env python3
"""
topology.py — 3-Domain SR Testbed Topology with FRR
=====================================================
Research: Privacy-Preserving Dynamic Re-computation for Multi-Domain SR

Usage:
  sudo python3 topology.py

Inside Mininet CLI:
  verify_isis   — check IS-IS adjacencies on all nodes
  verify_bgp    — check eBGP sessions on all ASBRs
  verify_sr     — check SR SID allocations
  ping_loopback — end-to-end A-PE1 → C-PE1 test
  frr_status <n>— FRR daemon status for a node
  show_route <n>— IP routing table for a node
  exit          — shut down

Cleanup: sudo mn -c
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Node
from mininet.log import setLogLevel, info, warn
from mininet.cli import CLI as MininetCLI
from mininet.link import TCLink
import os
import time

# ─────────────────────────────────────────────
#  Paths
# ─────────────────────────────────────────────

CONFIGS_DIR = os.path.expanduser('/root/sr-testbed/configs/frr')
RUN_DIR     = '/tmp/frr'
LOG_DIR     = '/tmp/frr_logs'
FRR_ZEBRA   = '/usr/lib/frr/zebra'
FRR_MGMT    = '/usr/lib/frr/mgmtd'
FRR_ISIS    = '/usr/lib/frr/isisd'
FRR_BGP     = '/usr/lib/frr/bgpd'
VTYSH       = '/usr/bin/vtysh'

# ─────────────────────────────────────────────
#  Node definitions
# ─────────────────────────────────────────────

LOOPBACKS = {
    'a_pe1':   ('10.0.1.1',   16001),
    'a_r1':    ('10.0.1.2',   16002),
    'a_r2':    ('10.0.1.3',   16003),
    'a_asbr1': ('10.0.1.254', 16010),
    'a_asbr2': ('10.0.1.253', 16011),
    'b_r1':    ('10.0.2.1',   17001),
    'b_r2':    ('10.0.2.2',   17002),
    'b_r3':    ('10.0.2.3',   17003),
    'b_asbr1': ('10.0.2.251', 17010),
    'b_asbr2': ('10.0.2.252', 17011),
    'b_asbr3': ('10.0.2.253', 17012),
    'b_asbr4': ('10.0.2.254', 17013),
    'c_pe1':   ('10.0.3.1',   18001),
    'c_r1':    ('10.0.3.2',   18002),
    'c_r2':    ('10.0.3.3',   18003),
    'c_asbr1': ('10.0.3.254', 18010),
    'c_asbr2': ('10.0.3.253', 18011),
}

ASBR_NODES = {
    'a_asbr1', 'a_asbr2',
    'b_asbr1', 'b_asbr2', 'b_asbr3', 'b_asbr4',
    'c_asbr1', 'c_asbr2',
}


# ─────────────────────────────────────────────
#  Linux Router Node
# ─────────────────────────────────────────────

class LinuxRouter(Node):

    def config(self, **params):
        super().config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')
        self.cmd('sysctl -w net.mpls.platform_labels=1000')
        self.cmd('sysctl -w net.mpls.conf.lo.input=1')
        for intf in self.intfList():
            if intf.name != 'lo':
                self.cmd(f'sysctl -w net.mpls.conf.{intf.name}.input=1')

    def terminate(self):
        node_run = f'{RUN_DIR}/{self.name}'
        for daemon in ['bgpd', 'isisd', 'zebra', 'mgmtd']:
            self.cmd(
                f'[ -f {node_run}/{daemon}.pid ] && '
                f'kill $(cat {node_run}/{daemon}.pid) 2>/dev/null; true'
            )
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        super().terminate()


# ─────────────────────────────────────────────
#  Topology
# ─────────────────────────────────────────────

class SRTestbedTopo(Topo):

    def build(self):
        intra = dict(cls=TCLink, bw=1000, delay='2ms')
        inter = dict(cls=TCLink, bw=500,  delay='5ms')

        # Domain A
        a_pe1   = self.addNode('a_pe1',   cls=LinuxRouter, ip=None)
        a_r1    = self.addNode('a_r1',    cls=LinuxRouter, ip=None)
        a_r2    = self.addNode('a_r2',    cls=LinuxRouter, ip=None)
        a_asbr1 = self.addNode('a_asbr1', cls=LinuxRouter, ip=None)
        a_asbr2 = self.addNode('a_asbr2', cls=LinuxRouter, ip=None)

        self.addLink(a_pe1,   a_r1,    **intra,
                     params1={'ip': '10.1.1.1/30'},  params2={'ip': '10.1.1.2/30'})
        self.addLink(a_pe1,   a_r2,    **intra,
                     params1={'ip': '10.1.1.5/30'},  params2={'ip': '10.1.1.6/30'})
        self.addLink(a_r1,    a_asbr1, **intra,
                     params1={'ip': '10.1.1.9/30'},  params2={'ip': '10.1.1.10/30'})
        self.addLink(a_r2,    a_asbr2, **intra,
                     params1={'ip': '10.1.1.13/30'}, params2={'ip': '10.1.1.14/30'})
        self.addLink(a_r1,    a_r2,    **intra,
                     params1={'ip': '10.1.1.17/30'}, params2={'ip': '10.1.1.18/30'})

        # Domain B
        b_r1    = self.addNode('b_r1',    cls=LinuxRouter, ip=None)
        b_r2    = self.addNode('b_r2',    cls=LinuxRouter, ip=None)
        b_r3    = self.addNode('b_r3',    cls=LinuxRouter, ip=None)
        b_asbr1 = self.addNode('b_asbr1', cls=LinuxRouter, ip=None)
        b_asbr2 = self.addNode('b_asbr2', cls=LinuxRouter, ip=None)
        b_asbr3 = self.addNode('b_asbr3', cls=LinuxRouter, ip=None)
        b_asbr4 = self.addNode('b_asbr4', cls=LinuxRouter, ip=None)

        self.addLink(b_r1,    b_r2,    **intra,
                     params1={'ip': '10.2.1.1/30'},  params2={'ip': '10.2.1.2/30'})
        self.addLink(b_r2,    b_r3,    **intra,
                     params1={'ip': '10.2.1.5/30'},  params2={'ip': '10.2.1.6/30'})
        self.addLink(b_r1,    b_asbr1, **intra,
                     params1={'ip': '10.2.1.9/30'},  params2={'ip': '10.2.1.10/30'})
        self.addLink(b_r1,    b_asbr2, **intra,
                     params1={'ip': '10.2.1.13/30'}, params2={'ip': '10.2.1.14/30'})
        self.addLink(b_r3,    b_asbr3, **intra,
                     params1={'ip': '10.2.1.17/30'}, params2={'ip': '10.2.1.18/30'})
        self.addLink(b_r3,    b_asbr4, **intra,
                     params1={'ip': '10.2.1.21/30'}, params2={'ip': '10.2.1.22/30'})
        self.addLink(b_r2,    b_r1,    **intra,
                     params1={'ip': '10.2.1.25/30'}, params2={'ip': '10.2.1.26/30'})

        # Domain C
        c_pe1   = self.addNode('c_pe1',   cls=LinuxRouter, ip=None)
        c_r1    = self.addNode('c_r1',    cls=LinuxRouter, ip=None)
        c_r2    = self.addNode('c_r2',    cls=LinuxRouter, ip=None)
        c_asbr1 = self.addNode('c_asbr1', cls=LinuxRouter, ip=None)
        c_asbr2 = self.addNode('c_asbr2', cls=LinuxRouter, ip=None)

        self.addLink(c_pe1,   c_r1,    **intra,
                     params1={'ip': '10.3.1.1/30'},  params2={'ip': '10.3.1.2/30'})
        self.addLink(c_pe1,   c_r2,    **intra,
                     params1={'ip': '10.3.1.5/30'},  params2={'ip': '10.3.1.6/30'})
        self.addLink(c_r1,    c_asbr1, **intra,
                     params1={'ip': '10.3.1.9/30'},  params2={'ip': '10.3.1.10/30'})
        self.addLink(c_r2,    c_asbr2, **intra,
                     params1={'ip': '10.3.1.13/30'}, params2={'ip': '10.3.1.14/30'})
        self.addLink(c_r1,    c_r2,    **intra,
                     params1={'ip': '10.3.1.17/30'}, params2={'ip': '10.3.1.18/30'})

        # Inter-AS eBGP links
        self.addLink(a_asbr1, b_asbr1, **inter,
                     params1={'ip': '10.100.12.1/30'}, params2={'ip': '10.100.12.2/30'})
        self.addLink(a_asbr2, b_asbr2, **inter,
                     params1={'ip': '10.100.12.5/30'}, params2={'ip': '10.100.12.6/30'})
        self.addLink(b_asbr3, c_asbr1, **inter,
                     params1={'ip': '10.100.23.1/30'}, params2={'ip': '10.100.23.2/30'})
        self.addLink(b_asbr4, c_asbr2, **inter,
                     params1={'ip': '10.100.23.5/30'}, params2={'ip': '10.100.23.6/30'})


# ─────────────────────────────────────────────
#  FRR startup
# ─────────────────────────────────────────────

def configure_loopbacks(net):
    info('*** Configuring loopbacks\n')
    for node_name, (lo_ip, _sid) in LOOPBACKS.items():
        node = net.get(node_name)
        node.cmd(f'ip addr add {lo_ip}/32 dev lo')
        node.cmd('ip link set lo up')


def start_frr(net):
    info('*** Starting FRR daemons\n')

    if not os.path.exists(FRR_ZEBRA):
        warn(f'FRR not found at {FRR_ZEBRA}\n')
        return False

    for node_name in LOOPBACKS.keys():
        node     = net.get(node_name)
        cfg      = os.path.join(CONFIGS_DIR, node_name, 'frr.conf')
        node_run = f'{RUN_DIR}/{node_name}'
        node_log = f'{LOG_DIR}/{node_name}'

        if not os.path.exists(cfg):
            warn(f'  [MISSING] {cfg}\n')
            continue


        node.cmd(f'mkdir -p {node_run} {node_log}')

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


        node.cmd(
            f'vtysh --vty_socket {node_run}/ '
            f'-f {cfg} 2>/dev/null'
        )
        info(f'  [OK] {node_name}\n')

    return True


# ─────────────────────────────────────────────
#  Verification
# ─────────────────────────────────────────────

def vtysh(node, node_name, cmd):
    return node.cmd(
        f'{VTYSH} '
        f'--vty_socket {RUN_DIR}/{node_name} '
        f'-c "{cmd}" 2>/dev/null'
    )


def verify_isis(net):
    info('\n*** IS-IS Adjacencies\n')
    nodes = ['a_pe1', 'a_r1', 'a_r2', 'a_asbr1', 'a_asbr2',
             'b_r1', 'b_r2', 'b_r3', 'b_asbr1', 'b_asbr2',
             'b_asbr3', 'b_asbr4', 'c_pe1', 'c_r1', 'c_r2',
             'c_asbr1', 'c_asbr2']
    for n in nodes:
        result = vtysh(net.get(n), n, 'show isis neighbor')
        up = result.count('Up')
        info(f'  {"✓" if up > 0 else "✗"} {n}: {up} neighbor(s)\n')


def verify_bgp(net):
    info('\n*** eBGP Sessions\n')
    pairs = [
        ('a_asbr1', '10.100.12.2'), ('a_asbr2', '10.100.12.6'),
        ('b_asbr1', '10.100.12.1'), ('b_asbr2', '10.100.12.5'),
        ('b_asbr3', '10.100.23.2'), ('b_asbr4', '10.100.23.6'),
        ('c_asbr1', '10.100.23.1'), ('c_asbr2', '10.100.23.5'),
    ]
    for n, peer in pairs:
        result = vtysh(net.get(n), n, f'show bgp neighbor {peer}')
        up = 'BGP state = Established' in result
        info(f'  {"✓" if up else "✗"} {n} → {peer}: '
             f'{"Established" if up else "not established"}\n')


def verify_sr(net):
    info('\n*** SR-MPLS SIDs\n')
    for n, (lo, sid) in LOOPBACKS.items():
        result = vtysh(net.get(n), n, 'show isis segment-routing node')
        found = str(sid) in result
        info(f'  {"✓" if found else "?"} {n}: {lo} SID={sid}\n')


# ─────────────────────────────────────────────
#  Extended CLI
# ─────────────────────────────────────────────

class SRCLI(MininetCLI):

    def do_verify_isis(self, _):
        'Check IS-IS adjacencies on all nodes'
        verify_isis(self.mn)

    def do_verify_bgp(self, _):
        'Check eBGP sessions on all ASBR nodes'
        verify_bgp(self.mn)

    def do_verify_sr(self, _):
        'Check SR-MPLS SID allocations'
        verify_sr(self.mn)

    def do_frr_status(self, line):
        'Show FRR daemon status: frr_status <node>'
        n = line.strip()
        if not n:
            print('Usage: frr_status <node_name>')
            return
        node = self.mn.get(n)
        run  = f'{RUN_DIR}/{n}'
        for d in ['zebra', 'isisd', 'bgpd']:
            r = node.cmd(
                f'[ -f {run}/{d}.pid ] && '
                f'kill -0 $(cat {run}/{d}.pid) 2>/dev/null '
                f'&& echo running || echo stopped'
            )
            print(f'  {d}: {r.strip()}')

    def do_show_route(self, line):
        'Show IP routing table: show_route <node>'
        n = line.strip()
        if not n:
            print('Usage: show_route <node_name>')
            return
        print(vtysh(self.mn.get(n), n, 'show ip route'))

    def do_ping_loopback(self, _):
        'End-to-end SR test: A-PE1 loopback → C-PE1 loopback'
        info('\n*** Pinging 10.0.3.1 from A-PE1 (10.0.1.1)\n')
        result = self.mn.get('a_pe1').cmd('ping -c 4 -I 10.0.1.1 10.0.3.1')
        print(result)

    def do_frr_log(self, line):
        'Show FRR log: frr_log <node> <daemon>  e.g. frr_log a_r1 isisd'
        parts = line.strip().split()
        if len(parts) != 2:
            print('Usage: frr_log <node> <daemon>')
            return
        n, d  = parts
        log   = f'{LOG_DIR}/{n}/{d}.log'
        node  = self.mn.get(n)
        print(node.cmd(f'tail -30 {log} 2>/dev/null || echo "Log not found: {log}"'))


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def print_summary():
    info('\n' + '='*60 + '\n')
    info('  SR TESTBED — 3-DOMAIN TOPOLOGY READY\n')
    info('='*60 + '\n')
    info('  Domain A  AS65001  SRGB 16000-16999  lo 10.0.1.x\n')
    info('  Domain B  AS65002  SRGB 17000-17999  lo 10.0.2.x\n')
    info('  Domain C  AS65003  SRGB 18000-18999  lo 10.0.3.x\n\n')
    info('  CLI: verify_isis | verify_bgp | verify_sr\n')
    info('       ping_loopback | frr_status <n> | show_route <n>\n')
    info('       frr_log <node> <daemon>\n')
    info('='*60 + '\n\n')


def run():
    setLogLevel('info')
    info('*** Building 3-domain SR testbed\n')

    net = Mininet(
        topo=SRTestbedTopo(),
        controller=None,
        waitConnected=True
    )
    net.start()
    configure_loopbacks(net)

    frr_ok = start_frr(net)

    if frr_ok:
        info('\n*** Waiting 30s for IS-IS convergence...\n')
        time.sleep(30)
        verify_isis(net)
        info('\n*** Waiting 15s for eBGP sessions...\n')
        time.sleep(15)
        verify_bgp(net)
    else:
        warn('\n*** Topology up but FRR not started\n')
        warn('    Copy configs to ~/sr-testbed/configs/frr/ first\n\n')

    print_summary()
    SRCLI(net)

    net.stop()
    os.system(f'rm -rf {RUN_DIR} {LOG_DIR}')


if __name__ == '__main__':
    run()
