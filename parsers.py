"""
GC Log Parsers for various JVM garbage collectors.
Supports: G1GC, ZGC, Shenandoah, Parallel GC, CMS, Serial GC
Works with JDK 8+ unified logging and legacy formats.
"""

import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple
from dateutil import parser as date_parser


# =============================================================================
# GC LOG PATTERNS
# =============================================================================

# JDK 11+ Unified Logging Format
UNIFIED_TIMESTAMP = re.compile(
    r'^\[(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.,]\d{3}[+-]\d{4})\]'
    r'|^\[(?P<uptime>\d+[.,]\d+)s\]'
)

UNIFIED_GC_START = re.compile(
    r'\[(?:info|debug)\s*\]\[gc(?:,\w+)*\s*\]\s*GC\((?P<gc_id>\d+)\)\s+(?P<gc_type>.+?)(?:\s+\((?P<cause>[^)]+)\))?$'
)

UNIFIED_GC_PAUSE = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Pause\s+(?P<pause_type>\w+(?:\s+\([^)]+\))?)\s+.*?(?P<pause_ms>\d+(?:\.\d+)?)\s*ms'
)

UNIFIED_HEAP = re.compile(
    r'GC\((?P<gc_id>\d+)\).*?(?P<heap_before>\d+)(?P<before_unit>[KMG])->(?P<heap_after>\d+)(?P<after_unit>[KMG])\((?P<heap_total>\d+)(?P<total_unit>[KMG])\)'
)

# JDK 8 Style Patterns
JDK8_TIMESTAMP = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.,]\d{3}[+-]\d{4}):\s*'
    r'|^(?P<uptime>\d+[.,]\d+):\s*'
)

JDK8_GC_EVENT = re.compile(
    r'\[(?P<gc_type>GC|Full GC)\s*(?:\((?P<cause>[^)]+)\))?\s*'
    r'(?:(?P<heap_before>\d+)K->(?P<heap_after>\d+)K\((?P<heap_total>\d+)K\))?,?\s*'
    r'(?:(?P<pause_ms>\d+(?:\.\d+)?)\s*(?:secs|ms))?\]'
)

# G1GC Specific Patterns
G1_PAUSE = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Pause\s+(?P<pause_type>Young|Mixed|Full|Remark|Cleanup)'
    r'(?:\s+\((?P<cause>[^)]+)\))?.*?(?P<pause_ms>\d+(?:\.\d+)?)\s*ms'
)

G1_CONCURRENT = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Concurrent\s+(?P<phase>\w+(?:\s+\w+)*)\s+(?P<duration_ms>\d+(?:\.\d+)?)\s*ms'
)

G1_PHASE = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+(?P<phase>Pre Evacuate|Evacuate|Post Evacuate|Other):\s+(?P<duration_ms>\d+(?:\.\d+)?)\s*ms'
)

# ZGC Specific Patterns
ZGC_PAUSE = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Pause\s+(?P<pause_type>\w+(?:\s+\w+)*)\s+(?P<pause_ms>\d+(?:\.\d+)?)\s*ms'
)

ZGC_CONCURRENT = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Concurrent\s+(?P<phase>\w+(?:\s+\w+)*)\s+(?P<duration_ms>\d+(?:\.\d+)?)\s*ms'
)

ZGC_STATS = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+(?:Used|Capacity|Free|Waste):\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[KMG])?B?'
)

# Shenandoah Patterns
SHENANDOAH_PAUSE = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Pause\s+(?P<pause_type>\w+(?:\s+\([^)]+\))?)\s+(?P<pause_ms>\d+(?:\.\d+)?)\s*ms'
)

SHENANDOAH_CONCURRENT = re.compile(
    r'GC\((?P<gc_id>\d+)\)\s+Concurrent\s+(?P<phase>\w+)\s+(?P<duration_ms>\d+(?:\.\d+)?)\s*ms'
)

