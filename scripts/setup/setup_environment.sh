#!/bin/bash
# Civic Conversational OS - Environment Setup
# Sets up dedicated Python environment with all dependencies

set -e  # Exit on any error

echo "🏛️  Setting up Civic Conversational OS Environment"
echo "================================================="

# Check if we're in the right directory
if [ ! -f "CLAUDE.md" ]; then
    echo "❌ Error: Run this from the civic project root directory"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv civicos-env

# Activate environment
echo "🔌 Activating environment..."
source civicos-env/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install core dependencies first
echo "🏗️  Installing core civic platform dependencies..."
pip install requests beautifulsoup4 openai schedule PyYAML pytz certifi

# Install development tools
echo "🧪 Installing development dependencies..."
pip install pytest

# Install Phase 2A resilience dependencies (optional)
echo "🛡️  Installing Phase 2A resilience dependencies..."
echo "   (This enables vendor independence and data sovereignty)"

# Try to install CDP backend
if pip install cdp-backend; then
    echo "   ✅ CDP backend installed"
else
    echo "   ⚠️  CDP backend failed - continuing without it"
fi

# Try to install civic-scraper
if pip install civic-scraper; then
    echo "   ✅ civic-scraper installed"
else
    echo "   ⚠️  civic-scraper failed - continuing without it"
fi

# Try to install Google Cloud dependencies
if pip install google-cloud-firestore; then
    echo "   ✅ Google Cloud Firestore installed"
else
    echo "   ⚠️  Google Cloud Firestore failed - continuing without it"
fi

echo ""
echo "✅ Environment setup complete!"
echo ""
echo "🚀 To activate the environment:"
echo "   source civicos-env/bin/activate"
echo ""
echo "🧪 To test core functionality:"
echo "   python src/civic_digest.py test"
echo ""
echo "🛡️  To test Phase 2A resilience (if dependencies installed):"
echo "   python tests/test_phase2a_resilience_integration.py"
echo ""
echo "📊 To see what's installed:"
echo "   pip list"
echo ""
echo "💾 To save current dependencies:"
echo "   pip freeze > requirements-frozen.txt"