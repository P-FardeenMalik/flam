#!/bin/bash
# QueueCTL Installation Script for Unix/Linux/Mac

echo "============================================================"
echo "QueueCTL Installation Script"
echo "============================================================"
echo ""

echo "Step 1: Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
echo ""

echo "Step 2: Installing QueueCTL package..."
pip install -e .
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install QueueCTL"
    exit 1
fi
echo ""

echo "Step 3: Verifying installation..."
python verify_install.py
if [ $? -ne 0 ]; then
    echo "ERROR: Installation verification failed"
    exit 1
fi
echo ""

echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "You can now use QueueCTL:"
echo "  queuectl --help"
echo "  queuectl enqueue '{\"id\":\"test\",\"command\":\"echo Hello\"}'"
echo ""
echo "Run ./quick_test.sh to test the system."
echo ""
