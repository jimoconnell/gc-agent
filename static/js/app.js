// GC Log Analyzer - Frontend JavaScript

let analysisData = null;
let pauseChart = null;
let heapChart = null;

// Zoom state for pause chart
let pauseChartZoom = {
    startIndex: 0,
    endIndex: null,
    isDragging: false,
    dragStartX: null,
    selectionStart: null
};

// Upload handling
document.addEventListener('DOMContentLoaded', () => {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');

    uploadZone.addEventListener('click', () => fileInput.click());

    // Prevent browser from opening files dropped anywhere
    document.addEventListener('dragover', e => { e.preventDefault(); e.stopPropagation(); });
    document.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); });

    uploadZone.addEventListener('dragover', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragenter', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', e => {
        handleFiles(e.target.files);
    });

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.panel + '-panel').classList.add('active');
            
            // Re-render charts when their tabs become visible (they need visible width)
            if (analysisData) {
                if (tab.dataset.panel === 'overview') {
                    setTimeout(() => {
                        displayPauseChart();
                        displayHeapChart();
                    }, 50);
                } else if (tab.dataset.panel === 'timeline') {
                    setTimeout(() => displayTimelineChart(), 50);
                }
            }
        });
    });
});

async function handleFiles(files) {
    if (files.length === 0) return;

    document.getElementById('upload-section').style.display = 'none';
    document.getElementById('loading').classList.add('active');

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Analysis failed');

        analysisData = await response.json();
        displayResults();
    } catch (error) {
        alert('Error analyzing GC logs: ' + error.message);
        resetAnalysis();
    }
}

function displayResults() {
    document.getElementById('loading').classList.remove('active');
    document.getElementById('results').classList.add('active');

    const stats = analysisData.statistics;
    const summary = analysisData.summary;

    // Reset zoom for new data
    pauseChartZoom.startIndex = 0;
    pauseChartZoom.endIndex = null;

    // Update summary cards
    updateSummaryCards(stats, summary);

    // Display charts
    displayPauseChart();
    displayHeapChart();
    displayDistributionChart();
    displayTimelineChart();

    // Display issues
    displayIssues();

    // Display events table
    displayEventsTable();
    
    // Auto-start agentic analysis if AI is available
    autoStartAgenticAnalysis();
}

function updateSummaryCards(stats, summary) {
    const grid = document.getElementById('summary-grid');
    
    const severityClass = summary.severity === 'critical' ? 'critical' : 
                          summary.severity === 'warning' ? 'warning' : 'healthy';
    
    let cardsHtml = `
        <div class="summary-card ${severityClass}">
            <div class="summary-label">Status</div>
            <div class="summary-value">${summary.severity.toUpperCase()}</div>
        </div>
        <div class="summary-card info">
            <div class="summary-label">Collector</div>
            <div class="summary-value" style="font-size: 1.25rem;">${analysisData.collector_type}</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">GC Events</div>
            <div class="summary-value">${(stats.total_gc_events || 0).toLocaleString()}</div>
        </div>
        <div class="summary-card ${stats.full_gc_count > 5 ? 'critical' : ''}">
            <div class="summary-label">Full GCs</div>
            <div class="summary-value">${stats.full_gc_count || 0}</div>
        </div>
        <div class="summary-card ${stats.max_pause_ms > 500 ? 'critical' : stats.max_pause_ms > 200 ? 'warning' : ''}">
            <div class="summary-label">Max Pause</div>
            <div class="summary-value">${formatMs(stats.max_pause_ms)}</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">Avg Pause</div>
            <div class="summary-value">${formatMs(stats.avg_pause_ms)}</div>
        </div>
        <div class="summary-card ${stats.throughput_percent < 95 ? 'warning' : 'healthy'}">
            <div class="summary-label">Throughput</div>
            <div class="summary-value">${stats.throughput_percent ? stats.throughput_percent.toFixed(1) + '%' : 'N/A'}</div>
        </div>
        <div class="summary-card">
            <div class="summary-label">Max Heap</div>
            <div class="summary-value">${formatMB(stats.max_heap_mb)}</div>
        </div>
    `;
    
    grid.innerHTML = cardsHtml;
}

