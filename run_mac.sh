#!/bin/bash
# Runs Macro Recorder on a Mac straight from the source code, without building.
# Run it in Terminal from this folder:   bash run_mac.sh
# Needs Python 3 from python.org. Give Terminal the Accessibility, Input Monitoring and
# Screen Recording permissions (System Settings > Privacy & Security).
cd "$(dirname "$0")/Source code"
python3 -m pip install -q -r requirements.txt
python3 macro_recorder.py
