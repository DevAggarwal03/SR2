// Network Topology Data
const nodes = [
    // Domain A
    { id: 'a_pe1', label: 'A-PE1', domain: 'A', type: 'pe', x: 100, y: 300 },
    { id: 'a_r1', label: 'A-R1', domain: 'A', type: 'internal', x: 200, y: 150 },
    { id: 'a_r2', label: 'A-R2', domain: 'A', type: 'internal', x: 200, y: 450 },
    { id: 'a_asbr1', label: 'A-ASBR1', domain: 'A', type: 'asbr', x: 350, y: 150 },
    { id: 'a_asbr2', label: 'A-ASBR2', domain: 'A', type: 'asbr', x: 350, y: 450 },
    
    // Domain B
    { id: 'b_asbr1', label: 'B-ASBR1', domain: 'B', type: 'asbr', x: 500, y: 150 },
    { id: 'b_asbr2', label: 'B-ASBR2', domain: 'B', type: 'asbr', x: 500, y: 450 },
    { id: 'b_r1', label: 'B-R1', domain: 'B', type: 'internal', x: 600, y: 150 },
    { id: 'b_r2', label: 'B-R2', domain: 'B', type: 'internal', x: 700, y: 300 },
    { id: 'b_r3', label: 'B-R3', domain: 'B', type: 'internal', x: 800, y: 300 },
    { id: 'b_asbr3', label: 'B-ASBR3', domain: 'B', type: 'asbr', x: 950, y: 150 },
    { id: 'b_asbr4', label: 'B-ASBR4', domain: 'B', type: 'asbr', x: 950, y: 450 },
    
    // Domain C
    { id: 'c_asbr1', label: 'C-ASBR1', domain: 'C', type: 'asbr', x: 1100, y: 150 },
    { id: 'c_asbr2', label: 'C-ASBR2', domain: 'C', type: 'asbr', x: 1100, y: 450 },
    { id: 'c_r1', label: 'C-R1', domain: 'C', type: 'internal', x: 1250, y: 150 },
    { id: 'c_r2', label: 'C-R2', domain: 'C', type: 'internal', x: 1250, y: 450 },
    { id: 'c_pe1', label: 'C-PE1', domain: 'C', type: 'pe', x: 1350, y: 300 },
];

const links = [
    // Domain A
    { source: 'a_pe1', target: 'a_r1', id: 'l1' },
    { source: 'a_pe1', target: 'a_r2', id: 'l2' },
    { source: 'a_r1', target: 'a_asbr1', id: 'la_r1_asbr1' },
    { source: 'a_r2', target: 'a_asbr2', id: 'l4' },
    { source: 'a_r1', target: 'a_r2', id: 'l5' },
    
    // Domain B
    { source: 'b_asbr1', target: 'b_r1', id: 'l6' },
    { source: 'b_asbr2', target: 'b_r1', id: 'l7' },
    { source: 'b_r1', target: 'b_r2', id: 'l8' },
    { source: 'b_r2', target: 'b_r3', id: 'l9' },
    { source: 'b_r3', target: 'b_asbr3', id: 'lb_r3_asbr3' },
    { source: 'b_r3', target: 'b_asbr4', id: 'l11' },
    
    // Domain C
    { source: 'c_asbr1', target: 'c_r1', id: 'l12' },
    { source: 'c_asbr2', target: 'c_r2', id: 'l13' },
    { source: 'c_r1', target: 'c_r2', id: 'l14' },
    { source: 'c_r1', target: 'c_pe1', id: 'l15' },
    { source: 'c_r2', target: 'c_pe1', id: 'l16' },
    
    // Inter-domain
    { source: 'a_asbr1', target: 'b_asbr1', id: 'l17', inter: true },
    { source: 'a_asbr2', target: 'b_asbr2', id: 'l18', inter: true },
    { source: 'b_asbr3', target: 'c_asbr1', id: 'l19', inter: true },
    { source: 'b_asbr4', target: 'c_asbr2', id: 'l20', inter: true },
];

// D3 configuration
const width = document.getElementById('network-graph').clientWidth;
const height = 600;
const svg = d3.select('#network-graph')
    .append('svg')
    .attr('width', '100%')
    .attr('height', height)
    .attr('viewBox', [0, 0, 1400, 600]);

