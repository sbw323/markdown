#!/bin/bash

VM_NAME="python-agent-node"
ZONE="us-east4-a"

echo "Starting local watchdog for $VM_NAME..."

while true; do
    # Fetch current VM status silently
    STATUS=$(gcloud compute instances describe $VM_NAME --zone=$ZONE --format="value(status)" 2>/dev/null)

    if [ "$STATUS" == "TERMINATED" ]; then
        echo "$(date): Spot VM preempted. Attempting to restart..."
        gcloud compute instances start $VM_NAME --zone=$ZONE
        
    elif [ "$STATUS" == "RUNNING" ]; then
        # Optional: You can comment this out if you don't want it spamming your terminal
        echo "$(date): VM is running smoothly."
        
    else
        echo "$(date): VM status is $STATUS. Waiting..."
    fi

    # Wait 60 seconds before polling the API again to avoid rate limits
    sleep 60
done