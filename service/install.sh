#!/bin/bash

# Installation script for Build Farm Streamlit service
# This script generates service files from templates and installs them

set -e

echo "Installing Build Farm Streamlit service..."

# Get the directory where this script is located (service directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$SCRIPT_DIR/unit"

# Get the project root directory (one level up from service/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_FRONTEND_DIR="$PROJECT_ROOT/frontend"
SERVICE_SCRIPT_PATH="/opt/streamlit"

# Get the actual user (not root if running with sudo)
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$(whoami)"
fi

echo "Project root: $PROJECT_ROOT"
echo "Frontend dir: $PROJECT_FRONTEND_DIR"
echo "Service user: $SERVICE_USER"
echo ""

# Verify template files exist
if [ ! -f "$SCRIPT_DIR/run_streamlit.sh.template" ]; then
    echo "Error: Template file not found at $SCRIPT_DIR/run_streamlit.sh.template"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/streamlit.service.template" ]; then
    echo "Error: Template file not found at $SCRIPT_DIR/streamlit.service.template"
    exit 1
fi

# Generate run_streamlit.sh from template
echo "Generating run_streamlit.sh from template..."
sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
    -e "s|{{PROJECT_FRONTEND_DIR}}|$PROJECT_FRONTEND_DIR|g" \
    "$SCRIPT_DIR/run_streamlit.sh.template" > "$UNIT_DIR/run_streamlit.sh"

# Generate streamlit.service from template
echo "Generating streamlit.service from template..."
sed -e "s|{{SERVICE_USER}}|$SERVICE_USER|g" \
    -e "s|{{PROJECT_FRONTEND_DIR}}|$PROJECT_FRONTEND_DIR|g" \
    -e "s|{{SERVICE_SCRIPT_PATH}}|$SERVICE_SCRIPT_PATH|g" \
    "$SCRIPT_DIR/streamlit.service.template" > "$UNIT_DIR/streamlit.service"

# Create /opt/streamlit directory if it doesn't exist
echo "Creating $SERVICE_SCRIPT_PATH directory..."
sudo mkdir -p "$SERVICE_SCRIPT_PATH"

# Copy generated run_streamlit.sh to /opt/streamlit/
echo "Installing run_streamlit.sh to $SERVICE_SCRIPT_PATH/..."
sudo cp "$UNIT_DIR/run_streamlit.sh" "$SERVICE_SCRIPT_PATH/run_streamlit.sh"
sudo chmod +x "$SERVICE_SCRIPT_PATH/run_streamlit.sh"

# Copy generated streamlit.service to /etc/systemd/system/
echo "Installing streamlit.service to /etc/systemd/system/..."
sudo cp "$UNIT_DIR/streamlit.service" /etc/systemd/system/streamlit.service
sudo chmod 644 /etc/systemd/system/streamlit.service

# Reload systemd daemon
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo ""
echo "✅ Installation complete!"
echo ""
echo "Available commands:"
echo "  Start service:   sudo systemctl start streamlit"
echo "  Stop service:    sudo systemctl stop streamlit"
echo "  Restart service: sudo systemctl restart streamlit"
echo "  Enable on boot:  sudo systemctl enable streamlit"
echo "  View logs:       sudo journalctl -u streamlit -f"
echo ""
