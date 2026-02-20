#!/bin/bash

# Initialize Python virtual environment and install dependencies

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVICE_DIR="$SCRIPT_DIR/service"

echo "Creating virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies from requirements.txt..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "Installation complete!"
echo ""
echo "============================================"
echo "Setting up systemd service..."
echo "============================================"
echo ""

# Prompt user to install systemd service
read -p "Do you want to install and enable the systemd service? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing systemd service..."
    sudo bash "$SERVICE_DIR/install.sh"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "Enabling and starting the service..."
        sudo systemctl enable streamlit
        sudo systemctl start streamlit
        echo "Service enabled and started!"
        echo ""
        echo "View service logs with: sudo journalctl -u streamlit -f"
    else
        echo "Service installation failed. Please check the error above."
        exit 1
    fi
else
    echo "Skipping systemd service installation."
    echo "To install the systemd service later, run: sudo bash $SERVICE_DIR/install.sh"
fi

echo ""
echo "To activate the virtual environment, run: source $VENV_DIR/bin/activate"
