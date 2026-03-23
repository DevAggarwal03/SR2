# Research Context: Privacy-Preserving Dynamic Re-computation for Multi-Domain SR

> **Purpose:** Running reference document capturing full setup progress, errors encountered, solutions applied, and remaining work.
> **Last Updated:** March 23, 2026
> **Status:** Phase 2 — In Progress (~85% complete)

---

## 1. Research Overview

**Topic:** Comparison of SR-MPLS and SRv6 in Segment Routing (SR) in Programmable Networks and SDN.

**Specific Contribution (Gap 6):** Multi-Domain SR Traffic Engineering Without Topology Disclosure.

**Formal Problem Statement:**
> *Given a multi-domain SR network where internal topology must remain private, design a protocol enabling child PCEs to notify a parent PCE of domain-state degradations using abstract, topology-concealing metrics, triggering timely and near-optimal cross-domain SR policy recomputation.*

**Paper Title:** *"Privacy-Preserving Dynamic Re-computation for Multi-Domain Segment Routing: An Abstract Event Notification Framework"*

**Target Venues:** IEEE TNSM, IEEE/IFIP NOMS, Computer Networks (Elsevier)

---

## 2. Environment

### Host Machine
- OS: Windows 11 x64
- Virtualisation: VMware Workstation

### VM (Ubuntu Server inside VMware)
- OS: Ubuntu 22.04.5 LTS (x86_64)
- RAM: 10 GB | CPU: 4 cores | Disk: 40 GB
- Network: NAT — IP: 192.168.238.131
- Username: dev
- SSH: `ssh dev@192.168.238.131`

### Software Stack

| Component | Tool | Version | Status |
|---|---|---|---|
| Network emulation | Mininet | 2.3.1b4 | ✅ Installed |
| Router implementation | FRRouting (FRR) | 10.5.3 | ✅ Installed |
| IGP + SR | IS-IS with SR-MPLS | FRR built-in | ✅ Converged |
| BGP-LS topology export | FRR BGP daemon | FRR built-in | ✅ Sessions up |
| Child PCE | OpenDaylight (Karaf) | 0.12.2 | ✅ Running |
| PCEP server | ODL BGPCEP module | 0.13.2 | ✅ Listening port 1790 |
| Parent PCE | Custom Python script | Python 3.10.12 | ⬜ Phase 2 |
| PCEP extension (ADSO) | Modified BGPCEP Java | — | ⬜ Phase 3 |
| Failure injection | Mininet link.stop() | — | ⬜ Phase 3 |
| Traffic measurement | iPerf3 | apt | ✅ Installed |
| Packet capture | tcpdump + tshark | apt | ✅ Installed |
| Java | OpenJDK 11 | 11.0.30 | ✅ Active |

### Key Environment Notes

```bash
# Java (must be 11 for ODL 0.12.2)
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Activate Python venv
source ~/sr-testbed/venv/bin/activate

# Start ODL
cd ~/sr-testbed/odl && bin/karaf

# Start topology (must be sudo)
sudo python3 ~/sr-testbed/topology/3dTopology.py

# After VM reboot — renew IP
sudo dhclient ens33 && ip addr show ens33

# Cleanup Mininet
sudo mn -c

# FRR system service MUST stay masked
sudo systemctl status frr  # should show masked
```

---

## 3. Project Directory Structure

```
~/sr-testbed/
├── topology/
│   └── 3dTopology.py          ← Main topology + FRR startup script
├── configs/
│   └── frr/                   ← Per-node FRR configs (17 nodes)
│       ├── a_pe1/frr.conf
│       ├── a_r1/frr.conf
│       ├── a_r2/frr.conf
│       ├── a_asbr1/frr.conf
│       ├── a_asbr2/frr.conf
│       ├── b_r1/frr.conf
│       ├── b_r2/frr.conf
│       ├── b_r3/frr.conf
│       ├── b_asbr1/frr.conf
│       ├── b_asbr2/frr.conf
│       ├── b_asbr3/frr.conf
│       ├── b_asbr4/frr.conf
│       ├── c_pe1/frr.conf
│       ├── c_r1/frr.conf
│       ├── c_r2/frr.conf
│       ├── c_asbr1/frr.conf
│       └── c_asbr2/frr.conf
├── child-pce/                 ← ODL BGPCEP config (Phase 3)
├── parent-pce/                ← Python parent PCE (Phase 3)
├── adso-protocol/             ← ADSO TLV spec (Phase 3)
├── experiments/
│   ├── scenarios/             ← Failure injection scripts
│   └── results/               ← iPerf3, tcpdump, CSVs
├── scripts/
│   └── start_frr.py
├── paper/
│   └── figures/
├── odl/                       ← ODL 0.12.2 Karaf installation
└── venv/                      ← Python virtual environment
```

