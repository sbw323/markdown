#!/bin/bash

TARGET_DIR="_agent_work"

# 1. Clear the contents if the directory exists (preserves the parent folder permissions)
if [ -d "$TARGET_DIR" ]; then
    find "$TARGET_DIR" -mindepth 1 -delete
fi

# 2. Recreate the specific subdirectories
mkdir -p "$TARGET_DIR"/{_bak,_runs,_checkpoint_sprint0,_checkpoint_sprint1,test_output}

echo "Successfully wiped '$TARGET_DIR' and restored the default subdirectory structure."
