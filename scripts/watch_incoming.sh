#!/bin/bash
# File watcher using inotify for incoming directory
# Monitors for new account files and processes them automatically

INCOMING_DIR="/app/incoming"
API_URL="http://localhost:8000/accounts/process"

echo "Starting file watcher for $INCOMING_DIR"
echo "API endpoint: $API_URL"

# Check if inotifywait is installed
if ! command -v inotifywait &> /dev/null; then
    echo "ERROR: inotifywait is not installed"
    echo "Install it with: apt-get install inotify-tools"
    exit 1
fi

# Create incoming directory if it doesn't exist
mkdir -p "$INCOMING_DIR"

# Monitor for new files
inotifywait -m -e close_write --format '%f' "$INCOMING_DIR" | while read FILE
do
    # Only process ZIP and session files
    if [[ "$FILE" == *.zip ]] || [[ "$FILE" == *.session ]]; then
        echo "[$(date)] New file detected: $FILE"

        # Wait a moment to ensure file is fully written
        sleep 1

        # Call API to process the file
        RESPONSE=$(curl -s -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -d "{\"file_path\": \"$INCOMING_DIR/$FILE\"}")

        echo "[$(date)] API response: $RESPONSE"

        # Check if processing was successful
        if echo "$RESPONSE" | grep -q '"success":true'; then
            echo "[$(date)] Successfully processed: $FILE"
        else
            echo "[$(date)] Failed to process: $FILE"
            # Move failed file to error directory
            mkdir -p "$INCOMING_DIR/errors"
            mv "$INCOMING_DIR/$FILE" "$INCOMING_DIR/errors/" 2>/dev/null
        fi
    fi
done
