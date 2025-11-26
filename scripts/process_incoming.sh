#!/bin/bash
# Cron-based file processor for incoming directory
# Run this script every minute via cron: * * * * * /app/scripts/process_incoming.sh

INCOMING_DIR="/app/incoming"
API_URL="http://localhost:8000/accounts/process"
LOCK_FILE="/tmp/process_incoming.lock"

# Check if another instance is running
if [ -f "$LOCK_FILE" ]; then
    # Check if process is actually running
    if ps -p $(cat "$LOCK_FILE") > /dev/null 2>&1; then
        echo "Another instance is already running"
        exit 0
    else
        # Stale lock file, remove it
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"

# Cleanup on exit
trap "rm -f $LOCK_FILE" EXIT

# Create incoming directory if it doesn't exist
mkdir -p "$INCOMING_DIR"

# Process each file in incoming directory
for file in "$INCOMING_DIR"/*.zip "$INCOMING_DIR"/*.session; do
    # Skip if no files found
    [ -e "$file" ] || continue

    filename=$(basename "$file")
    echo "[$(date)] Processing: $filename"

    # Call API to process the file
    RESPONSE=$(curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "{\"file_path\": \"$file\"}" \
        --max-time 60)

    # Check if API call was successful
    if [ $? -eq 0 ]; then
        echo "[$(date)] API response: $RESPONSE"

        # Check if processing was successful
        if echo "$RESPONSE" | grep -q '"success":true'; then
            echo "[$(date)] Successfully processed: $filename"
            # File should be moved by the API, but double-check
            if [ -f "$file" ]; then
                echo "[$(date)] Warning: File still exists after processing"
            fi
        else
            echo "[$(date)] Failed to process: $filename"
            # Move failed file to error directory
            mkdir -p "$INCOMING_DIR/errors"
            mv "$file" "$INCOMING_DIR/errors/" 2>/dev/null
        fi
    else
        echo "[$(date)] API call failed for: $filename"
    fi

    # Small delay between files
    sleep 2
done

echo "[$(date)] Processing cycle completed"