> **Important:** ODL configs also live at `/root/sr-testbed/configs/frr/` because topology runs as sudo (root). Keep both in sync.

---

## 4. 3-Domain Topology

```
Domain A (AS 65001)          Domain B (AS 65002)          Domain C (AS 65003)
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│  A-PE1 (16001)  │          │  B-R1  (17001)  │          │  C-PE1 (18001)  │
│  A-R1  (16002)  │          │  B-R2  (17002)  │          │  C-R1  (18002)  │
│  A-R2  (16003)  │          │  B-R3  (17003)  │          │  C-R2  (18003)  │
│  A-ASBR1 ───────┼──eBGP───▶│  B-ASBR1        │          │                 │
│  A-ASBR2 ───────┼──eBGP───▶│  B-ASBR2        │          │                 │
└─────────────────┘          │  B-ASBR3 ───────┼──eBGP───▶│  C-ASBR1        │
                             │  B-ASBR4 ───────┼──eBGP───▶│  C-ASBR2        │
                             └─────────────────┘          └─────────────────┘

SR Policy: A-PE1 ──────────────────────────────────────────────▶ C-PE1
```

### SR SID Allocation

| Domain | AS | SRGB | Loopbacks |
|---|---|---|---|
| A | 65001 | 16000–16999 | 10.0.1.x/32 |
| B | 65002 | 17000–17999 | 10.0.2.x/32 |
| C | 65003 | 18000–18999 | 10.0.3.x/32 |

### Inter-AS eBGP Links

| Link | Subnet | A-side IP | B-side IP |
|---|---|---|---|
| A-ASBR1 ↔ B-ASBR1 | 10.100.12.0/30 | 10.100.12.1 | 10.100.12.2 |
| A-ASBR2 ↔ B-ASBR2 | 10.100.12.4/30 | 10.100.12.5 | 10.100.12.6 |
| B-ASBR3 ↔ C-ASBR1 | 10.100.23.0/30 | 10.100.23.1 | 10.100.23.2 |
| B-ASBR4 ↔ C-ASBR2 | 10.100.23.4/30 | 10.100.23.5 | 10.100.23.6 |

---

## 5. ODL Setup — Errors & Solutions

### Error 1: ODL version mismatch (YANG schema conflict)
- **Symptom:** `SchemaResolutionException` — PCEP bundles (0.13.2) couldn't resolve `network-topology` YANG model
- **Root cause:** ODL 0.12.2 Karaf distribution shipped with 0.13.2 BGPCEP bundles — version mismatch in YANG dependencies
- **Attempted fixes:** ODL 0.14.4 (failed — Maven offline), ODL 0.21.3 (auth issues), ODL 0.22.12 (AAA overhaul)
- **Solution:** Stayed on ODL 0.12.2, installed features correctly, PCEP bundles self-resolved once all features were started

### Error 2: Stale PID file blocking Karaf startup
- **Symptom:** `There is a Root instance already running with name root and pid 73698`
- **Solution:**
```bash
sudo kill -9 73698 2>/dev/null
rm -f ~/sr-testbed/odl/instances/root.lock
rm -f ~/sr-testbed/odl/data/port
cd ~/sr-testbed/odl && bin/karaf clean
```

### Error 3: ODL 0.14.4 Maven resolver failure
- **Symptom:** `Error installing bundle: mvn:org.apache.karaf.features/org.apache.karaf.features.core/4.3.6`
- **Root cause:** ODL 0.14.4 needs online Maven to resolve startup bundles; VM has no internet for Maven
- **Solution:** Abandoned 0.14.4, returned to 0.12.2