// Visual grouping backgrounds
svg.append('rect').attr('x', 50).attr('y', 50).attr('width', 350).attr('height', 500).attr('fill', '#f8f9fa').attr('rx', 20).attr('opacity', 0.5);
svg.append('rect').attr('x', 450).attr('y', 50).attr('width', 550).attr('height', 500).attr('fill', '#fff3e0').attr('rx', 20).attr('opacity', 0.5);
svg.append('rect').attr('x', 1050).attr('y', 50).attr('width', 320).attr('height', 500).attr('fill', '#e8f5e9').attr('rx', 20).attr('opacity', 0.5);

// Render links
const link = svg.selectAll('.link')
    .data(links)
    .enter()
    .append('line')
    .attr('class', 'link')
    .attr('id', d => d.id)
    .attr('x1', d => nodes.find(n => n.id === d.source).x)
    .attr('y1', d => nodes.find(n => n.id === d.source).y)
    .attr('x2', d => nodes.find(n => n.id === d.target).x)
    .attr('y2', d => nodes.find(n => n.id === d.target).y);

// Render nodes
const node = svg.selectAll('.node')
    .data(nodes)
    .enter()
    .append('g')
    .attr('class', d => `node ${d.type}`)
    .attr('transform', d => `translate(${d.x}, ${d.y})`);

node.append('circle')
    .attr('r', 12)
    .attr('fill', d => {
        if (d.type === 'pe') return '#3182ce';
        if (d.type === 'asbr') return '#d97706'; // Darker amber for visibility
        return '#718096';
    });

node.append('text')
    .attr('dy', 25)
    .attr('text-anchor', 'middle')
    .text(d => d.label);

// Variables to track state
let activeScenario = null;
const primaryPathLinks = ['l1', 'la_r1_asbr1', 'l17', 'l6', 'l8', 'l9', 'lb_r3_asbr3', 'l19', 'l12', 'l15'];

// Highlight initial path
function highlightInitialPath() {
    primaryPathLinks.forEach(id => d3.select(`#${id}`).classed('active', true).attr('stroke', '#2ecc71'));
}
highlightInitialPath();

// Scenario actions
const scenarios = {
    'S1': {
        title: 'Link Failure in Domain A',
        targetDomain: 'A',
        action: () => {
            d3.select('#la_r1_asbr1').attr('stroke', '#e74c3c').classed('active', false).style('stroke-dasharray', '5,2');
            updateMetrics('A', 12.5, 350, 0.02, 'OK');
            logEvent('Failure Injection [S1]: Link between A-R1 and A-ASBR1 down.', 'D-A delay increased to 12.5ms.');
        },
        reconvergence: {
            time: 34.68,
            newPath: ['l2', 'l4', 'l18', 'l7', 'l8', 'l9', 'lb_r3_asbr3', 'l19', 'l12', 'l15'],
            details: 'ADSO triggered (delay > 8ms). Parent PCE pushed new SR policy via A-ASBR2.'
        }
    },
    'S2': {
        title: 'ASBR Degradation (D-B)',
        targetDomain: 'B',
        action: () => {
            d3.select('#b_asbr3 circle').attr('fill', '#f39c12').style('stroke', '#e74c3c').style('stroke-width', '4px');
            updateMetrics('B', 6.0, 200, 8.0, 'OK');
            logEvent('Metric Alert [S2]: Packet loss at B-ASBR3 raised to 8%.', 'D-B quality degradation detected.');
        },
        reconvergence: {
            time: 35.21,
            newPath: ['l1', 'la_r1_asbr1', 'l17', 'l6', 'l8', 'l9', 'l11', 'l20', 'l13', 'l16'],
            details: 'ADSO triggered (loss > 5%). Path rerouted through B-ASBR4/C-ASBR2.'
        }
    },
    'S3': {
        title: 'ASBR Total Failure (D-B)',
        targetDomain: 'B',
        action: () => {
            d3.select('#b_asbr3 circle').attr('fill', '#e74c3c');
            d3.select('#lb_r3_asbr3').attr('stroke', '#e74c3c').classed('active', false);
            d3.select('#l19').attr('stroke', '#e74c3c').classed('active', false);
            updateMetrics('B', 0.0, 0.0, 100.0, 'DOWN');
            logEvent('Critical Failure [S3]: B-ASBR3 Offline.', 'Reachability transition detected.');
        },
        reconvergence: {
            time: 34.21,
            newPath: ['l1', 'la_r1_asbr1', 'l17', 'l6', 'l8', 'l9', 'l11', 'l20', 'l13', 'l16'],
            details: 'Immediate ADSO re-convergence. Backup domain exit B-ASBR4 utilized.'
        }
    },
    'S4': {
        title: 'Domain B Recovery',
        targetDomain: 'B',
        action: () => {
            d3.select('#b_asbr3 circle').attr('fill', '#f39c12').style('stroke', '#fff').style('stroke-width', '2px');
            d3.select('#lb_r3_asbr3').attr('stroke', '#cbd5e0').classed('active', false);
            d3.select('#l19').attr('stroke', '#cbd5e0').classed('active', false);
            updateMetrics('B', 2.0, 500, 0.0, 'OK');
            logEvent('Recovery Event [S4]: B-ASBR3 back online.', 'Restoring optimal cross-domain path.');
        },
        reconvergence: {
            time: 29.43,
            newPath: ['l1', 'la_r1_asbr1', 'l17', 'l6', 'l8', 'l9', 'lb_r3_asbr3', 'l19', 'l12', 'l15'],
            details: 'ADSO triggered (ASBR UP). Path restored to nominal segment list.'
        }
    }
};