# Parallel/CMS/Serial Patterns
PARALLEL_GC = re.compile(
    r'\[(?P<gc_type>PSYoungGen|ParOldGen|Full GC):\s+'
    r'(?P<before>\d+)K->(?P<after>\d+)K\((?P<total>\d+)K\)'
)

CMS_PHASE = re.compile(
    r'\[(?P<phase>CMS-initial-mark|CMS-concurrent-mark|CMS-concurrent-preclean|'
    r'CMS-concurrent-abortable-preclean|CMS-concurrent-sweep|CMS-concurrent-reset).*?\]'
)

# Common patterns for heap info
HEAP_SUMMARY = re.compile(
    r'(?:Heap\s+(?:before|after)\s+GC|Eden|Survivor|Old|Tenured|Metaspace|Class\s+space)[\s:]+(?P<info>.+)'
)

ALLOCATION_FAILURE = re.compile(r'Allocation\s+Failure|to-space\s+exhausted|evacuation\s+failure', re.IGNORECASE)

SAFEPOINT = re.compile(r'safepoint|Total\s+time\s+for\s+which\s+application\s+threads\s+were\s+stopped', re.IGNORECASE)


def normalize_size(value: float, unit: str) -> float:
    """Convert size to MB."""
    multipliers = {'K': 1/1024, 'M': 1, 'G': 1024, '': 1}
    return value * multipliers.get(unit.upper(), 1)


def parse_timestamp(line: str) -> Tuple[Optional[datetime], Optional[float], str]:
    """
    Parse timestamp from a GC log line.
    Returns (datetime, uptime_seconds, remaining_line)
    """
    # Try unified logging format
    match = UNIFIED_TIMESTAMP.match(line)
    if match:
        if match.group('timestamp'):
            try:
                ts = date_parser.parse(match.group('timestamp'))
                return ts, None, line[match.end():]
            except:
                pass
        elif match.group('uptime'):
            uptime = float(match.group('uptime').replace(',', '.'))
            return None, uptime, line[match.end():]
    
    # Try JDK 8 format
    match = JDK8_TIMESTAMP.match(line)
    if match:
        if match.group('timestamp'):
            try:
                ts = date_parser.parse(match.group('timestamp'))
                return ts, None, line[match.end():]
            except:
                pass
        elif match.group('uptime'):
            uptime = float(match.group('uptime').replace(',', '.'))
            return None, uptime, line[match.end():]
    
    return None, None, line


class GCEvent:
    """Represents a single GC event."""
    
    def __init__(self):
        self.gc_id: Optional[int] = None
        self.timestamp: Optional[datetime] = None
        self.uptime_seconds: Optional[float] = None
        self.gc_type: str = "Unknown"
        self.pause_type: str = ""
        self.cause: str = ""
        self.pause_ms: float = 0.0
        self.concurrent_ms: float = 0.0
        self.heap_before_mb: float = 0.0
        self.heap_after_mb: float = 0.0
        self.heap_total_mb: float = 0.0
        self.is_full_gc: bool = False
        self.is_concurrent: bool = False
        self.phases: List[Dict[str, Any]] = []
        self.raw_lines: List[str] = []
        self.flags: List[str] = []  # allocation failure, to-space exhausted, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'gc_id': self.gc_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'uptime_seconds': self.uptime_seconds,
            'gc_type': self.gc_type,
            'pause_type': self.pause_type,
            'cause': self.cause,
            'pause_ms': self.pause_ms,
            'concurrent_ms': self.concurrent_ms,
            'heap_before_mb': round(self.heap_before_mb, 2),
            'heap_after_mb': round(self.heap_after_mb, 2),
            'heap_total_mb': round(self.heap_total_mb, 2),
            'heap_reclaimed_mb': round(self.heap_before_mb - self.heap_after_mb, 2),
            'is_full_gc': self.is_full_gc,
            'is_concurrent': self.is_concurrent,
            'phases': self.phases,
            'flags': self.flags,
        }