### Error 4: HTTP 401 on RESTCONF
- **Symptom:** All credential combinations returning 401
- **Root cause:** ODL 0.12.2 AAA datastore (H2 DB) takes precedence over `users.properties` file
- **Solution:** Wiped AAA datastore and cache, allowed ODL to reinitialise with default `admin:admin`
```bash
rm -f ~/sr-testbed/odl/data/idmlight.db.mv.db
rm -rf ~/sr-testbed/odl/data/cache/
rm -rf ~/sr-testbed/odl/data/journal/
bin/karaf clean
```

### Error 5: PCEP port 4189 never opened
- **Symptom:** Port 4189 absent from `ss -tlnp` even after topology PUT returned HTTP 201
- **Root cause:** YANG schema for `network-topology-pcep` not loaded (feature not fully started)
- **Solution:** Installed `odl-bgpcep-pcep` feature, waited for all bundles to reach Active state, re-pushed topology config. PCEP server binds on **port 1790** in this build (not 4189)

### ODL Credentials & Endpoints (confirmed working)
```
Username: admin
Password: admin
RESTCONF: http://localhost:8181/restconf/
PCEP port: 1790
```

---

## 6. FRR + Mininet Setup — Errors & Solutions

### Error 6: FRR daemons failing with permission denied
- **Symptom:** `Can't create pid lock file /tmp/frr/a_r1/isisd.pid (Permission denied)`
- **Root cause:** System FRR service (`watchfrr`) was running and owned `/tmp/frr/` as `frr` user; per-node instances couldn't write
- **Solution:**
```bash
sudo systemctl stop frr
sudo systemctl mask frr   # prevents auto-restart
sudo pkill -9 -f "watchfrr"
sudo pkill -9 -f "mgmtd"
```

### Error 7: FRR daemons starting but config not loading
- **Symptom:** `show running-config` showed default config only (hostname: ubuntu, no router isis)
- **Root cause:** FRR 10.x uses `mgmtd` for config management; the `-f` flag on individual daemons is ignored when mgmtd is running
- **Solution:** Start all daemons first, then push config via `vtysh -f`:
```python
node.cmd(f'vtysh --vty_socket {node_run}/ -f {cfg} 2>/dev/null')
```

### Error 8: FRR 10.x requires mgmtd before zebra
- **Symptom:** Zebra failed silently; `frr_status` showed all daemons stopped
- **Root cause:** FRR 10.x introduced mandatory `mgmtd` daemon that must start first
- **Solution:** Added mgmtd to startup sequence:
```python
FRR_MGMT = '/usr/lib/frr/mgmtd'
# Start order: mgmtd → zebra → isisd → bgpd → vtysh -f config
```

### Error 9: vtysh "failed to connect to any daemons"
- **Symptom:** All vtysh commands returned `Exiting: failed to connect`
- **Root cause:** Per-node daemons were writing vty sockets to `/var/run/frr/` (system default) — all 17 nodes sharing and overwriting the same socket
- **Solution:** Pass `--vty_socket {node_run}` to each daemon so each node gets its own isolated socket directory in `/tmp/frr/<node_name>/`

### Error 10: IS-IS adjacencies not forming
- **Symptom:** All nodes showed 0 IS-IS neighbors despite daemons running
- **Root cause:** vtysh checker was using wrong socket path (missing trailing `/`)
- **Solution:** Fixed vtysh helper to use `--vty_socket /tmp/frr/<node_name>/` with trailing slash. IS-IS immediately showed adjacencies once checker was fixed.

### Error 11: BGP not exchanging routes between domains
- **Symptom:** eBGP sessions Established but each ASBR only had its own domain routes
- **Root cause 1:** Missing `redistribute isis` in BGP address-family config
- **Root cause 2:** `route-map ALLOW-ALL` referenced in config but never defined — caused all outbound advertisements to be blocked
- **Solution:**
```
# Live fix in Mininet CLI:
vtysh -c "conf t" -c "route-map ALLOW-ALL permit 10" -c "exit" -c "end"
vtysh -c "clear bgp * soft"
```
Then added permanently to all ASBR frr.conf files.

