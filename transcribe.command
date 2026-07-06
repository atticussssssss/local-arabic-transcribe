#!/bin/bash
# macOS double-click launcher.
# First run downloads the Whisper large-v3 model (~3GB) automatically.
# To reuse a model you already have:  export WHISPER_MODEL=/path/to/faster-whisper-large-v3
cd "$(dirname "$0")"
echo "==============================================="
echo " Arabic Subtitle SOP"
echo " Processing files in inbox/ ..."
echo "==============================================="
python3 run.py
echo ""
echo "Done. Results are in outputs/:"
echo "  <name>.srt           subtitles"
echo "  <name>.txt           plain text"
echo "  <name>.warnings.txt  segments to review by hand"
echo ""
echo "Press Enter to close."
read
