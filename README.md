# 🤖 GC Agent

Agentic AI-powered JVM Garbage Collection log analyzer with autonomous investigation and tuning recommendations.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Features

- **Multi-Collector Support**: G1GC, ZGC, Shenandoah, Parallel GC, CMS, Serial GC
- **Visual Analysis**: 
  - Interactive pause time charts with zoom
  - Heap usage over time
  - Pause time distribution
- **Issue Detection**:
  - Long GC pauses (>500ms)
  - Frequent Full GCs
  - Allocation failures
  - High GC frequency
  - Low throughput (<95%)
  - High heap utilization
- **Agentic AI Analysis**: Autonomous investigation using tools
- **Quick AI Analysis**: Fast summary with recommendations
- **Interactive Chat**: Ask questions about your GC logs

## Agentic Analysis

The **Agentic Triage** mode uses a ReAct-style agent that autonomously investigates your GC logs:

1. **Thinks** about what to investigate next
2. **Uses tools** to query specific data:
   - `get_summary` - Overall statistics
   - `get_long_pauses` - Find pauses above threshold
   - `get_full_gcs` - Analyze Full GC events
   - `get_allocation_failures` - Find allocation issues
   - `analyze_heap_trend` - Detect memory leaks
   - `analyze_pause_pattern` - Find pause anomalies
   - `compare_gc_phases` - Identify slow phases
   - `get_tuning_recommendations` - Get JVM flags
3. **Observes** results and decides next steps
4. **Concludes** with specific findings and recommendations

This provides deeper investigation than a single-shot prompt, with a visible trace of the agent's reasoning.

## Quick Start

### Prerequisites

- Python 3.8+
- [Ollama](https://ollama.ai/) (for AI analysis)

### Installation

```bash
git clone https://github.com/jimoconnell/gc-agent.git
cd gc-agent

# Run the application
./run.sh        # Linux/macOS
run.bat         # Windows
```

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
```

### Usage

1. Open http://localhost:5006 in your browser
2. Drag and drop your GC log files (or click to browse)
3. View the analysis dashboard
4. Click "Agentic Triage" for autonomous AI investigation

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GC_ANALYZER_HOST` | `0.0.0.0` | Server host |
| `GC_ANALYZER_PORT` | `5006` | Server port |
| `GC_ANALYZER_DEBUG` | `true` | Enable debug mode |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Ollama model for AI analysis |

## Supported Log Formats

### JDK 11+ Unified Logging

```bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
```

### JDK 8 Style

```bash
-XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log
```

## GC Collectors Supported

| Collector | JDK Versions | JVM Flags |
|-----------|--------------|-----------|
| G1GC | 8+ | `-XX:+UseG1GC` |
| ZGC | 11+ | `-XX:+UseZGC` |
| Shenandoah | 12+ | `-XX:+UseShenandoahGC` |
| Parallel | 8+ | `-XX:+UseParallelGC` |
| CMS | 8-14 | `-XX:+UseConcMarkSweepGC` |
| Serial | 8+ | `-XX:+UseSerialGC` |

## AI Setup

Install Ollama and pull a model:

```bash
# Install Ollama (macOS)
brew install ollama

# Start Ollama
ollama serve

# Pull a model
ollama pull qwen2.5:14b
```

## Screenshots

### Dashboard
- Summary cards with key metrics
- Interactive pause time chart with zoom
- Heap usage visualization

### Agentic Analysis
- Step-by-step investigation trace
- Tool usage visibility
- Specific JVM tuning recommendations

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