function displayPauseChart() {
    const container = document.getElementById('pause-chart');
    const allEvents = analysisData.events.filter(e => e.pause_ms > 0);
    
    if (allEvents.length === 0) {
        container.innerHTML = '<div class="empty-state">No pause data available</div>';
        return;
    }

    // Initialize zoom state
    if (pauseChartZoom.endIndex === null) {
        pauseChartZoom.endIndex = allEvents.length;
    }
    
    // Get visible events based on zoom
    const startIdx = Math.max(0, pauseChartZoom.startIndex);
    const endIdx = Math.min(allEvents.length, pauseChartZoom.endIndex);
    const events = allEvents.slice(startIdx, endIdx);
    
    if (events.length === 0) {
        pauseChartZoom.startIndex = 0;
        pauseChartZoom.endIndex = allEvents.length;
        displayPauseChart();
        return;
    }

    // Create wrapper with controls
    const width = container.clientWidth;
    const height = 300;
    const padding = { top: 20, right: 20, bottom: 60, left: 70 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const maxPause = Math.max(...events.map(e => e.pause_ms));
    const isZoomed = startIdx > 0 || endIdx < allEvents.length;

    // Build zoom controls HTML
    let html = `<div class="chart-controls">
        <div class="zoom-buttons">
            <button class="zoom-btn" onclick="zoomPauseChart('in')" title="Zoom In">🔍+</button>
            <button class="zoom-btn" onclick="zoomPauseChart('out')" title="Zoom Out" ${!isZoomed ? 'disabled' : ''}>🔍−</button>
            <button class="zoom-btn" onclick="zoomPauseChart('reset')" title="Reset Zoom" ${!isZoomed ? 'disabled' : ''}>↺</button>
        </div>
        <div class="zoom-info">
            ${isZoomed ? `Showing ${events.length} of ${allEvents.length} events (${startIdx + 1} - ${endIdx})` : `All ${allEvents.length} events`}
        </div>
        <div class="chart-hint">Click and drag to select a region to zoom</div>
    </div>`;

    // Create SVG
    let svg = `<svg id="pause-chart-svg" width="${width}" height="${height}" style="font-family: inherit; cursor: crosshair;">`;
    
    // Background for mouse events
    svg += `<rect x="${padding.left}" y="${padding.top}" width="${chartWidth}" height="${chartHeight}" fill="transparent" />`;
    
    // Grid lines
    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
        const y = padding.top + (chartHeight / yTicks) * i;
        const value = maxPause - (maxPause / yTicks) * i;
        svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#30363d" stroke-width="1"/>`;
        svg += `<text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#8b949e" font-size="11">${formatMs(value)}</text>`;
    }

    // Calculate time range for X-axis
    const hasTimestamps = events.some(e => e.timestamp);
    const hasUptime = events.some(e => e.uptime_seconds !== null && e.uptime_seconds !== undefined);
    
    // X-axis time labels
    const xTicks = Math.min(8, events.length);
    const tickInterval = Math.floor(events.length / xTicks) || 1;
    
    for (let i = 0; i < events.length; i += tickInterval) {
        const x = padding.left + (chartWidth / events.length) * i + (chartWidth / events.length) / 2;
        const event = events[i];
        
        let label = '';
        if (hasTimestamps && event.timestamp) {
            const d = new Date(event.timestamp);
            label = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } else if (hasUptime && event.uptime_seconds !== null) {
            label = formatUptime(event.uptime_seconds);
        } else {
            label = `#${startIdx + i + 1}`;
        }
        
        svg += `<text x="${x}" y="${height - padding.bottom + 20}" text-anchor="middle" fill="#8b949e" font-size="10" transform="rotate(-45, ${x}, ${height - padding.bottom + 20})">${label}</text>`;
    }

    // Data points (bars)
    const barWidth = Math.max(2, Math.min(12, chartWidth / events.length - 1));
    events.forEach((event, i) => {
        const x = padding.left + (chartWidth / events.length) * i + (chartWidth / events.length - barWidth) / 2;
        const barHeight = (event.pause_ms / maxPause) * chartHeight;
        const y = padding.top + chartHeight - barHeight;
        
        let color = '#3fb950';  // healthy (green)
        if (event.pause_ms > 500) color = '#f85149';  // critical (red)
        else if (event.pause_ms > 200) color = '#d29922';  // warning (yellow/orange)
        else if (event.pause_ms > 50) color = '#58a6ff';  // info (blue)
        
        if (event.is_full_gc) color = '#f85149';  // Full GC always red
        
        const timeInfo = event.timestamp 
            ? new Date(event.timestamp).toLocaleString() 
            : (event.uptime_seconds ? `Uptime: ${formatUptime(event.uptime_seconds)}` : '');
        
        svg += `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" fill="${color}" opacity="0.85" data-index="${startIdx + i}">
                    <title>${event.pause_type || event.gc_type}: ${event.pause_ms.toFixed(2)}ms\n${timeInfo}${event.cause ? '\nCause: ' + event.cause : ''}</title>
                </rect>`;
    });

    // Selection overlay (hidden by default)
    svg += `<rect id="pause-selection" x="0" y="${padding.top}" width="0" height="${chartHeight}" fill="rgba(88, 166, 255, 0.2)" stroke="#58a6ff" stroke-width="1" style="display: none;"/>`;
    
    // Y-axis label
    svg += `<text x="20" y="${height / 2}" text-anchor="middle" fill="#8b949e" font-size="12" transform="rotate(-90, 20, ${height / 2})">Pause Time</text>`;

    svg += '</svg>';
    
    container.innerHTML = html + svg;
    
    // Add mouse event listeners for drag-to-zoom
    setupPauseChartInteraction(allEvents, padding, chartWidth, chartHeight);
}

