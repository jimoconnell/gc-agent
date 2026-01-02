"""
Agentic GC Analysis Engine

Provides autonomous, tool-using AI analysis that can:
- Decide what to investigate next
- Call tools to gather specific data
- Follow chains of reasoning
- Proactively explore issues
"""

import json
import requests
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from config import OLLAMA_URL, OLLAMA_MODEL


class ToolType(Enum):
    """Types of tools the agent can use."""
    QUERY = "query"
    ANALYZE = "analyze"
    COMPARE = "compare"
    RECOMMEND = "recommend"


@dataclass
class Tool:
    """Definition of a tool the agent can use."""
    name: str
    description: str
    tool_type: ToolType
    parameters: Dict[str, str]
    handler: Callable


@dataclass
class AgentStep:
    """A single step in the agent's reasoning."""
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False


@dataclass
class AgentTrace:
    """Complete trace of agent's investigation."""
    steps: List[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    issues_found: List[Dict] = field(default_factory=list)
    recommendations: List[Dict] = field(default_factory=list)
    

class GCAgenticAnalyzer:
    """
    Agentic analyzer that autonomously investigates GC issues.
    
    The agent follows a ReAct-style loop:
    1. Think about what to investigate
    2. Choose a tool to use
    3. Observe the result
    4. Repeat until conclusion
    """
    
    def __init__(self, gc_data: Dict[str, Any]):
        self.gc_data = gc_data
        self.events = gc_data.get('events', [])
        self.statistics = gc_data.get('statistics', {})
        self.issues = gc_data.get('issues', [])
        self.collector_type = gc_data.get('collector_type', 'Unknown')
        self.trace = AgentTrace()
        self.max_steps = 8
        self.tools = self._register_tools()
    
    def _register_tools(self) -> Dict[str, Tool]:
        """Register all available tools."""
        return {
            "get_summary": Tool(
                name="get_summary",
                description="Get overall GC statistics summary including pause times, throughput, and heap usage",
                tool_type=ToolType.QUERY,
                parameters={},
                handler=self._tool_get_summary
            ),
            "get_long_pauses": Tool(
                name="get_long_pauses",
                description="Get all GC pauses longer than a specified threshold in milliseconds",
                tool_type=ToolType.QUERY,
                parameters={"threshold_ms": "minimum pause time in milliseconds (default: 200)"},
                handler=self._tool_get_long_pauses
            ),
            "get_full_gcs": Tool(
                name="get_full_gcs",
                description="Get all Full GC events with their details",
                tool_type=ToolType.QUERY,
                parameters={},
                handler=self._tool_get_full_gcs
            ),
            "get_allocation_failures": Tool(
                name="get_allocation_failures",
                description="Get events with allocation failures or to-space exhaustion",
                tool_type=ToolType.QUERY,
                parameters={},
                handler=self._tool_get_allocation_failures
            ),
            "analyze_heap_trend": Tool(
                name="analyze_heap_trend",
                description="Analyze heap usage trend over time to detect memory leaks or sizing issues",
                tool_type=ToolType.ANALYZE,
                parameters={},
                handler=self._tool_analyze_heap_trend
            ),
            "analyze_pause_pattern": Tool(
                name="analyze_pause_pattern",
                description="Analyze pause time patterns to identify problematic periods",
                tool_type=ToolType.ANALYZE,
                parameters={},
                handler=self._tool_analyze_pause_pattern
            ),
            "compare_gc_phases": Tool(
                name="compare_gc_phases",
                description="Compare different GC phases to identify which phase is causing issues",
                tool_type=ToolType.COMPARE,
                parameters={},
                handler=self._tool_compare_gc_phases
            ),
            "get_tuning_recommendations": Tool(
                name="get_tuning_recommendations",
                description="Get specific JVM tuning recommendations based on current findings",
                tool_type=ToolType.RECOMMEND,
                parameters={"issue_type": "type of issue to get recommendations for"},
                handler=self._tool_get_tuning_recommendations
            ),
            "final_answer": Tool(
                name="final_answer",
                description="Provide the final analysis conclusion when investigation is complete",
                tool_type=ToolType.ANALYZE,
                parameters={"conclusion": "the final analysis conclusion"},
                handler=self._tool_final_answer
            ),
        }
    
    # =========================================================================
    # TOOL IMPLEMENTATIONS
    # =========================================================================
    
    def _tool_get_summary(self, **kwargs) -> str:
        """Get overall statistics summary."""
        stats = self.statistics
        return f"""GC Summary for {self.collector_type}:
- Total GC Events: {stats.get('total_gc_events', 0):,}
- Pause Events: {stats.get('pause_events', 0):,}
- Full GC Count: {stats.get('full_gc_count', 0)}
- Total Pause Time: {stats.get('total_pause_time_seconds', 0):.2f}s
- Throughput: {stats.get('throughput_percent', 0):.1f}%
- Min Pause: {stats.get('min_pause_ms', 0):.1f}ms
- Max Pause: {stats.get('max_pause_ms', 0):.1f}ms
- Avg Pause: {stats.get('avg_pause_ms', 0):.1f}ms
- P95 Pause: {stats.get('p95_pause_ms', 0):.1f}ms
- P99 Pause: {stats.get('p99_pause_ms', 0):.1f}ms
- Max Heap: {stats.get('max_heap_mb', 0):.0f}MB
- GC Frequency: {stats.get('gc_frequency_per_minute', 0):.1f}/min
- Known Issues: {len(self.issues)}"""

    def _tool_get_long_pauses(self, threshold_ms: float = 200, **kwargs) -> str:
        """Get pauses longer than threshold."""
        try:
            threshold = float(threshold_ms)
        except:
            threshold = 200
            
        long_pauses = [e for e in self.events if e.get('pause_ms', 0) > threshold]
        
        if not long_pauses:
            return f"No pauses found longer than {threshold}ms"
        
        result = f"Found {len(long_pauses)} pauses > {threshold}ms:\n"
        for e in long_pauses[:10]:  # Limit to 10
            result += f"- {e.get('pause_type', e.get('gc_type', 'GC'))}: {e.get('pause_ms', 0):.1f}ms"
            if e.get('cause'):
                result += f" (cause: {e['cause']})"
            if e.get('heap_before_mb') and e.get('heap_after_mb'):
                result += f", heap: {e['heap_before_mb']:.0f}MB → {e['heap_after_mb']:.0f}MB"
            result += "\n"
        
        if len(long_pauses) > 10:
            result += f"... and {len(long_pauses) - 10} more\n"
        
        return result

    def _tool_get_full_gcs(self, **kwargs) -> str:
        """Get all Full GC events."""
        full_gcs = [e for e in self.events if e.get('is_full_gc', False)]
        
        if not full_gcs:
            return "No Full GC events found - this is good!"
        
        total_pause = sum(e.get('pause_ms', 0) for e in full_gcs)
        avg_pause = total_pause / len(full_gcs) if full_gcs else 0
        
        result = f"Found {len(full_gcs)} Full GC events:\n"
        result += f"- Total pause time from Full GCs: {total_pause:.1f}ms ({total_pause/1000:.2f}s)\n"
        result += f"- Average Full GC pause: {avg_pause:.1f}ms\n\n"
        result += "Details:\n"
        
        for e in full_gcs[:5]:
            result += f"- {e.get('pause_ms', 0):.1f}ms"
            if e.get('cause'):
                result += f" (cause: {e['cause']})"
            if e.get('heap_before_mb') and e.get('heap_after_mb'):
                reclaimed = e['heap_before_mb'] - e['heap_after_mb']
                result += f", reclaimed: {reclaimed:.0f}MB"
            result += "\n"
        
        if len(full_gcs) > 5:
            result += f"... and {len(full_gcs) - 5} more\n"
        
        return result

    def _tool_get_allocation_failures(self, **kwargs) -> str:
        """Get allocation failure events."""
        failures = [e for e in self.events if 'allocation_failure' in e.get('flags', [])]
        
        if not failures:
            return "No allocation failures detected - heap sizing appears adequate."
        
        result = f"⚠️ Found {len(failures)} allocation failures:\n"
        result += "This indicates the heap is too small or there's excessive allocation pressure.\n\n"
        
        for e in failures[:5]:
            result += f"- {e.get('pause_type', e.get('gc_type', 'GC'))}: {e.get('pause_ms', 0):.1f}ms"
            if e.get('heap_before_mb'):
                result += f", heap was {e['heap_before_mb']:.0f}MB"
            result += "\n"
        
        return result

    def _tool_analyze_heap_trend(self, **kwargs) -> str:
        """Analyze heap usage trend."""
        heap_events = [e for e in self.events if e.get('heap_after_mb', 0) > 0]
        
        if len(heap_events) < 3:
            return "Not enough heap data points to analyze trend."
        
        # Check if heap after GC is trending upward (potential leak)
        after_values = [e['heap_after_mb'] for e in heap_events]
        
        # Compare first third vs last third
        third = len(after_values) // 3
        if third < 1:
            return "Not enough data for trend analysis."
        
        first_avg = sum(after_values[:third]) / third
        last_avg = sum(after_values[-third:]) / third
        
        trend_pct = ((last_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0
        
        result = f"Heap Trend Analysis:\n"
        result += f"- Early GCs: avg {first_avg:.0f}MB after GC\n"
        result += f"- Recent GCs: avg {last_avg:.0f}MB after GC\n"
        result += f"- Trend: {trend_pct:+.1f}%\n\n"
        
        if trend_pct > 20:
            result += "⚠️ CONCERN: Heap usage after GC is trending upward significantly.\n"
            result += "This could indicate a memory leak or insufficient heap size.\n"
            self.trace.issues_found.append({
                "type": "memory_leak_suspected",
                "severity": "warning",
                "trend_percent": trend_pct
            })
        elif trend_pct > 50:
            result += "🚨 CRITICAL: Strong upward trend in heap usage - likely memory leak!\n"
            self.trace.issues_found.append({
                "type": "memory_leak_likely",
                "severity": "critical", 
                "trend_percent": trend_pct
            })
        else:
            result += "✓ Heap usage appears stable - no obvious memory leak.\n"
        
        return result

    def _tool_analyze_pause_pattern(self, **kwargs) -> str:
        """Analyze pause time patterns."""
        pause_events = [e for e in self.events if e.get('pause_ms', 0) > 0]
        
        if not pause_events:
            return "No pause data to analyze."
        
        pauses = [e['pause_ms'] for e in pause_events]
        
        # Find clusters of long pauses
        long_pause_threshold = self.statistics.get('avg_pause_ms', 50) * 2
        
        result = "Pause Pattern Analysis:\n"
        
        # Check for pause spikes
        max_pause = max(pauses)
        avg_pause = sum(pauses) / len(pauses)
        
        if max_pause > avg_pause * 10:
            result += f"⚠️ Significant pause spikes detected: max {max_pause:.1f}ms vs avg {avg_pause:.1f}ms\n"
            self.trace.issues_found.append({
                "type": "pause_spikes",
                "severity": "warning",
                "max_ms": max_pause,
                "avg_ms": avg_pause
            })
        
        # Check distribution
        dist = self.statistics.get('pause_distribution', {})
        long_pauses = dist.get('500ms-1s', 0) + dist.get('>1s', 0)
        total = sum(dist.values()) if dist else 1
        
        if long_pauses > 0:
            pct = (long_pauses / total) * 100
            result += f"- {long_pauses} pauses ({pct:.1f}%) are >= 500ms\n"
            if pct > 5:
                result += "  This is concerning for latency-sensitive applications.\n"
        
        # Check for increasing pause times
        if len(pauses) > 10:
            first_half = pauses[:len(pauses)//2]
            second_half = pauses[len(pauses)//2:]
            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)
            
            if second_avg > first_avg * 1.5:
                result += f"⚠️ Pause times increasing over time: {first_avg:.1f}ms → {second_avg:.1f}ms\n"
                self.trace.issues_found.append({
                    "type": "increasing_pauses",
                    "severity": "warning"
                })
        
        return result

    def _tool_compare_gc_phases(self, **kwargs) -> str:
        """Compare GC phases."""
        phase_stats = {}
        
        for e in self.events:
            phase = e.get('pause_type', e.get('gc_type', 'Unknown'))
            if phase not in phase_stats:
                phase_stats[phase] = {'count': 0, 'total_ms': 0, 'max_ms': 0}
            
            phase_stats[phase]['count'] += 1
            pause = e.get('pause_ms', 0)
            phase_stats[phase]['total_ms'] += pause
            phase_stats[phase]['max_ms'] = max(phase_stats[phase]['max_ms'], pause)
        
        if not phase_stats:
            return "No phase data available."
        
        result = "GC Phase Comparison:\n"
        
        # Sort by total time
        sorted_phases = sorted(phase_stats.items(), key=lambda x: x[1]['total_ms'], reverse=True)
        
        for phase, stats in sorted_phases[:8]:
            avg = stats['total_ms'] / stats['count'] if stats['count'] > 0 else 0
            result += f"- {phase}: {stats['count']} events, total {stats['total_ms']:.1f}ms, avg {avg:.1f}ms, max {stats['max_ms']:.1f}ms\n"
        
        # Identify worst phase
        if sorted_phases:
            worst = sorted_phases[0]
            result += f"\n⚠️ Most time-consuming phase: {worst[0]} ({worst[1]['total_ms']:.1f}ms total)\n"
        
        return result

    def _tool_get_tuning_recommendations(self, issue_type: str = "general", **kwargs) -> str:
        """Get JVM tuning recommendations."""
        collector = self.collector_type
        stats = self.statistics
        
        recommendations = []
        
        # Base recommendations on collector type
        if collector == "G1GC":
            if stats.get('max_pause_ms', 0) > 200:
                recommendations.append({
                    "flag": "-XX:MaxGCPauseMillis=200",
                    "reason": "Set target max pause time to 200ms",
                    "priority": "high"
                })
            if stats.get('full_gc_count', 0) > 0:
                recommendations.append({
                    "flag": "-XX:G1HeapRegionSize=<size>",
                    "reason": "Adjust region size (try 16m or 32m for large heaps)",
                    "priority": "medium"
                })
                recommendations.append({
                    "flag": "-XX:InitiatingHeapOccupancyPercent=35",
                    "reason": "Start marking earlier to avoid Full GCs",
                    "priority": "high"
                })
        
        elif collector == "ZGC":
            recommendations.append({
                "flag": "-XX:+UseZGC -XX:+ZGenerational",
                "reason": "Use generational ZGC for better performance (JDK 21+)",
                "priority": "medium"
            })
        
        elif collector == "Parallel":
            if stats.get('throughput_percent', 100) < 95:
                recommendations.append({
                    "flag": "-XX:GCTimeRatio=19",
                    "reason": "Target 95% throughput (1/(1+19) = 5% GC time)",
                    "priority": "medium"
                })
        
        # General recommendations based on issues
        if stats.get('max_heap_used_mb', 0) > stats.get('max_heap_mb', 1) * 0.85:
            recommendations.append({
                "flag": "-Xmx<larger>",
                "reason": "Heap utilization is >85%, consider increasing max heap",
                "priority": "high"
            })
        
        if any(i.get('type') == 'allocation_failure' for i in self.issues):
            recommendations.append({
                "flag": "-Xms<same as Xmx>",
                "reason": "Set initial heap equal to max to avoid resizing",
                "priority": "high"
            })
        
        if stats.get('gc_frequency_per_minute', 0) > 10:
            recommendations.append({
                "flag": "-XX:NewRatio=2",
                "reason": "Adjust young/old generation ratio to reduce GC frequency",
                "priority": "medium"
            })
        
        self.trace.recommendations = recommendations
        
        result = f"Tuning Recommendations for {collector}:\n\n"
        for rec in recommendations:
            priority_icon = "🔴" if rec['priority'] == 'high' else "🟡"
            result += f"{priority_icon} {rec['flag']}\n"
            result += f"   Reason: {rec['reason']}\n\n"
        
        if not recommendations:
            result += "No specific tuning recommendations - GC appears well-configured.\n"
        
        return result

    def _tool_final_answer(self, conclusion: str = "", **kwargs) -> str:
        """Mark the investigation as complete."""
        return conclusion

    # =========================================================================
    # AGENT EXECUTION
    # =========================================================================
    
    def _build_tools_description(self) -> str:
        """Build description of available tools for the prompt."""
        desc = "Available tools:\n\n"
        for name, tool in self.tools.items():
            desc += f"- {name}: {tool.description}\n"
            if tool.parameters:
                desc += f"  Parameters: {json.dumps(tool.parameters)}\n"
        return desc

    def _parse_agent_response(self, response: str) -> tuple[str, Optional[str], Optional[Dict]]:
        """Parse the agent's response to extract thought, action, and action input."""
        thought = ""
        action = None
        action_input = {}
        
        lines = response.strip().split('\n')
        current_section = None
        
        for line in lines:
            line_lower = line.lower().strip()
            
            if line_lower.startswith('thought:'):
                current_section = 'thought'
                thought = line.split(':', 1)[1].strip() if ':' in line else ""
            elif line_lower.startswith('action:'):
                current_section = 'action'
                action = line.split(':', 1)[1].strip() if ':' in line else ""
            elif line_lower.startswith('action input:') or line_lower.startswith('action_input:'):
                current_section = 'action_input'
                input_str = line.split(':', 1)[1].strip() if ':' in line else "{}"
                try:
                    action_input = json.loads(input_str) if input_str else {}
                except:
                    action_input = {"value": input_str}
            elif current_section == 'thought':
                thought += " " + line.strip()
            elif current_section == 'action_input':
                try:
                    action_input = json.loads(line.strip())
                except:
                    pass
        
        return thought.strip(), action, action_input

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with a prompt."""
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 500
                    }
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json().get('response', '')
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error calling LLM: {str(e)}"

    def run(self) -> AgentTrace:
        """Run the agentic analysis loop."""
        
        system_prompt = f"""You are an expert JVM GC analyst investigating garbage collection issues.
You have access to GC log data from a {self.collector_type} collector.

{self._build_tools_description()}

Follow this format for each step:
Thought: [your reasoning about what to investigate next]
Action: [the tool name to use]
Action Input: {{"param": "value"}}

When you have enough information, use the final_answer tool.

Be systematic: start with summary, identify issues, drill into specifics, then provide recommendations."""

        # Initial prompt with context
        initial_context = f"""Analyze this GC log data and identify any performance issues.

Quick stats:
- Collector: {self.collector_type}
- Total Events: {self.statistics.get('total_gc_events', 0)}
- Max Pause: {self.statistics.get('max_pause_ms', 0):.1f}ms
- Throughput: {self.statistics.get('throughput_percent', 0):.1f}%
- Full GCs: {self.statistics.get('full_gc_count', 0)}
- Known Issues: {len(self.issues)}

Begin your investigation."""

        conversation = system_prompt + "\n\n" + initial_context
        
        for step_num in range(1, self.max_steps + 1):
            # Get agent's next action
            response = self._call_llm(conversation)
            
            thought, action, action_input = self._parse_agent_response(response)
            
            step = AgentStep(
                step_number=step_num,
                thought=thought,
                action=action,
                action_input=action_input
            )
            
            # Execute the action
            if action and action in self.tools:
                tool = self.tools[action]
                try:
                    observation = tool.handler(**(action_input or {}))
                    step.observation = observation
                except Exception as e:
                    step.observation = f"Error executing tool: {str(e)}"
                
                if action == "final_answer":
                    step.is_final = True
                    self.trace.final_answer = action_input.get('conclusion', observation)
                    self.trace.steps.append(step)
                    break
            else:
                step.observation = f"Unknown tool: {action}. Available tools: {list(self.tools.keys())}"
            
            self.trace.steps.append(step)
            
            # Add to conversation for next iteration
            conversation += f"\n\nThought: {thought}\nAction: {action}\nAction Input: {json.dumps(action_input)}\nObservation: {step.observation}\n"
        
        # If we didn't get a final answer, generate one
        if not self.trace.final_answer:
            summary_prompt = conversation + "\n\nBased on your investigation, provide a final summary of findings and recommendations."
            final_response = self._call_llm(summary_prompt)
            self.trace.final_answer = final_response
        
        return self.trace

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary for JSON response."""
        return {
            "steps": [
                {
                    "step": s.step_number,
                    "thought": s.thought,
                    "action": s.action,
                    "action_input": s.action_input,
                    "observation": s.observation,
                    "is_final": s.is_final
                }
                for s in self.trace.steps
            ],
            "final_answer": self.trace.final_answer,
            "issues_found": self.trace.issues_found,
            "recommendations": self.trace.recommendations,
            "total_steps": len(self.trace.steps)
        }


def run_agentic_analysis(gc_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run agentic analysis on GC data."""
    analyzer = GCAgenticAnalyzer(gc_data)
    analyzer.run()
    return analyzer.to_dict()

