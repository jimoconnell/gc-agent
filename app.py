#!/usr/bin/env python3
"""
GC Agent - Agentic AI-powered JVM Garbage Collection analysis
Visualize GC activity, detect issues, and get autonomous AI-powered tuning recommendations.
https://github.com/jimoconnell/gc-agent
"""

import os
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from parsers import parse_gc_log
from agentic import run_agentic_analysis
from config import (
    OLLAMA_URL, OLLAMA_MODEL, HOST, PORT, DEBUG,
    MAX_CONTENT_LENGTH, UPLOAD_FOLDER
)

app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def static_files(path):
    """Serve static files."""
    return send_from_directory('static', path)


@app.route('/ai-health', methods=['GET'])
def ai_health():
    """Check if Ollama is available for AI analysis."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if response.status_code == 200:
            return jsonify({
                'available': True,
                'url': OLLAMA_URL,
                'model': OLLAMA_MODEL
            })
        else:
            return jsonify({'available': False, 'reason': 'Ollama not responding'})
    except requests.exceptions.ConnectionError:
        return jsonify({'available': False, 'reason': 'Cannot connect to Ollama'})
    except requests.exceptions.Timeout:
        return jsonify({'available': False, 'reason': 'Ollama timeout'})
    except Exception as e:
        return jsonify({'available': False, 'reason': str(e)})


@app.route('/analyze', methods=['POST'])
def analyze():
    """Analyze uploaded GC log files."""
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
    
    # Combine all file contents
    combined_content = ""
    filenames = []
    
    for file in files:
        if file and file.filename:
            try:
                content = file.read().decode('utf-8', errors='replace')
                combined_content += content + "\n"
                filenames.append(secure_filename(file.filename))
            except Exception as e:
                return jsonify({'error': f'Error reading {file.filename}: {str(e)}'}), 400
    
    if not combined_content.strip():
        return jsonify({'error': 'No valid content to analyze'}), 400
    
    try:
        result = parse_gc_log(combined_content)
        result['filenames'] = filenames
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Analysis error: {str(e)}'}), 500


@app.route('/ai-analyze', methods=['POST'])
def ai_analyze():
    """Get AI-powered analysis of the GC log data."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Build a focused prompt for GC analysis
        stats = data.get('statistics', {})
        issues = data.get('issues', [])
        summary = data.get('summary', {})
        collector = data.get('collector_type', 'Unknown')
        events = data.get('events', [])
        
        # Format issues for the prompt
        issues_text = ""
        for issue in issues:
            issues_text += f"  - [{issue.get('severity', 'unknown').upper()}] {issue.get('type', '')}: {issue.get('description', '')}\n"
        
        # Sample some events for context
        event_samples = ""
        long_pauses = [e for e in events if e.get('pause_ms', 0) > 200][:5]
        for e in long_pauses:
            event_samples += f"  - {e.get('pause_type', e.get('gc_type', 'GC'))}: {e.get('pause_ms', 0):.1f}ms, heap {e.get('heap_before_mb', 0):.0f}MB -> {e.get('heap_after_mb', 0):.0f}MB\n"
        
        prompt = f"""You are an expert JVM performance engineer analyzing GC (Garbage Collection) logs. Analyze the following data and provide actionable insights.

## GC Summary
- Collector: {collector}
- Total GC Events: {stats.get('total_gc_events', 0):,}
- Full GC Count: {stats.get('full_gc_count', 0)}
- Pause Events: {stats.get('pause_events', 0):,}
- Total Pause Time: {stats.get('total_pause_time_seconds', 0):.2f} seconds
- Throughput: {stats.get('throughput_percent', 0):.1f}%

## Pause Statistics
- Min Pause: {stats.get('min_pause_ms', 0):.2f}ms
- Max Pause: {stats.get('max_pause_ms', 0):.2f}ms
- Average Pause: {stats.get('avg_pause_ms', 0):.2f}ms
- P95 Pause: {stats.get('p95_pause_ms', 0):.2f}ms
- P99 Pause: {stats.get('p99_pause_ms', 0):.2f}ms

## Heap Statistics
- Max Heap: {stats.get('max_heap_mb', 0):.0f} MB
- Max Heap Used: {stats.get('max_heap_used_mb', 0):.0f} MB
- GC Frequency: {stats.get('gc_frequency_per_minute', 0):.1f} GCs/minute

## Detected Issues
{issues_text if issues_text else "No significant issues detected."}

## Sample Long Pause Events
{event_samples if event_samples else "No notably long pauses."}

---

Based on this data, provide:
1. **Executive Summary**: What's the overall health of GC in 2-3 sentences?
2. **Root Cause Analysis**: What's causing the main issues? Be specific.
3. **Tuning Recommendations**: Specific JVM flags and values to try.
4. **Performance Impact**: How is GC affecting application performance?
5. **Priority Actions**: What should be fixed first?

Be specific and provide actionable recommendations with actual JVM flag values where appropriate."""

        # Call Ollama
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 2000
                }
            },
            timeout=120
        )
        
        if response.status_code != 200:
            return jsonify({'error': f'Ollama error: {response.text}'}), 500
        
        result = response.json()
        return jsonify({
            'analysis': result.get('response', 'No response from model'),
            'model': OLLAMA_MODEL,
            'prompt_tokens': result.get('prompt_eval_count', 0),
            'response_tokens': result.get('eval_count', 0)
        })
        
    except requests.exceptions.ConnectionError:
        return jsonify({'error': f'Cannot connect to Ollama at {OLLAMA_URL}. Is it running?'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Ollama request timed out. Try again or use a smaller model.'}), 504
    except Exception as e:
        return jsonify({'error': f'AI analysis error: {str(e)}'}), 500


@app.route('/ai-chat', methods=['POST'])
def ai_chat():
    """Chat with AI about the GC log data."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        question = data.get('question', '')
        context = data.get('context', {})
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        # Build context from GC data
        stats = context.get('statistics', {})
        collector = context.get('collector_type', 'Unknown')
        issues = context.get('issues', [])
        
        issues_summary = ", ".join([f"{i.get('type', '')}" for i in issues[:5]]) if issues else "none detected"
        
        system_context = f"""You are an expert JVM GC tuning assistant. You have access to GC log analysis data:

GC Summary:
- Collector: {collector}
- Total Events: {stats.get('total_gc_events', 0):,}
- Full GCs: {stats.get('full_gc_count', 0)}
- Max Pause: {stats.get('max_pause_ms', 0):.1f}ms
- Avg Pause: {stats.get('avg_pause_ms', 0):.1f}ms
- Throughput: {stats.get('throughput_percent', 0):.1f}%
- Max Heap: {stats.get('max_heap_mb', 0):.0f}MB
- Issues: {issues_summary}

Answer questions about GC tuning concisely and accurately. Provide specific JVM flags when relevant."""

        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": f"{system_context}\n\nUser Question: {question}\n\nAnswer:",
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 1000
                }
            },
            timeout=60
        )
        
        if response.status_code != 200:
            return jsonify({'error': f'Ollama error: {response.text}'}), 500
        
        result = response.json()
        return jsonify({
            'answer': result.get('response', 'No response from model'),
            'model': OLLAMA_MODEL
        })
        
    except requests.exceptions.ConnectionError:
        return jsonify({'error': f'Cannot connect to Ollama at {OLLAMA_URL}'}), 503
    except Exception as e:
        return jsonify({'error': f'Chat error: {str(e)}'}), 500


@app.route('/agentic-analyze', methods=['POST'])
def agentic_analyze():
    """
    Run agentic AI analysis that autonomously investigates GC issues.
    
    The agent uses tools to:
    - Query specific data
    - Analyze patterns
    - Compare phases
    - Generate recommendations
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Run the agentic analysis
        result = run_agentic_analysis(data)
        
        return jsonify({
            'success': True,
            'model': OLLAMA_MODEL,
            'agentic': True,
            **result
        })
        
    except requests.exceptions.ConnectionError:
        return jsonify({'error': f'Cannot connect to Ollama at {OLLAMA_URL}. Is it running?'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Agentic analysis timed out. Try again.'}), 504
    except Exception as e:
        return jsonify({'error': f'Agentic analysis error: {str(e)}'}), 500


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  🤖 GC Agent")
    print("  Agentic AI-powered GC Log Analysis")
    print(f"  Open http://localhost:{PORT} in your browser")
    print("="*60 + "\n")
    app.run(debug=DEBUG, host=HOST, port=PORT)

