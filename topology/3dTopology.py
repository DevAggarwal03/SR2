#!/usr/bin/env python3
"""
topology.py — 3-Domain SR Testbed Topology with FRR
=====================================================
Research: Privacy-Preserving Dynamic Re-computation for Multi-Domain SR

Usage:
  sudo python3 3dTopology.py

Inside Mininet CLI:
  verify_isis    — check IS-IS adjacencies on all nodes
  verify_bgp     — check eBGP sessions on all ASBRs
  verify_e2e     — end-to-end reachability check
  ping_loopback  — A-PE1 → C-PE1 ping test
  fix_routes     — re-run kernel route fix
  frr_status <n> — FRR daemon status for a node
  show_route <n> — IP routing table for a node
  frr_log <n> <d>— tail FRR log
  bgp_routes <n> — BGP table for an ASBR
  exit           — shut down

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

CONFIGS_DIR = '/home/dev/sr-testbed/configs/frr'
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

ASBR_PEERS = {
    'a_asbr1': '10.100.12.2',
    'a_asbr2': '10.100.12.6',
    'b_asbr1': '10.100.12.1',
    'b_asbr2': '10.100.12.5',
    'b_asbr3': '10.100.23.2',
    'b_asbr4': '10.100.23.6',
    'c_asbr1': '10.100.23.1',
    'c_asbr2': '10.100.23.5',
}

ASBR_AS = {
    'a_asbr1': 65001, 'a_asbr2': 65001,
    'b_asbr1': 65002, 'b_asbr2': 65002,
    'b_asbr3': 65002, 'b_asbr4': 65002,
    'c_asbr1': 65003, 'c_asbr2': 65003,
}


# ─────────────────────────────────────────────
#  Linux Router Node
# ─────────────────────────────────────────────

class LinuxRouter(Node):

    def config(self, **params):
        super().config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')
        self.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0')
        self.cmd('sysctl -w net.ipv4.conf.default.rp_filter=0')
        self.cmd('sysctl -w net.mpls.platform_labels=1000')
        self.cmd('sysctl -w net.mpls.conf.lo.input=1')
        for intf in self.intfList():
            if intf.name != 'lo':
                self.cmd(f'sysctl -w net.mpls.conf.{intf.name}.input=1')
                self.cmd(f'sysctl -w net.ipv4.conf.{intf.name}.rp_filter=0')

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
#  Loopback configuration
# ─────────────────────────────────────────────

def configure_loopbacks(net):
    info('*** Configuring loopbacks\n')
    for node_name, (lo_ip, _sid) in LOOPBACKS.items():
        node = net.get(node_name)
        node.cmd(f'ip addr add {lo_ip}/32 dev lo')
        node.cmd('ip link set lo up')


# ─────────────────────────────────────────────
#  FRR startup
# ─────────────────────────────────────────────

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
            f'{FRR_MGMT} -f {cfg} -u root -g root '
            f'-i {node_run}/mgmtd.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/mgmtd.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.5)

        node.cmd(
            f'{FRR_ZEBRA} -f {cfg} -u root -g root '
            f'-i {node_run}/zebra.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/zebra.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.3)

        node.cmd(
            f'{FRR_ISIS} -f {cfg} -u root -g root '
            f'-i {node_run}/isisd.pid '
            f'-z {node_run}/zserv.api '
            f'--vty_socket {node_run} '
            f'--log file:{node_log}/isisd.log '
            f'--log-level informational -d 2>/dev/null'
        )
        time.sleep(0.5)

        if node_name in ASBR_NODES:
            node.cmd(
                f'{FRR_BGP} -f {cfg} -u root -g root '
                f'-i {node_run}/bgpd.pid '
                f'-z {node_run}/zserv.api '
                f'--vty_socket {node_run} '
                f'--log file:{node_log}/bgpd.log '
                f'--log-level informational -d 2>/dev/null'
            )
        time.sleep(0.3)

        node.cmd(f'vtysh --vty_socket {node_run}/ -f {cfg} 2>/dev/null')
        info(f'  [OK] {node_name}\n')

    return True


# ─────────────────────────────────────────────
#  Post-startup routing policies
# ─────────────────────────────────────────────

def post_config(net):
    info('\n*** Applying cross-domain routing policies\n')

    for node_name in ASBR_NODES:
        node = net.get(node_name)
        peer = ASBR_PEERS[node_name]
        asn  = ASBR_AS[node_name]
        run  = f'{RUN_DIR}/{node_name}/'

        node.cmd(
            f'vtysh --vty_socket {run} -c "conf t" '
            f'-c "route-map ALLOW-ALL permit 10" -c "end" 2>/dev/null'
        )
        node.cmd(
            f'vtysh --vty_socket {run} -c "conf t" '
            f'-c "router isis CORE" '
            f'-c "redistribute ipv4 bgp level-2" '
            f'-c "exit" '
            f'-c "router bgp {asn}" '
            f'-c "address-family ipv4 unicast" '
            f'-c "neighbor {peer} next-hop-self" '
            f'-c "neighbor {peer} route-map ALLOW-ALL in" '
            f'-c "neighbor {peer} route-map ALLOW-ALL out" '
            f'-c "redistribute isis" '
            f'-c "redistribute connected" '
            f'-c "exit" -c "end" 2>/dev/null'
        )
        node.cmd(
            f'vtysh --vty_socket {run} '
            f'-c "clear bgp {peer} soft" 2>/dev/null'
        )
        info(f'  [OK] {node_name}\n')

    info('*** Waiting 25s for routes to propagate...\n')
    time.sleep(25)


def fix_kernel_routes(net):
    """
    Workaround for Mininet + FRR 10.x SR-MPLS kernel route issue.
    FRR installs routes with MPLS-encap nexthop objects that Mininet
    namespaces cannot execute. Replace them with plain IP routes.
    Control-plane SR path computation (ADSO contribution) is unaffected.
    """
    info('\n*** Fixing kernel routes for Mininet compatibility\n')

    for node_name in LOOPBACKS.keys():
        node  = net.get(node_name)
        fixed = 0

        for proto in ['isis', 'bgp']:
            raw = node.cmd(f'ip route show proto {proto} 2>/dev/null')
            for line in raw.splitlines():
                line = line.strip()
                if not line or 'via' not in line or 'dev' not in line:
                    continue
                if line.startswith('nexthop'):
                    continue
                parts = line.split()
                if not parts:
                    continue
                dst = parts[0]
                try:
                    via_idx = parts.index('via')
                    gw      = parts[via_idx + 1]
                    dev_idx = parts.index('dev')
                    dev     = parts[dev_idx + 1]
                except (ValueError, IndexError):
                    continue
                node.cmd(
                    f'ip route replace {dst} via {gw} dev {dev} '
                    f'proto {proto} 2>/dev/null'
                )
                fixed += 1

        node.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0 2>/dev/null')
        node.cmd('sysctl -w net.ipv4.conf.default.rp_filter=0 2>/dev/null')
        info(f'  [OK] {node_name}: {fixed} route(s) fixed\n')

    info('*** Waiting 5s after route fix...\n')
    time.sleep(5)


# ─────────────────────────────────────────────
#  Verification
# ─────────────────────────────────────────────

def vtysh(node, node_name, cmd):
    return node.cmd(
        f'{VTYSH} --vty_socket {RUN_DIR}/{node_name}/ '
        f'-c "{cmd}" 2>/dev/null'
    )


def verify_isis(net):
    info('\n*** IS-IS Adjacencies\n')
    for n in LOOPBACKS.keys():
        result = vtysh(net.get(n), n, 'show isis neighbor')
        up = result.count('Up')
        info(f'  {"✓" if up > 0 else "✗"} {n}: {up} neighbor(s)\n')


def verify_bgp(net):
    info('\n*** eBGP Sessions\n')
    for n, peer in ASBR_PEERS.items():
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


def verify_e2e(net):
    info('\n*** End-to-End Reachability\n')
    tests = [
        ('a_pe1', '10.0.2.1', 'A-PE1 → B-R1  (A→B)'),
        ('a_pe1', '10.0.3.1', 'A-PE1 → C-PE1 (A→B→C)'),
        ('c_pe1', '10.0.1.1', 'C-PE1 → A-PE1 (C→B→A)'),
        ('b_r2',  '10.0.1.1', 'B-R2  → A-PE1 (B→A)'),
        ('b_r2',  '10.0.3.1', 'B-R2  → C-PE1 (B→C)'),
    ]
    all_ok = True
    for src, dst, label in tests:
        result = net.get(src).cmd(f'ping -c 2 -W 1 {dst}')
        ok = '2 received' in result or '1 received' in result
        info(f'  {"✓" if ok else "✗"} {label}\n')
        if not ok:
            all_ok = False
    return all_ok


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

    def do_verify_e2e(self, _):
        'Check end-to-end reachability across all 3 domains'
        verify_e2e(self.mn)

    def do_frr_status(self, line):
        'FRR daemon status: frr_status <node>'
        n = line.strip()
        if not n:
            print('Usage: frr_status <node_name>')
            return
        run = f'{RUN_DIR}/{n}'
        for d in ['mgmtd', 'zebra', 'isisd', 'bgpd']:
            r = self.mn.get(n).cmd(
                f'[ -f {run}/{d}.pid ] && '
                f'kill -0 $(cat {run}/{d}.pid) 2>/dev/null '
                f'&& echo running || echo stopped'
            )
            print(f'  {d}: {r.strip()}')

    def do_show_route(self, line):
        'IP routing table: show_route <node>'
        n = line.strip()
        if not n:
            print('Usage: show_route <node_name>')
            return
        print(vtysh(self.mn.get(n), n, 'show ip route'))

    def do_ping_loopback(self, _):
        'End-to-end test: A-PE1 → C-PE1'
        info('\n*** Pinging 10.0.3.1 from A-PE1 (10.0.1.1)\n')
        print(self.mn.get('a_pe1').cmd('ping -c 4 -I 10.0.1.1 10.0.3.1'))

    def do_frr_log(self, line):
        'Tail FRR log: frr_log <node> <daemon>'
        parts = line.strip().split()
        if len(parts) != 2:
            print('Usage: frr_log <node> <daemon>')
            return
        n, d = parts
        log  = f'{LOG_DIR}/{n}/{d}.log'
        print(self.mn.get(n).cmd(
            f'tail -30 {log} 2>/dev/null || echo "Log not found: {log}"'
        ))

    def do_bgp_routes(self, line):
        'BGP table: bgp_routes <node>'
        n = line.strip()
        if not n:
            print('Usage: bgp_routes <asbr_node>')
            return
        print(vtysh(self.mn.get(n), n, 'show bgp ipv4 unicast'))

    def do_fix_routes(self, _):
        'Re-run kernel route fix if connectivity breaks'
        fix_kernel_routes(self.mn)
        verify_e2e(self.mn)


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def print_summary():
    info('\n' + '='*62 + '\n')
    info('  SR TESTBED — 3-DOMAIN TOPOLOGY READY\n')
    info('='*62 + '\n')
    info('  Domain A  AS65001  SRGB 16000-16999  lo 10.0.1.x\n')
    info('  Domain B  AS65002  SRGB 17000-17999  lo 10.0.2.x\n')
    info('  Domain C  AS65003  SRGB 18000-18999  lo 10.0.3.x\n\n')
    info('  CLI: verify_isis | verify_bgp | verify_sr | verify_e2e\n')
    info('       ping_loopback | fix_routes\n')
    info('       frr_status <n> | show_route <n> | frr_log <n> <d>\n')
    info('       bgp_routes <n>\n')
    info('='*62 + '\n\n')


def run():
    setLogLevel('info')
    info('*** Building 3-domain SR testbed\n')

    net = Mininet(topo=SRTestbedTopo(), controller=None, waitConnected=True)
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

        post_config(net)
        fix_kernel_routes(net)

        info('\n*** Verifying end-to-end reachability...\n')
        ok = verify_e2e(net)
        if ok:
            info('*** All paths reachable ✓\n\n')
        else:
            warn('*** Some paths still unreachable — run fix_routes in CLI\n\n')
    else:
        warn('\n*** FRR not started — check: ' + CONFIGS_DIR + '\n\n')

    print_summary()
    SRCLI(net)
    net.stop()
    os.system(f'rm -rf {RUN_DIR} {LOG_DIR}')


if __name__ == '__main__':
    run()
