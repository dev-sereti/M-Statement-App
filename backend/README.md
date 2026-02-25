# MPesa Statement Processor - Backend

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run
uvicorn app.main:app --reload --port 8000

# Test
pytest -v