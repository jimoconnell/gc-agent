"""
Configuration for GC Log Analyzer.
"""

import os

# Ollama configuration
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:14b')

# Server configuration
HOST = os.environ.get('GC_ANALYZER_HOST', '0.0.0.0')
PORT = int(os.environ.get('GC_ANALYZER_PORT', '5006'))
DEBUG = os.environ.get('GC_ANALYZER_DEBUG', 'true').lower() == 'true'
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max upload

# Upload folder
UPLOAD_FOLDER = '/tmp/gc-log-analyzer'

