# Simulation Assumptions

The following assumptions were made during the development of this SR-ADSO (Segment Routing - Abstract Domain State Object) project simulation:

1.  **Topology Visualization**: 
    - The node positions are fixed for clarity, rather than being purely dynamic, to ensure the hierarchical structure (Domain A, B, C) is easily understandable.
    - Links are represented as lines, with labels for latency and bandwidth where appropriate (though simplified from the 1000Mbps/500Mbps real-world values for visibility).
2.  **Path Selection Logic**:
    - The simulation mimics the primary SR path (`a_pe1` -> `a_asbr1` -> `b_asbr3` -> `c_pe1`) mentioned in the project.
    - Path recomputation in the UI is based on the logic described in the ADSO paper (Equation 1: cost function using delay, bandwidth, and loss).
3.  **Timing and Animations**:
    - Experimental timings (~30-35ms for ADSO, ~400s for BGP) are scaled in the UI for visibility. A 30ms event might be represented as an instantaneous update if too fast, or slightly slowed down for human observation but with the correct labels for real results.
4.  **Data Source**:
    - The simulation results (ADSO re-convergence times, metric changes) are driven from the provided `experiment_results.json`.
5.  **Metrics Simplified**:
    - While the paper mentions five metrics, the UI focuses on the three primary ones (Delay, Bandwidth, Packet Loss) that trigger the threshold logic, as others (SID depth) are more static in this testbed.
6.  **PCE Coordination**:
    - The simulation assumes the Child PCE and Parent PCE are always reachable via PCEP, and the notification delay is consistent with the experimental breakdown.