### Error 12: Cross-domain ping failing despite BGP routes present
- **Symptom:** BGP routes exchanged between ASBRs but `a_pe1` had no route to `10.0.3.1`
- **Root cause:** BGP routes not redistributed back into IS-IS — internal routers couldn't see cross-domain prefixes
- **FRR 10.x syntax:** `redistribute ipv4 bgp level-2` (NOT `redistribute bgp level-2`)
- **Solution (live):**
```
vtysh -c "conf t" -c "router isis CORE" -c "redistribute ipv4 bgp level-2" -c "exit" -c "end"
```
- **Status:** ✅ Fixed — persisted `redistribute ipv4 bgp level-2 route-map ALLOW-ALL` and `route-map ALLOW-ALL permit 10` into all 8 ASBR frr.conf files. Restart topology to apply.

---

## 7. Current Status (Phase 2 — In Progress)

### Completed ✅

- [x] Ubuntu 22.04.5 LTS VM (VMware, 10GB RAM, 40GB disk)
- [x] SSH access from Windows Terminal
- [x] Java 11 installed and JAVA_HOME configured
- [x] FRR 10.5.3 installed — bgpd, isisd, ospfd, pathd enabled
- [x] SR kernel modules loaded (mpls_router, mpls_iptunnel)
- [x] Python 3.10.12 + venv configured
- [x] ODL 0.12.2 installed and running
- [x] ODL RESTCONF working (HTTP 200, admin:admin)
- [x] ODL BGPCEP features installed (all Started)
- [x] PCEP topology created (HTTP 201), server on port 1790
- [x] Mininet 2.3.1b4 installed and smoke-tested
- [x] 3-domain topology (17 nodes, all links verified)
- [x] FRR configs for all 17 nodes
- [x] IS-IS converged — all 17 nodes showing adjacencies Up
- [x] eBGP sessions — all 8 pairs Established
- [x] BGP route redistribution — IS-IS → BGP → IS-IS pipeline configured
- [x] Cross-domain route learning — a_pe1 has route to 10.0.3.1
- [x] `route-map ALLOW-ALL permit 10` persisted to all 8 ASBR frr.conf files
- [x] `redistribute ipv4 bgp level-2 route-map ALLOW-ALL` persisted to all 8 ASBR IS-IS configs
- [x] BGP neighbor route-map in/out references added to all ASBRs

### In Progress 🔄

- [ ] **End-to-end ping A-PE1 → C-PE1** — route exists, ICMP failing
  - TTL trace shows packets die after a_asbr1 (entering Domain B)
  - Investigating: reverse route on Domain C, MPLS label forwarding, ip_forward on transit nodes
  - Next step: check `b_asbr1 show ip route 10.0.3.1` and `c_pe1 show ip route 10.0.1.1`

### Remaining ⬜

- [ ] Fix end-to-end ping — restart topology with fixed configs, verify
- [ ] Verify SR-MPLS label forwarding end-to-end (`show mpls table`)
- [ ] BGP-LS export from FRR to ODL (configure ODL as BGP-LS receiver)
- [ ] Verify topology visible in ODL RESTCONF operational datastore
- [ ] iPerf3 baseline measurement (A-PE1 → C-PE1)
- [ ] SR kernel modules persistent on boot
- [ ] Python packages in venv (networkx, scapy, pandas, matplotlib, pyshark)

---

## 8. Remaining Phases

### Phase 2 — Remaining Items (Est. 1–2 sessions)
1. Fix end-to-end ICMP (current active task)
2. Persist all ASBR config fixes into frr.conf files
3. Configure BGP-LS export to ODL
4. Verify end-to-end SR-MPLS label switching
5. iPerf3 baseline

### Phase 3 — Protocol Implementation (Weeks 3–5)
- Implement ADSO TLV in ODL BGPCEP Java module
- Abstract Event Vocabulary (5 metrics):
  1. Min end-to-end delay across domain boundary
  2. Max available bandwidth between border nodes
  3. Max SR segment list depth domain can support
  4. Packet loss rate at ASBR
  5. ASBR reachability status (binary)
- Notification triggering logic (absolute/relative thresholds, rate limiter)
- Python Parent PCE script

