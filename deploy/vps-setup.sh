#!/bin/bash
# VPS Setup Script for Scheduling Project
# Run with: sudo bash /opt/slg/scheduling/deploy/vps-setup.sh

set -e

echo "=== Step 1: Install pip ==="
apt install -y python3-pip

echo "=== Step 2: Create project directory ==="
mkdir -p /opt/slg/scheduling
chown zack:zack /opt/slg/scheduling

echo "=== Step 3: Create Python virtual environment ==="
cd /opt/slg/scheduling
sudo -u zack python3 -m venv .venv
sudo -u zack .venv/bin/pip install --upgrade pip

echo "=== Step 4: Install Python dependencies ==="
sudo -u zack .venv/bin/pip install \
    playwright==1.50.0 \
    pydantic==2.10.6 \
    pydantic-settings==2.7.1 \
    structlog==25.1.0 \
    tenacity==9.0.0 \
    requests==2.32.3 \
    python-dotenv==1.0.1

echo "=== Step 5: Install Playwright Chromium (headless) ==="
sudo -u zack .venv/bin/playwright install chromium
# Install system dependencies for Chromium
.venv/bin/playwright install-deps chromium

echo "=== Step 6: Create log directory ==="
mkdir -p /var/log/scheduling
chown zack:zack /var/log/scheduling

echo "=== Step 7: Create data directories ==="
sudo -u zack mkdir -p /opt/slg/scheduling/data/state
sudo -u zack mkdir -p /opt/slg/scheduling/reports

echo ""
echo "=== SETUP COMPLETE ==="
echo "Python: $(python3 --version)"
echo "Venv: /opt/slg/scheduling/.venv"
echo "Playwright: $(.venv/bin/python -c 'import playwright; print(playwright.__version__)')"
echo ""
echo "Next steps:"
echo "  1. Copy project files to /opt/slg/scheduling/"
echo "  2. Create /opt/slg/scheduling/.env with credentials"
echo "  3. Test: cd /opt/slg/scheduling && .venv/bin/python scripts/scrape_schedules.py --weekly-teachers"