function runScenario(id) {
    if (activeScenario === id) return;
    resetVisuals();
    activeScenario = id;
    
    // UI updates
    document.querySelectorAll('.scenario-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`btn-${id.toLowerCase()}`).classList.add('active');
    
    const s = scenarios[id];
    s.action();
    
    // Simulate ADSO delay for re-convergence
    setTimeout(() => {
        applyNewPath(s.reconvergence.newPath);
        // Display new Segment List in the log for better analysis
        const sl = id === 'S1' ? '[16001, 16011, 17011, 18001]' : (id === 'S2' || id === 'S3' ? '[16001, 16010, 17013, 18001]' : '[16001, 16010, 17012, 18001]');
        logEvent('ADSO Re-convergence Complete', `${s.reconvergence.details} <br><strong>New SL:</strong> ${sl} | <strong>Time:</strong> ${s.reconvergence.time}ms`);
    }, 800); 
}

function updateMetrics(domain, delay, bw, loss, reach) {
    document.getElementById('active-domain-label').innerText = `Domain ${domain}`;
    document.getElementById('metric-delay').innerText = delay;
    document.getElementById('metric-bw').innerText = bw;
    document.getElementById('metric-loss').innerText = loss;
    document.getElementById('metric-reach').innerText = reach;
}

function logEvent(title, details) {
    const log = document.getElementById('timeline-log');
    const time = new Date().toLocaleTimeString().split(' ')[0];
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-time">[${time}]</span>
        <span class="log-event">${title}</span>
        <div class="log-details">${details}</div>
    `;
    log.prepend(entry);
}

function applyNewPath(pathIds) {
    d3.selectAll('.link').classed('active', false).attr('stroke', '#cbd5e0');
    pathIds.forEach(id => {
        d3.select(`#${id}`).classed('active', true).attr('stroke', '#2ecc71');
    });
}

function resetVisuals() {
    d3.selectAll('.link').classed('active', false).attr('stroke', '#cbd5e0').style('stroke-dasharray', null);
    d3.selectAll('circle').attr('fill', d => {
        if (d.type === 'pe') return '#3182ce';
        if (d.type === 'asbr') return '#d97706';
        return '#718096';
    }).style('stroke', 'rgba(0,0,0,0.1)').style('stroke-width', '1.5px');
}

function resetSimulation() {
    activeScenario = null;
    resetVisuals();
    highlightInitialPath();
    updateMetrics('A', 2.0, 500, 0.0, 'UP');
    document.querySelectorAll('.scenario-btn').forEach(btn => btn.classList.remove('active'));
    logEvent('Reset', 'Simulation state restored to default.');
}