function setupPauseChartInteraction(allEvents, padding, chartWidth, chartHeight) {
    const svg = document.getElementById('pause-chart-svg');
    const selection = document.getElementById('pause-selection');
    if (!svg || !selection) return;
    
    const startIdx = pauseChartZoom.startIndex;
    const endIdx = pauseChartZoom.endIndex;
    const visibleEvents = allEvents.slice(startIdx, endIdx);
    
    svg.addEventListener('mousedown', (e) => {
        const rect = svg.getBoundingClientRect();
        const x = e.clientX - rect.left;
        
        if (x >= padding.left && x <= padding.left + chartWidth) {
            pauseChartZoom.isDragging = true;
            pauseChartZoom.dragStartX = x;
            selection.style.display = 'block';
            selection.setAttribute('x', x);
            selection.setAttribute('width', 0);
        }
    });
    
    svg.addEventListener('mousemove', (e) => {
        if (!pauseChartZoom.isDragging) return;
        
        const rect = svg.getBoundingClientRect();
        const x = Math.max(padding.left, Math.min(e.clientX - rect.left, padding.left + chartWidth));
        const startX = pauseChartZoom.dragStartX;
        
        const left = Math.min(x, startX);
        const width = Math.abs(x - startX);
        
        selection.setAttribute('x', left);
        selection.setAttribute('width', width);
    });
    
    svg.addEventListener('mouseup', (e) => {
        if (!pauseChartZoom.isDragging) return;
        
        const rect = svg.getBoundingClientRect();
        const endX = Math.max(padding.left, Math.min(e.clientX - rect.left, padding.left + chartWidth));
        const startX = pauseChartZoom.dragStartX;
        
        pauseChartZoom.isDragging = false;
        selection.style.display = 'none';
        
        // Calculate selected range
        const selWidth = Math.abs(endX - startX);
        if (selWidth < 10) return; // Too small, ignore
        
        const leftX = Math.min(startX, endX) - padding.left;
        const rightX = Math.max(startX, endX) - padding.left;
        
        const leftIdx = Math.floor((leftX / chartWidth) * visibleEvents.length);
        const rightIdx = Math.ceil((rightX / chartWidth) * visibleEvents.length);
        
        // Update zoom to selected range
        pauseChartZoom.startIndex = startIdx + Math.max(0, leftIdx);
        pauseChartZoom.endIndex = startIdx + Math.min(visibleEvents.length, rightIdx);
        
        displayPauseChart();
    });
    
    svg.addEventListener('mouseleave', () => {
        if (pauseChartZoom.isDragging) {
            pauseChartZoom.isDragging = false;
            selection.style.display = 'none';
        }
    });
}

function zoomPauseChart(action) {
    const allEvents = analysisData.events.filter(e => e.pause_ms > 0);
    const currentStart = pauseChartZoom.startIndex;
    const currentEnd = pauseChartZoom.endIndex || allEvents.length;
    const visibleCount = currentEnd - currentStart;
    
    switch (action) {
        case 'in':
            // Zoom to center 50%
            const zoomInAmount = Math.floor(visibleCount * 0.25);
            pauseChartZoom.startIndex = currentStart + zoomInAmount;
            pauseChartZoom.endIndex = currentEnd - zoomInAmount;
            break;
        case 'out':
            // Expand by 50%
            const zoomOutAmount = Math.floor(visibleCount * 0.5);
            pauseChartZoom.startIndex = Math.max(0, currentStart - zoomOutAmount);
            pauseChartZoom.endIndex = Math.min(allEvents.length, currentEnd + zoomOutAmount);
            break;
        case 'reset':
            pauseChartZoom.startIndex = 0;
            pauseChartZoom.endIndex = allEvents.length;
            break;
    }
    
    displayPauseChart();
}

