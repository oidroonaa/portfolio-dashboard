**🚀 Quick Start (Docker)**
1) Build
`docker build -t portfolio-dashboard .`
2) Run
`docker run --name portfolio -p 8000:8000 \
  -e JWT_SECRET_KEY='replace-this' \
  -e DATABASE_URL='sqlite:////tmp/app.db' \
  portfolio-dashboard`

👉 Open: http://localhost:8000
Default user: admin / admin123
Or register a new user from the login page.