### Phase 4 — Failure Injection & Experiments (Weeks 6–7)
- 4 failure scenarios (S1–S4)
- 3 comparison baselines per scenario (ADSO / no-notification / oracle)
- Collect 5 result tables (R1–R5)

### Phase 5 — Analysis & Paper Writing (Weeks 8–14)
- Result synthesis and Matplotlib figures
- Full paper draft (8 sections)

---

## 9. Debugging Reference — Current Issue

### Symptom
```
a_pe1 ping -c 4 -I 10.0.1.1 10.0.3.1
→ 100% packet loss
```

### What we know
- `a_pe1` HAS route to 10.0.3.1 (via IS-IS, metric 20)
- TTL=1 dies at 10.1.1.2 (a_r1) ✅
- TTL=2 dies at 10.1.1.10 (a_asbr1) ✅
- TTL=3 no response — packet enters Domain B and is dropped

### Next diagnostic commands to run
```
# In Mininet CLI:
b_asbr1 vtysh --vty_socket /tmp/frr/b_asbr1/ -c "show ip route 10.0.3.1"
b_asbr1 ping -c 2 10.0.3.1
c_pe1 vtysh --vty_socket /tmp/frr/c_pe1/ -c "show ip route 10.0.1.1"
b_r1 sysctl net.ipv4.ip_forward
```

### Likely causes (in order of probability)
1. `b_asbr1` has no route to Domain C (B↔C BGP redistribution not applied yet)
2. Reverse route missing on Domain C nodes (asymmetric routing)
3. MPLS encapsulation breaking ICMP at domain boundary
4. `ip_forward` disabled on a transit node in Domain B

---

## 10. Key Commands Reference

### ODL
```bash
# Start ODL
cd ~/sr-testbed/odl && bin/karaf

# Inside Karaf — install features
feature:install odl-restconf
feature:install odl-bgpcep-bgp
feature:install odl-bgpcep-pcep

# Test REST API
curl -u admin:admin http://localhost:8181/restconf/operational/network-topology:network-topology/ -o /dev/null -w "%{http_code}\n"

# Create PCEP topology
curl -u admin:admin -H "Content-Type: application/json" -X PUT \
  http://localhost:8181/restconf/config/network-topology:network-topology/topology/pcep-topology \
  -d '{"topology":[{"topology-id":"pcep-topology","topology-types":{"network-topology-pcep:topology-pcep":{}}}]}'
```

### Topology
```bash
# Start full topology with FRR
sudo python3 ~/sr-testbed/topology/3dTopology.py

# Inside Mininet CLI
verify_isis       # check all IS-IS adjacencies
verify_bgp        # check all eBGP sessions
verify_sr         # check SR SID allocations
ping_loopback     # end-to-end A-PE1 → C-PE1
frr_status <n>    # FRR daemon status for node
show_route <n>    # IP routing table
frr_log <n> <d>   # tail FRR log
```

### FRR vtysh (per node)
```bash
# General pattern
<node> vtysh --vty_socket /tmp/frr/<node>/ -c "<command>"

# Useful commands
-c "show isis neighbor"
-c "show isis segment-routing node"
-c "show bgp ipv4 unicast"
-c "show bgp neighbor <peer_ip>"
-c "show ip route"
-c "show mpls table"
-c "clear bgp * soft"
```

---

## 11. ADSO Protocol Design (Phase 3 Reference)

### 5 Abstract Metrics
1. Min end-to-end delay across domain boundary
2. Max available bandwidth between border nodes
3. Max SR segment list depth domain can support
4. Packet loss rate at ASBR
5. ASBR reachability status (binary — up/down)

### Triggering Logic
- Absolute threshold: fire if delay > 8ms
- Relative threshold: fire if bandwidth drops > 20%
- Rate limiter: max 1 notification per 500ms per metric

### Recovery Timeline Target
| Time | Event |
|---|---|
| T=0ms | Link fails inside Domain A |
| T≈15ms | TI-LFA activates — local repair |
| T≈20ms | Child PCE sends ADSO to Parent PCE |
| T≈35ms | Parent PCE recomputes SR path |
| T≈50ms | New SR policy pushed to ingress router |

---

*Continue from Section 9 — fix end-to-end ping, then proceed to BGP-LS export to ODL.*
