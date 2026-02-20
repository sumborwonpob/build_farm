#!/bin/bash

# Restart script for Build Farm Streamlit service

echo "Restarting streamlit service..."
sudo systemctl restart streamlit

echo "Service restarted successfully!"
echo ""
echo "View logs with: sudo journalctl -u streamlit -f"
