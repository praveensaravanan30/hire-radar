#!/usr/bin/env bash
# One-time setup for the job tracker.
set -e

cd "$(dirname "$0")"

echo "→ Creating Python virtual environment..."
python3 -m venv .venv

echo "→ Installing dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "→ Setting up .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   Created .env from template — add your ANTHROPIC_API_KEY before running!"
else
    echo "   .env already exists, skipping."
fi

echo ""
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit tracker/.env and add your ANTHROPIC_API_KEY"
echo "     (optional: also add ADZUNA_APP_ID/KEY and/or RAPIDAPI_JSEARCH_KEY)"
echo ""
echo "  2. Run once to test:"
echo "     .venv/bin/python tracker.py"
echo ""
echo "  3. Run on a schedule (every 3 hours in the background):"
echo "     .venv/bin/python tracker.py --loop &"
echo ""
echo "  4. Or add to cron to auto-start (runs every 3 hours):"
echo "     crontab -e"
echo "     Add: 0 */3 * * * cd $(pwd) && .venv/bin/python tracker.py >> logs/tracker.log 2>&1"
echo ""
echo "  5. See today's matches anytime:"
echo "     .venv/bin/python tracker.py --digest"
