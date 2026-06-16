#!/bin/bash
# Legacy entry point — the React UI is the main app now.
cd "$(dirname "$0")"
echo "Note: The React UI replaced the old Streamlit app."
echo ""
exec ./run_react_ui.sh