function formatUptime(seconds) {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

function displayHeapChart() {
    const container = document.getElementById('heap-chart');
    const events = analysisData.events.filter(e => e.heap_total_mb > 0);
    
    if (events.length === 0) {
        container.innerHTML = '<div class="empty-state">No heap data available</div>';
        return;
    }

    const width = container.clientWidth;
    const height = 250;
    const padding = { top: 20, right: 20, bottom: 40, left: 70 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const maxHeap = Math.max(...events.map(e => e.heap_total_mb));

    let svg = `<svg width="${width}" height="${height}" style="font-family: inherit;">`;
    
    // Grid lines
    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
        const y = padding.top + (chartHeight / yTicks) * i;
        const value = maxHeap - (maxHeap / yTicks) * i;
        svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#30363d" stroke-width="1"/>`;
        svg += `<text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#6e7681" font-size="11">${formatMB(value)}</text>`;
    }

    // Build path for heap usage
    let pathBefore = `M ${padding.left} ${padding.top + chartHeight}`;
    let pathAfter = `M ${padding.left} ${padding.top + chartHeight}`;
    let pathTotal = '';

    events.forEach((event, i) => {
        const x = padding.left + (chartWidth / (events.length - 1 || 1)) * i;
        const yBefore = padding.top + chartHeight - (event.heap_before_mb / maxHeap) * chartHeight;
        const yAfter = padding.top + chartHeight - (event.heap_after_mb / maxHeap) * chartHeight;
        const yTotal = padding.top + chartHeight - (event.heap_total_mb / maxHeap) * chartHeight;
        
        if (i === 0) {
            pathBefore = `M ${x} ${yBefore}`;
            pathAfter = `M ${x} ${yAfter}`;
            pathTotal = `M ${x} ${yTotal}`;
        } else {
            pathBefore += ` L ${x} ${yBefore}`;
            pathAfter += ` L ${x} ${yAfter}`;
            pathTotal += ` L ${x} ${yTotal}`;
        }
    });

    // Total heap line (dashed)
    svg += `<path d="${pathTotal}" stroke="#6e7681" stroke-width="2" fill="none" stroke-dasharray="5,5"/>`;
    
    // Before GC line
    svg += `<path d="${pathBefore}" stroke="#d29922" stroke-width="2" fill="none" opacity="0.8"/>`;
    
    // After GC line
    svg += `<path d="${pathAfter}" stroke="#3fb950" stroke-width="2" fill="none"/>`;

    // Legend
    svg += `<rect x="${width - 150}" y="10" width="12" height="12" fill="#3fb950"/>`;
    svg += `<text x="${width - 130}" y="20" fill="#e6edf3" font-size="11">After GC</text>`;
    svg += `<rect x="${width - 150}" y="28" width="12" height="12" fill="#d29922"/>`;
    svg += `<text x="${width - 130}" y="38" fill="#e6edf3" font-size="11">Before GC</text>`;
    svg += `<line x1="${width - 150}" y1="52" x2="${width - 138}" y2="52" stroke="#6e7681" stroke-width="2" stroke-dasharray="3,3"/>`;
    svg += `<text x="${width - 130}" y="56" fill="#e6edf3" font-size="11">Total Heap</text>`;

    svg += '</svg>';
    container.innerHTML = svg;
}

function displayTimelineChart() {
    const container = document.getElementById('timeline-chart');
    const events = analysisData.events.filter(e => e.pause_ms > 0);
    
    if (events.length === 0) {
        container.innerHTML = '<div class="empty-state">No GC events to display</div>';
        return;
    }

    const width = container.clientWidth;
    const height = 380;
    const padding = { top: 30, right: 30, bottom: 80, left: 80 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Determine time scale
    const hasTimestamps = events.some(e => e.timestamp);
    const hasUptime = events.some(e => e.uptime_seconds !== null && e.uptime_seconds !== undefined);
    
    let timeValues = [];
    let timeLabel = 'Event #';
    
    if (hasTimestamps) {
        timeValues = events.map(e => new Date(e.timestamp).getTime());
        timeLabel = 'Time';
    } else if (hasUptime) {
        timeValues = events.map(e => e.uptime_seconds || 0);
        timeLabel = 'Uptime';
    } else {
        timeValues = events.map((e, i) => i);
    }
    
    const minTime = Math.min(...timeValues);
    const maxTime = Math.max(...timeValues);
    const timeRange = maxTime - minTime || 1;
    
    const maxPause = Math.max(...events.map(e => e.pause_ms));
    const maxHeap = Math.max(...events.map(e => e.heap_total_mb || 0));

    let svg = `<svg width="${width}" height="${height}" style="font-family: inherit;">`;
    
    // Title
    svg += `<text x="${width / 2}" y="20" text-anchor="middle" fill="#e6edf3" font-size="14" font-weight="600">GC Activity Timeline</text>`;
    
    // Y-axis grid lines (pause time)
    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
        const y = padding.top + (chartHeight / yTicks) * i;
        const value = maxPause - (maxPause / yTicks) * i;
        svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#30363d" stroke-width="1"/>`;
        svg += `<text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#8b949e" font-size="10">${formatMs(value)}</text>`;
    }
    
    // X-axis time labels
    const xTicks = Math.min(10, events.length);
    const tickInterval = Math.floor(events.length / xTicks) || 1;
    
    for (let i = 0; i < events.length; i += tickInterval) {
        const x = padding.left + ((timeValues[i] - minTime) / timeRange) * chartWidth;
        const event = events[i];
        
        let label = '';
        if (hasTimestamps && event.timestamp) {
            const d = new Date(event.timestamp);
            label = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else if (hasUptime && event.uptime_seconds !== null) {
            label = formatUptime(event.uptime_seconds);
        } else {
            label = `#${i + 1}`;
        }
        
        svg += `<line x1="${x}" y1="${padding.top + chartHeight}" x2="${x}" y2="${padding.top + chartHeight + 5}" stroke="#8b949e" stroke-width="1"/>`;
        svg += `<text x="${x}" y="${height - padding.bottom + 25}" text-anchor="middle" fill="#8b949e" font-size="10" transform="rotate(-45, ${x}, ${height - padding.bottom + 25})">${label}</text>`;
    }
    
    // Draw heap usage as area chart (background)
    if (maxHeap > 0) {
        let heapPath = `M ${padding.left} ${padding.top + chartHeight}`;
        events.forEach((event, i) => {
            const x = padding.left + ((timeValues[i] - minTime) / timeRange) * chartWidth;
            const heapPct = (event.heap_after_mb || 0) / maxHeap;
            const y = padding.top + chartHeight - (heapPct * chartHeight * 0.3); // Scale to 30% of chart height
            heapPath += ` L ${x} ${y}`;
        });
        heapPath += ` L ${padding.left + chartWidth} ${padding.top + chartHeight} Z`;
        svg += `<path d="${heapPath}" fill="rgba(88, 166, 255, 0.1)" stroke="none"/>`;
    }
    
    // Draw pause times as vertical bars/lollipops
    events.forEach((event, i) => {
        const x = padding.left + ((timeValues[i] - minTime) / timeRange) * chartWidth;
        const barHeight = (event.pause_ms / maxPause) * chartHeight;
        const y = padding.top + chartHeight - barHeight;
        
        let color = '#3fb950';  // healthy
        if (event.pause_ms > 500) color = '#f85149';  // critical
        else if (event.pause_ms > 200) color = '#d29922';  // warning
        else if (event.pause_ms > 50) color = '#58a6ff';  // info
        
        if (event.is_full_gc) color = '#f85149';
        
        // Stem
        svg += `<line x1="${x}" y1="${padding.top + chartHeight}" x2="${x}" y2="${y}" stroke="${color}" stroke-width="2" opacity="0.7"/>`;
        
        // Circle at top
        const radius = event.is_full_gc ? 6 : 4;
        const timeInfo = event.timestamp 
            ? new Date(event.timestamp).toLocaleString() 
            : (event.uptime_seconds ? `Uptime: ${formatUptime(event.uptime_seconds)}` : '');
        
        svg += `<circle cx="${x}" cy="${y}" r="${radius}" fill="${color}" opacity="0.9">
            <title>${event.pause_type || event.gc_type}: ${event.pause_ms.toFixed(2)}ms\n${timeInfo}${event.is_full_gc ? '\n⚠️ Full GC' : ''}${event.cause ? '\nCause: ' + event.cause : ''}</title>
        </circle>`;
    });
    
    // Legend
    const legendY = height - 25;
    svg += `<circle cx="${padding.left}" cy="${legendY}" r="4" fill="#3fb950"/>`;
    svg += `<text x="${padding.left + 10}" y="${legendY + 4}" fill="#8b949e" font-size="10">Normal</text>`;
    
    svg += `<circle cx="${padding.left + 70}" cy="${legendY}" r="4" fill="#58a6ff"/>`;
    svg += `<text x="${padding.left + 80}" y="${legendY + 4}" fill="#8b949e" font-size="10">>50ms</text>`;
    
    svg += `<circle cx="${padding.left + 140}" cy="${legendY}" r="4" fill="#d29922"/>`;
    svg += `<text x="${padding.left + 150}" y="${legendY + 4}" fill="#8b949e" font-size="10">>200ms</text>`;
    
    svg += `<circle cx="${padding.left + 220}" cy="${legendY}" r="6" fill="#f85149"/>`;
    svg += `<text x="${padding.left + 232}" y="${legendY + 4}" fill="#8b949e" font-size="10">>500ms / Full GC</text>`;
    
    // Axis labels
    svg += `<text x="${padding.left - 50}" y="${padding.top + chartHeight / 2}" text-anchor="middle" fill="#8b949e" font-size="11" transform="rotate(-90, ${padding.left - 50}, ${padding.top + chartHeight / 2})">Pause Time</text>`;
    svg += `<text x="${padding.left + chartWidth / 2}" y="${height - 5}" text-anchor="middle" fill="#8b949e" font-size="11">${timeLabel}</text>`;

    svg += '</svg>';
    container.innerHTML = svg;
}

function displayDistributionChart() {
    const container = document.getElementById('distribution-chart');
    const dist = analysisData.statistics.pause_distribution;
    
    if (!dist) {
        container.innerHTML = '<div class="empty-state">No distribution data</div>';
        return;
    }

    const maxCount = Math.max(...Object.values(dist));
    
    let html = '<div class="distribution-chart">';
    
    const bucketOrder = ['0-10ms', '10-50ms', '50-100ms', '100-500ms', '500ms-1s', '>1s'];
    const bucketColors = {
        '0-10ms': '',
        '10-50ms': '',
        '50-100ms': '',
        '100-500ms': 'medium',
        '500ms-1s': 'high',
        '>1s': 'high'
    };
    
    for (const bucket of bucketOrder) {
        const count = dist[bucket] || 0;
        const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
        const colorClass = bucketColors[bucket];
        
        html += `
            <div class="dist-bar">
                <div class="dist-label">${bucket}</div>
                <div class="dist-track">
                    <div class="dist-fill ${colorClass}" style="width: ${pct}%"></div>
                </div>
                <div class="dist-count">${count.toLocaleString()}</div>
            </div>
        `;
    }
    
    html += '</div>';
    container.innerHTML = html;
}

function displayIssues() {
    const container = document.getElementById('issues-list');
    const issues = analysisData.issues || [];
    
    if (issues.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="color: var(--severity-healthy);">
                ✓ No significant issues detected
            </div>
        `;
        return;
    }
    
    let html = '<div class="issues-list">';
    
    for (const issue of issues) {
        html += `
            <div class="issue-card ${issue.severity}">
                <div class="issue-header">
                    <span class="issue-type">${issue.type.replace(/_/g, ' ')}</span>
                    <span class="issue-severity ${issue.severity}">${issue.severity}</span>
                </div>
                <div class="issue-description">${escapeHtml(issue.description)}</div>
            </div>
        `;
    }
    
    html += '</div>';
    container.innerHTML = html;
}

function displayEventsTable() {
    const container = document.getElementById('events-table');
    const events = analysisData.events || [];
    
    if (events.length === 0) {
        container.innerHTML = '<div class="empty-state">No GC events found</div>';
        return;
    }

    let html = `
        <div class="events-toolbar">
            <div class="filter-group">
                <span class="filter-label">Filter:</span>
                <select id="event-filter" onchange="filterEvents()">
                    <option value="all">All Events</option>
                    <option value="pause">Pause Events Only</option>
                    <option value="full">Full GC Only</option>
                    <option value="long">Long Pauses (>100ms)</option>
                </select>
            </div>
        </div>
        <div class="events-scroll">
            <table class="events-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Time</th>
                        <th>Type</th>
                        <th>Cause</th>
                        <th>Pause</th>
                        <th>Heap Before</th>
                        <th>Heap After</th>
                        <th>Reclaimed</th>
                    </tr>
                </thead>
                <tbody id="events-tbody">
    `;
    
    const displayEvents = events.slice(0, 500);  // Limit for performance
    
    for (const event of displayEvents) {
        const rowClass = event.is_full_gc ? 'full-gc' : (event.pause_ms > 200 ? 'long-pause' : '');
        const pauseClass = getPauseBadgeClass(event.pause_ms);
        
        html += `
            <tr class="${rowClass}" data-full="${event.is_full_gc}" data-pause="${event.pause_ms}">
                <td>${event.gc_id ?? '-'}</td>
                <td>${formatTime(event.timestamp || event.uptime_seconds)}</td>
                <td>${event.pause_type || event.gc_type}</td>
                <td>${event.cause || '-'}</td>
                <td><span class="pause-badge ${pauseClass}">${formatMs(event.pause_ms)}</span></td>
                <td>${formatMB(event.heap_before_mb)}</td>
                <td>${formatMB(event.heap_after_mb)}</td>
                <td>${formatMB(event.heap_reclaimed_mb)}</td>
            </tr>
        `;
    }
    
    html += '</tbody></table></div>';
    
    if (events.length > 500) {
        html += `<div class="empty-state">Showing first 500 of ${events.length} events</div>`;
    }
    
    container.innerHTML = html;
}

function filterEvents() {
    const filter = document.getElementById('event-filter').value;
    const rows = document.querySelectorAll('#events-tbody tr');
    
    rows.forEach(row => {
        const isFull = row.dataset.full === 'true';
        const pause = parseFloat(row.dataset.pause) || 0;
        
        let show = true;
        
        switch (filter) {
            case 'pause':
                show = pause > 0;
                break;
            case 'full':
                show = isFull;
                break;
            case 'long':
                show = pause > 100;
                break;
        }
        
        row.style.display = show ? '' : 'none';
    });
}

// AI Analysis
async function runAIAnalysis() {
    const btn = document.getElementById('ai-analyze-btn');
    const agenticBtn = document.getElementById('agentic-analyze-btn');
    const container = document.getElementById('ai-analysis');
    
    btn.disabled = true;
    agenticBtn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span> Analyzing...';
    
    container.innerHTML = `
        <div class="ai-loading">
            <div class="spinner"></div>
            <div class="ai-loading-text">AI is analyzing your GC logs... This may take a minute.</div>
        </div>
    `;
    
    try {
        const response = await fetch('/ai-analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(analysisData)
        });
        
        const result = await response.json();
        
        if (result.error) {
            container.innerHTML = `<div class="ai-error">❌ ${escapeHtml(result.error)}</div>`;
        } else {
            container.innerHTML = `<div class="ai-result">${formatMarkdown(result.analysis)}</div>`;
            if (result.model) {
                document.getElementById('ai-model-badge').textContent = result.model;
            }
        }
    } catch (error) {
        container.innerHTML = `<div class="ai-error">❌ Failed to get AI analysis: ${escapeHtml(error.message)}</div>`;
    } finally {
        btn.disabled = false;
        agenticBtn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">✨</span> Quick Analysis';
    }
}

// Auto-start agentic analysis if Ollama is available
async function autoStartAgenticAnalysis() {
    // First check if Ollama is reachable
    try {
        const healthCheck = await fetch('/ai-health', { 
            method: 'GET',
            signal: AbortSignal.timeout(3000)  // 3 second timeout
        });
        
        if (!healthCheck.ok) {
            console.log('AI not available, skipping auto-analysis');
            return;
        }
        
        const health = await healthCheck.json();
        if (!health.available) {
            console.log('Ollama not running, skipping auto-analysis');
            return;
        }
        
        // Ollama is available - show indicator and start analysis
        console.log('Ollama available, auto-starting agentic analysis');
        
        // Update AI tab to show analysis is starting
        const aiTab = document.querySelector('.tab.ai-tab');
        if (aiTab) {
            aiTab.innerHTML = '🤖 AI Analysis <span class="auto-analyzing">●</span>';
        }
        
        // Update the AI panel to show it's auto-analyzing
        const container = document.getElementById('ai-analysis');
        container.innerHTML = `
            <div class="ai-auto-start">
                <div class="ai-loading">
                    <div class="spinner"></div>
                    <div class="ai-loading-text">
                        🔬 Agent is automatically investigating your GC logs...<br>
                        <small style="color: var(--text-muted);">You can explore the charts while this runs</small>
                    </div>
                </div>
            </div>
        `;
        
        // Run the agentic analysis
        const response = await fetch('/agentic-analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(analysisData)
        });
        
        const result = await response.json();
        
        // Restore AI tab text
        if (aiTab) {
            aiTab.innerHTML = '🤖 AI Analysis <span class="analysis-ready">✓</span>';
        }
        
        if (result.error) {
            container.innerHTML = `<div class="ai-error">❌ ${escapeHtml(result.error)}</div>`;
        } else {
            displayAgenticResult(result);
            if (result.model) {
                document.getElementById('ai-model-badge').textContent = result.model;
            }
        }
        
    } catch (error) {
        // Silently fail - AI is optional
        console.log('Auto-analysis skipped:', error.message);
        
        // Restore AI tab if it was modified
        const aiTab = document.querySelector('.tab.ai-tab');
        if (aiTab) {
            aiTab.innerHTML = '🤖 AI Analysis';
        }
    }
}

// Agentic Analysis
async function runAgenticAnalysis() {
    const btn = document.getElementById('agentic-analyze-btn');
    const quickBtn = document.getElementById('ai-analyze-btn');
    const container = document.getElementById('ai-analysis');
    
    btn.disabled = true;
    quickBtn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span> Investigating...';
    
    container.innerHTML = `
        <div class="ai-loading">
            <div class="spinner"></div>
            <div class="ai-loading-text">Agent is autonomously investigating your GC issues...<br>This uses multiple analysis steps and may take a few minutes.</div>
        </div>
    `;
    
    try {
        const response = await fetch('/agentic-analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(analysisData)
        });
        
        const result = await response.json();
        
        if (result.error) {
            container.innerHTML = `<div class="ai-error">❌ ${escapeHtml(result.error)}</div>`;
        } else {
            displayAgenticResult(result);
            if (result.model) {
                document.getElementById('ai-model-badge').textContent = result.model;
            }
        }
    } catch (error) {
        container.innerHTML = `<div class="ai-error">❌ Failed to run agentic analysis: ${escapeHtml(error.message)}</div>`;
    } finally {
        btn.disabled = false;
        quickBtn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🔬</span> Agentic Triage';
    }
}

function displayAgenticResult(result) {
    const container = document.getElementById('ai-analysis');
    
    let html = '<div class="agentic-result">';
    
    // Show investigation steps
    if (result.steps && result.steps.length > 0) {
        html += `<div class="agentic-trace">
            <h3 style="color: var(--accent-cyan); margin-bottom: 1rem;">
                🔬 Investigation Trace (${result.total_steps} steps)
            </h3>`;
        
        for (const step of result.steps) {
            const isExpanded = step.is_final ? 'expanded' : '';
            const isFinal = step.is_final ? 'final' : '';
            
            html += `
                <div class="agentic-step ${isExpanded} ${isFinal}" onclick="this.classList.toggle('expanded')">
                    <div class="agentic-step-header">
                        <div class="agentic-step-number">${step.step}</div>
                        <div class="agentic-step-thought">${escapeHtml(step.thought || 'Thinking...')}</div>
                        ${step.action ? `<div class="agentic-step-action">${escapeHtml(step.action)}</div>` : ''}
                    </div>
                    ${step.observation ? `
                        <div class="agentic-step-body">
                            <div class="agentic-observation">${escapeHtml(step.observation)}</div>
                        </div>
                    ` : ''}
                </div>
            `;
        }
        
        html += '</div>';
    }
    
    // Show final answer
    if (result.final_answer) {
        html += `
            <div class="agentic-final-answer">
                <div class="agentic-final-header">
                    <span>✅</span> Analysis Complete
                </div>
                <div class="ai-result">${formatMarkdown(result.final_answer)}</div>
            </div>
        `;
    }
    
    // Show recommendations
    if (result.recommendations && result.recommendations.length > 0) {
        html += `
            <div class="agentic-recommendations">
                <div class="agentic-rec-title">🎯 Tuning Recommendations</div>
        `;
        
        for (const rec of result.recommendations) {
            const priorityIcon = rec.priority === 'high' ? '🔴' : '🟡';
            html += `
                <div class="agentic-rec-item">
                    <div class="agentic-rec-priority">${priorityIcon}</div>
                    <div class="agentic-rec-content">
                        <div class="agentic-rec-flag">${escapeHtml(rec.flag)}</div>
                        <div class="agentic-rec-reason">${escapeHtml(rec.reason)}</div>
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
    }
    
    // Show issues found
    if (result.issues_found && result.issues_found.length > 0) {
        html += `
            <div style="margin-top: 1.5rem;">
                <div class="agentic-rec-title">⚠️ Issues Discovered During Investigation</div>
        `;
        
        for (const issue of result.issues_found) {
            const severityColor = issue.severity === 'critical' ? 'var(--severity-critical)' : 'var(--severity-warning)';
            html += `
                <div class="agentic-rec-item" style="border-left: 3px solid ${severityColor};">
                    <div class="agentic-rec-content">
                        <div style="color: ${severityColor}; font-weight: 500; text-transform: capitalize;">
                            ${escapeHtml(issue.type.replace(/_/g, ' '))}
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
    }
    
    html += '</div>';
    
    container.innerHTML = html;
}

async function sendChatMessage() {
    const input = document.getElementById('ai-chat-input');
    const messagesContainer = document.getElementById('ai-chat-messages');
    const question = input.value.trim();
    
    if (!question) return;
    
    messagesContainer.innerHTML += `<div class="ai-chat-message user">${escapeHtml(question)}</div>`;
    input.value = '';
    input.disabled = true;
    
    const loadingId = 'loading-' + Date.now();
    messagesContainer.innerHTML += `<div class="ai-chat-message assistant" id="${loadingId}">Thinking...</div>`;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const response = await fetch('/ai-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                context: analysisData
            })
        });
        
        const result = await response.json();
        const loadingEl = document.getElementById(loadingId);
        
        if (result.error) {
            loadingEl.className = 'ai-chat-message error';
            loadingEl.innerHTML = escapeHtml(result.error);
        } else {
            loadingEl.innerHTML = formatMarkdown(result.answer);
        }
    } catch (error) {
        const loadingEl = document.getElementById(loadingId);
        loadingEl.className = 'ai-chat-message error';
        loadingEl.innerHTML = 'Failed to get response: ' + escapeHtml(error.message);
    } finally {
        input.disabled = false;
        input.focus();
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

function resetAnalysis() {
    analysisData = null;
    // Reset zoom state
    pauseChartZoom = {
        startIndex: 0,
        endIndex: null,
        isDragging: false,
        dragStartX: null,
        selectionStart: null
    };
    document.getElementById('results').classList.remove('active');
    document.getElementById('upload-section').style.display = 'block';
    document.getElementById('file-input').value = '';
}

// Utility functions
function formatMs(ms) {
    if (ms === undefined || ms === null) return '-';
    if (ms >= 1000) return (ms / 1000).toFixed(2) + 's';
    return ms.toFixed(1) + 'ms';
}

function formatMB(mb) {
    if (mb === undefined || mb === null || mb === 0) return '-';
    if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB';
    return mb.toFixed(0) + ' MB';
}

function formatTime(val) {
    if (!val) return '-';
    if (typeof val === 'number') return val.toFixed(3) + 's';
    try {
        const d = new Date(val);
        return d.toLocaleTimeString();
    } catch {
        return val;
    }
}

function getPauseBadgeClass(ms) {
    if (!ms || ms <= 10) return 'fast';
    if (ms <= 100) return 'normal';
    if (ms <= 500) return 'slow';
    return 'critical';
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
    
    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*<\/li>)+/g, '<ul>$&</ul>');
    
    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    
    // Cleanup
    html = html.replace(/<p>\s*<\/p>/g, '');
    html = html.replace(/<p>(<h[123]>)/g, '$1');
    html = html.replace(/(<\/h[123]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');
    
    return html;
}

