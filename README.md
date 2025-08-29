🚀 Quick Start (Docker)
1. Build
docker build -t portfolio-dashboard .
2. Run
docker run --name portfolio -p 8000:8000 \
  -e JWT_SECRET_KEY='replace-this' \
  -e DATABASE_URL='sqlite:////tmp/app.db' \
  portfolio-dashboard
👉 Open http://localhost:8000
Default seeded user: admin / admin123
Or register a new user from the login page.
🐙 Docker Compose (alternative)
export JWT_SECRET_KEY='replace-this'
docker compose up --build
# open http://localhost:8000
Stop with:
docker compose down
💻 Run Locally (no Docker)
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
export JWT_SECRET_KEY='replace-this'
export DATABASE_URL='sqlite:///app.db'
python app.py
# open http://localhost:8000