class GCLogParser:
    """Main parser for GC logs."""
    
    def __init__(self, content: str):
        self.content = content
        self.lines = content.split('\n')
        self.events: List[GCEvent] = []
        self.collector_type: str = "Unknown"
        self.jvm_version: str = ""
        self.gc_flags: List[str] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.total_uptime_seconds: float = 0.0
        
    def detect_collector(self) -> str:
        """Detect which GC collector is being used."""
        content_lower = self.content.lower()
        
        if 'using g1' in content_lower or 'g1 heap' in content_lower or '[gc,heap' in content_lower:
            return "G1GC"
        elif 'using z garbage collector' in content_lower or 'zgc' in content_lower:
            return "ZGC"
        elif 'using shenandoah' in content_lower or 'shenandoah' in content_lower:
            return "Shenandoah"
        elif 'using parallel' in content_lower or 'psyounggen' in content_lower:
            return "Parallel"
        elif 'cms' in content_lower or 'concurrent mark sweep' in content_lower:
            return "CMS"
        elif 'using serial' in content_lower or 'defnew' in content_lower:
            return "Serial"
        else:
            return "Unknown"
    
    def parse(self) -> Dict[str, Any]:
        """Parse the GC log and return structured data."""
        self.collector_type = self.detect_collector()
        
        # Extract JVM info if available
        self._extract_jvm_info()
        
        # Parse GC events based on collector type
        if self.collector_type in ["G1GC", "ZGC", "Shenandoah"]:
            self._parse_unified_format()
        else:
            self._parse_legacy_format()
        
        # Calculate statistics
        stats = self._calculate_statistics()
        
        # Detect issues
        issues = self._detect_issues()
        
        return {
            'collector_type': self.collector_type,
            'jvm_version': self.jvm_version,
            'gc_flags': self.gc_flags,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_uptime_seconds': self.total_uptime_seconds,
            'events': [e.to_dict() for e in self.events],
            'statistics': stats,
            'issues': issues,
            'summary': self._generate_summary(stats, issues),
        }
    
    def _extract_jvm_info(self):
        """Extract JVM version and GC flags from log header."""
        for line in self.lines[:50]:  # Check first 50 lines
            if 'VM' in line or 'version' in line.lower():
                self.jvm_version = line.strip()
            if '-XX:' in line:
                # Extract GC-related flags
                flags = re.findall(r'-XX:[+\-]?\w+(?:=\S+)?', line)
                self.gc_flags.extend(flags)
    
    def _parse_unified_format(self):
        """Parse JDK 11+ unified logging format."""
        current_event: Optional[GCEvent] = None
        current_gc_id: Optional[int] = None
        
        for line in self.lines:
            if not line.strip():
                continue
            
            timestamp, uptime, remaining = parse_timestamp(line)
            
            # Track time range
            if timestamp:
                if self.start_time is None or timestamp < self.start_time:
                    self.start_time = timestamp
                if self.end_time is None or timestamp > self.end_time:
                    self.end_time = timestamp
            if uptime is not None:
                if uptime > self.total_uptime_seconds:
                    self.total_uptime_seconds = uptime
            
            # Check for GC pause events
            pause_match = G1_PAUSE.search(line) or ZGC_PAUSE.search(line) or SHENANDOAH_PAUSE.search(line)
            if pause_match:
                event = GCEvent()
                event.gc_id = int(pause_match.group('gc_id'))
                event.timestamp = timestamp
                event.uptime_seconds = uptime
                event.pause_type = pause_match.group('pause_type')
                event.pause_ms = float(pause_match.group('pause_ms'))
                event.gc_type = self.collector_type
                event.cause = pause_match.group('cause') if 'cause' in pause_match.groupdict() and pause_match.group('cause') else ""
                event.is_full_gc = 'full' in event.pause_type.lower()
                event.raw_lines.append(line)
                
                # Check for issues
                if ALLOCATION_FAILURE.search(line):
                    event.flags.append('allocation_failure')
                
                self.events.append(event)
                current_event = event
                current_gc_id = event.gc_id
                continue
            
            # Check for heap info
            heap_match = UNIFIED_HEAP.search(line)
            if heap_match and current_event and int(heap_match.group('gc_id')) == current_gc_id:
                current_event.heap_before_mb = normalize_size(
                    float(heap_match.group('heap_before')), 
                    heap_match.group('before_unit')
                )
                current_event.heap_after_mb = normalize_size(
                    float(heap_match.group('heap_after')), 
                    heap_match.group('after_unit')
                )
                current_event.heap_total_mb = normalize_size(
                    float(heap_match.group('heap_total')), 
                    heap_match.group('total_unit')
                )
                continue
            
            # Check for concurrent phases
            concurrent_match = G1_CONCURRENT.search(line) or ZGC_CONCURRENT.search(line) or SHENANDOAH_CONCURRENT.search(line)
            if concurrent_match:
                event = GCEvent()
                event.gc_id = int(concurrent_match.group('gc_id'))
                event.timestamp = timestamp
                event.uptime_seconds = uptime
                event.gc_type = self.collector_type
                event.is_concurrent = True
                event.concurrent_ms = float(concurrent_match.group('duration_ms'))
                event.pause_type = f"Concurrent {concurrent_match.group('phase')}"
                event.raw_lines.append(line)
                self.events.append(event)
                continue
    
    def _parse_legacy_format(self):
        """Parse JDK 8 and earlier GC log format."""
        for line in self.lines:
            if not line.strip():
                continue
            
            timestamp, uptime, remaining = parse_timestamp(line)
            
            # Track time range
            if timestamp:
                if self.start_time is None or timestamp < self.start_time:
                    self.start_time = timestamp
                if self.end_time is None or timestamp > self.end_time:
                    self.end_time = timestamp
            if uptime is not None:
                if uptime > self.total_uptime_seconds:
                    self.total_uptime_seconds = uptime
            
            # Check for GC events
            gc_match = JDK8_GC_EVENT.search(line)
            if gc_match:
                event = GCEvent()
                event.timestamp = timestamp
                event.uptime_seconds = uptime
                event.gc_type = gc_match.group('gc_type') or "GC"
                event.cause = gc_match.group('cause') or ""
                event.is_full_gc = 'full' in event.gc_type.lower()
                
                if gc_match.group('heap_before'):
                    event.heap_before_mb = float(gc_match.group('heap_before')) / 1024
                if gc_match.group('heap_after'):
                    event.heap_after_mb = float(gc_match.group('heap_after')) / 1024
                if gc_match.group('heap_total'):
                    event.heap_total_mb = float(gc_match.group('heap_total')) / 1024
                if gc_match.group('pause_ms'):
                    pause = float(gc_match.group('pause_ms'))
                    # Convert seconds to ms if needed
                    if 'secs' in line:
                        pause *= 1000
                    event.pause_ms = pause
                
                event.raw_lines.append(line)
                
                # Check for issues
                if ALLOCATION_FAILURE.search(line):
                    event.flags.append('allocation_failure')
                
                self.events.append(event)
                continue
            
            # Check for parallel GC specific
            parallel_match = PARALLEL_GC.search(line)
            if parallel_match:
                event = GCEvent()
                event.timestamp = timestamp
                event.uptime_seconds = uptime
                event.gc_type = parallel_match.group('gc_type')
                event.heap_before_mb = float(parallel_match.group('before')) / 1024
                event.heap_after_mb = float(parallel_match.group('after')) / 1024
                event.heap_total_mb = float(parallel_match.group('total')) / 1024
                event.is_full_gc = 'full' in event.gc_type.lower() or 'old' in event.gc_type.lower()
                event.raw_lines.append(line)
                self.events.append(event)
    
    def _calculate_statistics(self) -> Dict[str, Any]:
        """Calculate GC statistics."""
        if not self.events:
            return {}
        
        pause_events = [e for e in self.events if e.pause_ms > 0]
        full_gc_events = [e for e in self.events if e.is_full_gc]
        concurrent_events = [e for e in self.events if e.is_concurrent]
        
        pause_times = [e.pause_ms for e in pause_events]
        heap_usages = [(e.heap_after_mb, e.heap_total_mb) for e in self.events if e.heap_total_mb > 0]
        
        total_pause_ms = sum(pause_times)
        
        stats = {
            'total_gc_events': len(self.events),
            'pause_events': len(pause_events),
            'full_gc_count': len(full_gc_events),
            'concurrent_gc_count': len(concurrent_events),
            'total_pause_time_ms': round(total_pause_ms, 2),
            'total_pause_time_seconds': round(total_pause_ms / 1000, 2),
        }
        
        if pause_times:
            pause_times_sorted = sorted(pause_times)
            stats['min_pause_ms'] = round(min(pause_times), 2)
            stats['max_pause_ms'] = round(max(pause_times), 2)
            stats['avg_pause_ms'] = round(sum(pause_times) / len(pause_times), 2)
            stats['median_pause_ms'] = round(pause_times_sorted[len(pause_times_sorted) // 2], 2)
            stats['p95_pause_ms'] = round(pause_times_sorted[int(len(pause_times_sorted) * 0.95)], 2) if len(pause_times_sorted) > 1 else stats['max_pause_ms']
            stats['p99_pause_ms'] = round(pause_times_sorted[int(len(pause_times_sorted) * 0.99)], 2) if len(pause_times_sorted) > 1 else stats['max_pause_ms']
        
        if heap_usages:
            stats['max_heap_mb'] = round(max(h[1] for h in heap_usages), 2)
            stats['max_heap_used_mb'] = round(max(h[0] for h in heap_usages), 2)
            stats['avg_heap_used_mb'] = round(sum(h[0] for h in heap_usages) / len(heap_usages), 2)
        
        # Calculate throughput
        if self.total_uptime_seconds > 0:
            gc_time_seconds = total_pause_ms / 1000
            throughput = ((self.total_uptime_seconds - gc_time_seconds) / self.total_uptime_seconds) * 100
            stats['throughput_percent'] = round(throughput, 2)
        
        # GC frequency
        if self.total_uptime_seconds > 0 and pause_events:
            stats['gc_frequency_per_minute'] = round((len(pause_events) / self.total_uptime_seconds) * 60, 2)
        
        # Pause time distribution
        if pause_times:
            buckets = {'0-10ms': 0, '10-50ms': 0, '50-100ms': 0, '100-500ms': 0, '500ms-1s': 0, '>1s': 0}
            for pt in pause_times:
                if pt <= 10:
                    buckets['0-10ms'] += 1
                elif pt <= 50:
                    buckets['10-50ms'] += 1
                elif pt <= 100:
                    buckets['50-100ms'] += 1
                elif pt <= 500:
                    buckets['100-500ms'] += 1
                elif pt <= 1000:
                    buckets['500ms-1s'] += 1
                else:
                    buckets['>1s'] += 1
            stats['pause_distribution'] = buckets
        
        return stats
    
    def _detect_issues(self) -> List[Dict[str, Any]]:
        """Detect potential issues in the GC log."""
        issues = []
        
        pause_events = [e for e in self.events if e.pause_ms > 0]
        full_gc_events = [e for e in self.events if e.is_full_gc]
        
        # Long pause detection
        long_pauses = [e for e in pause_events if e.pause_ms > 500]
        if long_pauses:
            max_pause = max(e.pause_ms for e in long_pauses)
            issues.append({
                'type': 'long_pause',
                'severity': 'critical' if max_pause > 1000 else 'warning',
                'count': len(long_pauses),
                'max_pause_ms': round(max_pause, 2),
                'description': f"Detected {len(long_pauses)} GC pauses > 500ms (max: {max_pause:.1f}ms)",
            })
        
        # Frequent Full GC
        if len(full_gc_events) > 5:
            issues.append({
                'type': 'frequent_full_gc',
                'severity': 'critical' if len(full_gc_events) > 10 else 'warning',
                'count': len(full_gc_events),
                'description': f"Detected {len(full_gc_events)} Full GC events - may indicate memory pressure",
            })
        
        # Allocation failures
        alloc_failures = [e for e in self.events if 'allocation_failure' in e.flags]
        if alloc_failures:
            issues.append({
                'type': 'allocation_failure',
                'severity': 'critical',
                'count': len(alloc_failures),
                'description': f"Detected {len(alloc_failures)} allocation failures - heap may be too small",
            })
        
        # High GC frequency
        if self.total_uptime_seconds > 60:
            gc_per_minute = (len(pause_events) / self.total_uptime_seconds) * 60
            if gc_per_minute > 10:
                issues.append({
                    'type': 'high_gc_frequency',
                    'severity': 'warning',
                    'frequency': round(gc_per_minute, 2),
                    'description': f"High GC frequency: {gc_per_minute:.1f} GCs/minute",
                })
        
        # Low throughput
        if self.total_uptime_seconds > 60 and pause_events:
            total_pause_seconds = sum(e.pause_ms for e in pause_events) / 1000
            throughput = ((self.total_uptime_seconds - total_pause_seconds) / self.total_uptime_seconds) * 100
            if throughput < 95:
                issues.append({
                    'type': 'low_throughput',
                    'severity': 'critical' if throughput < 90 else 'warning',
                    'throughput_percent': round(throughput, 2),
                    'description': f"Low application throughput: {throughput:.1f}% (target: >95%)",
                })
        
        # Heap utilization trending high
        heap_events = [e for e in self.events if e.heap_after_mb > 0 and e.heap_total_mb > 0]
        if len(heap_events) > 10:
            recent_utilization = [e.heap_after_mb / e.heap_total_mb * 100 for e in heap_events[-10:]]
            avg_util = sum(recent_utilization) / len(recent_utilization)
            if avg_util > 85:
                issues.append({
                    'type': 'high_heap_utilization',
                    'severity': 'warning',
                    'avg_utilization_percent': round(avg_util, 2),
                    'description': f"High heap utilization: {avg_util:.1f}% average in recent GCs",
                })
        
        return issues
    
    def _generate_summary(self, stats: Dict[str, Any], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a human-readable summary."""
        severity = 'healthy'
        if any(i['severity'] == 'critical' for i in issues):
            severity = 'critical'
        elif any(i['severity'] == 'warning' for i in issues):
            severity = 'warning'
        
        summary_text = f"{self.collector_type} collector, "
        summary_text += f"{stats.get('total_gc_events', 0)} GC events"
        
        if stats.get('max_pause_ms'):
            summary_text += f", max pause {stats['max_pause_ms']:.1f}ms"
        
        if stats.get('throughput_percent'):
            summary_text += f", throughput {stats['throughput_percent']:.1f}%"
        
        if issues:
            critical_count = sum(1 for i in issues if i['severity'] == 'critical')
            warning_count = sum(1 for i in issues if i['severity'] == 'warning')
            if critical_count:
                summary_text += f" ⚠️ {critical_count} critical issues"
            if warning_count:
                summary_text += f" ⚠ {warning_count} warnings"
        
        return {
            'severity': severity,
            'text': summary_text,
            'issue_count': len(issues),
            'critical_count': sum(1 for i in issues if i['severity'] == 'critical'),
            'warning_count': sum(1 for i in issues if i['severity'] == 'warning'),
        }


def parse_gc_log(content: str) -> Dict[str, Any]:
    """Parse a GC log and return structured data."""
    parser = GCLogParser(content)
    return parser.parse()

