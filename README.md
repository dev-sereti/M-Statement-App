# MPesa Statement Processor

Upload encrypted MPesa PDF statements, unlock with PIN, extract transactions to Excel.

## Quick Start (Local Development)

### Backend (Terminal 1)
```bash
cd backend
python -m venv venv
venv\Scripts\activate # Linux: source venv/bin/activate        
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

### Frontend (Terminal 2)

cd frontend
npm install
npm run dev