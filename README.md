# MPesa Statement Processor

Upload encrypted MPesa PDF statements, unlock with PIN, extract transactions to Excel.

## Quick Start (Local Development)

### Backend (Terminal 1)
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev