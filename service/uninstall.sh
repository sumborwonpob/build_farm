#!/bin/bash

# Uninstall script for Build Farm Streamlit service
# This script removes the service files and cleans up

set -e

echo "Uninstalling Build Farm Streamlit service..."

# Stop the service if it's running
echo "Stopping streamlit service..."
sudo systemctl stop streamlit || true

# Disable the service
echo "Disabling streamlit service..."
sudo systemctl disable streamlit || true

# Remove systemd service file
echo "Removing /etc/systemd/system/streamlit.service..."
sudo rm -f /etc/systemd/system/streamlit.service

# Remove /opt/streamlit directory
echo "Removing /opt/streamlit directory..."
sudo rm -rf /opt/streamlit

# Reload systemd daemon
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo ""
echo "Uninstallation complete!"
echo ""
