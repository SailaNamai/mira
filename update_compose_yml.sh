#!/bin/bash

# Get the current directory path
CURRENT_PATH=$(pwd)

# Prompt for VLC passkey
echo "Enter VLC passkey (press Enter for default 'vlcremote'): "
read -r VLC_PASSKEY
VLC_PASSKEY=${VLC_PASSKEY:-vlcremote}  # Use default if empty

# Create backup first
cp docker-compose.yml docker-compose.yml.backup

# Replace CONTAINER_PATH with current path
sed -i "s|CONTAINER_PATH=.*|CONTAINER_PATH=$CURRENT_PATH|" docker-compose.yml

# Replace VLC_PASSKEY with user input
sed -i "s|VLC_PASSKEY=.*|VLC_PASSKEY=$VLC_PASSKEY|" docker-compose.yml

echo "Successfully updated docker-compose.yml:"
echo "Backup created: docker-compose.yml.backup"
echo "CONTAINER_PATH set to: $CURRENT_PATH"
echo "VLC_PASSKEY set to: $VLC_PASSKEY"