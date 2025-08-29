import os
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Enum, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from passlib.hash import bcrypt
import enum

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)
jwt = JWTManager(app)

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

class TxType(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    investments = relationship("Investment", back_populates="user", cascade="all,delete")
    transactions = relationship("Transaction", back_populates="user", cascade="all,delete")

class Investment(Base):
    __tablename__ = "investments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(32), nullable=False)  # stock, bond, mutual fund, etc.
    symbol = Column(String(32), nullable=True)
    name = Column(String(128), nullable=False)
    current_price = Column(Float, nullable=False, default=0.0)
    user = relationship("User", back_populates="investments")
    transactions = relationship("Transaction", back_populates="investment", cascade="all,delete")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    investment_id = Column(Integer, ForeignKey("investments.id"), nullable=False)
    type = Column(Enum(TxType), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False, default=datetime.utcnow)
    user = relationship("User", back_populates="transactions")
    investment = relationship("Investment", back_populates="transactions")

Base.metadata.create_all(engine)

def seed_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="admin").first():
            u = User(username="admin", password_hash=bcrypt.hash("admin123"))
            db.add(u)
            db.commit()
    finally:
        db.close()
seed_admin()

def compute_investment_metrics(db, inv: Investment, user_id: int):
    buys = db.query(func.coalesce(func.sum(Transaction.quantity), 0.0).label("qty"),
                    func.coalesce(func.sum(Transaction.quantity * Transaction.price), 0.0).label("cost")
                   ).filter(Transaction.user_id == user_id,
                            Transaction.investment_id == inv.id,
                            Transaction.type == TxType.BUY).one()
    sells = db.query(func.coalesce(func.sum(Transaction.quantity), 0.0)).filter(
        Transaction.user_id == user_id,
        Transaction.investment_id == inv.id,
        Transaction.type == TxType.SELL
    ).scalar() or 0.0
    buy_qty = float(buys.qty or 0.0)
    buy_cost = float(buys.cost or 0.0)
    sell_qty = float(sells or 0.0)
    qty = buy_qty - sell_qty
    avg_buy = (buy_cost / buy_qty) if buy_qty > 0 else 0.0
    cost_basis = qty * avg_buy
    current_value = qty * float(inv.current_price or 0.0)
    unrealized_pl = current_value - cost_basis
    pl_pct = (unrealized_pl / cost_basis * 100.0) if cost_basis > 0 else 0.0
    return {
        "id": inv.id,
        "type": inv.type,
        "symbol": inv.symbol,
        "name": inv.name,
        "current_price": inv.current_price,
        "quantity": qty,
        "avg_purchase_price": avg_buy,
        "cost_basis": cost_basis,
        "current_value": current_value,
        "unrealized_pl": unrealized_pl,
        "pl_percent": pl_pct,
    }

def require_json(req, *fields):
    data = req.get_json(silent=True) or {}
    missing = [f for f in fields if f not in data]
    if missing:
        return None, jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    return data, None, None

@app.get("/")
def index():
    return app.send_static_file("index.html")

@app.post("/api/register")
def register():
    data, err_resp, code = require_json(request, "username", "password")
    if err_resp: return err_resp, code
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=data["username"]).first():
            return jsonify({"error": "Username already exists"}), 400
        u = User(username=data["username"], password_hash=bcrypt.hash(data["password"]))
        db.add(u); db.commit()
        return jsonify({"status": "ok"})
    finally:
        db.close()

@app.post("/api/login")
def login():
    data, err_resp, code = require_json(request, "username", "password")
    if err_resp: return err_resp, code
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=data["username"]).first()
        if not u or not bcrypt.verify(data["password"], u.password_hash):
            return jsonify({"error": "Invalid credentials"}), 401
        token = create_access_token(identity=str(u.id), additional_claims={"username": u.username})
        return jsonify({"access_token": token})
    finally:
        db.close()

@app.get("/api/me")
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        return jsonify({"id": u.id, "username": u.username})
    finally:
        db.close()

@app.get("/api/investments")
@jwt_required()
def list_investments():
    user_id = int(get_jwt_identity())
    db = SessionLocal()
    try:
        invs = db.query(Investment).filter_by(user_id=user_id).order_by(Investment.id.desc()).all()
        enriched = [compute_investment_metrics(db, inv, user_id) for inv in invs]
        return jsonify(enriched)
    finally:
        db.close()

@app.post("/api/investments")
@jwt_required()
def create_investment():
    user_id = int(get_jwt_identity())
    data, err_resp, code = require_json(request, "type", "name", "current_price")
    if err_resp: return err_resp, code
    symbol = data.get("symbol")
    inv_type = data["type"]
    name = data["name"]
    current_price = float(data["current_price"])
    db = SessionLocal()
    try:
        inv = Investment(user_id=user_id, type=inv_type, symbol=symbol, name=name, current_price=current_price)
        db.add(inv); db.commit()
        return jsonify({"id": inv.id})
    finally:
        db.close()

@app.put("/api/investments/<int:inv_id>")
@jwt_required()
def update_investment(inv_id):
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        inv = db.query(Investment).filter_by(id=inv_id, user_id=user_id).first()
        if not inv: return jsonify({"error": "Not found"}), 404
        for key in ["type", "symbol", "name", "current_price"]:
            if key in data:
                setattr(inv, key, float(data[key]) if key == "current_price" else data[key])
        db.commit()
        return jsonify({"status": "ok"})
    finally:
        db.close()

@app.delete("/api/investments/<int:inv_id>")
@jwt_required()
def delete_investment(inv_id):
    user_id = int(get_jwt_identity())
    db = SessionLocal()
    try:
        inv = db.query(Investment).filter_by(id=inv_id, user_id=user_id).first()
        if not inv: return jsonify({"error": "Not found"}), 404
        db.delete(inv); db.commit()
        return jsonify({"status": "deleted"})
    finally:
        db.close()

@app.get("/api/transactions")
@jwt_required()
def list_transactions():
    user_id = int(get_jwt_identity())
    inv_id = request.args.get("investment_id", type=int)
    db = SessionLocal()
    try:
        q = db.query(Transaction, Investment.name, Investment.symbol)\
             .join(Investment, Transaction.investment_id == Investment.id)\
             .filter(Transaction.user_id == user_id)
        if inv_id: q = q.filter(Transaction.investment_id == inv_id)
        txs = q.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
        out = []
        for tx, inv_name, inv_symbol in txs:
            out.append({
                "id": tx.id,
                "investment_id": tx.investment_id,
                "investment_name": inv_name,
                "investment_symbol": inv_symbol,
                "type": tx.type.value,
                "quantity": tx.quantity,
                "price": tx.price,
                "date": tx.date.isoformat()
            })
        return jsonify(out)
    finally:
        db.close()

@app.post("/api/transactions")
@jwt_required()
def create_transaction():
    user_id = int(get_jwt_identity())
    data, err_resp, code = require_json(request, "investment_id", "type", "quantity", "price", "date")
    if err_resp: return err_resp, code
    inv_id = int(data["investment_id"])
    tx_type = data["type"]
    qty = float(data["quantity"])
    price = float(data["price"])
    try:
        date_obj = datetime.fromisoformat(data["date"])
    except Exception:
        return jsonify({"error": "Invalid date format, use ISO 8601"}), 400
    if tx_type not in ("BUY", "SELL"):
        return jsonify({"error": "type must be BUY or SELL"}), 400
    db = SessionLocal()
    try:
        inv = db.query(Investment).filter_by(id=inv_id, user_id=user_id).first()
        if not inv: return jsonify({"error": "Investment not found"}), 404
        tx = Transaction(user_id=user_id, investment_id=inv_id, type=TxType[tx_type],
                         quantity=qty, price=price, date=date_obj)
        db.add(tx); db.commit()
        return jsonify({"id": tx.id})
    finally:
        db.close()

@app.get("/api/portfolio/overview")
@jwt_required()
def portfolio_overview():
    user_id = int(get_jwt_identity())
    db = SessionLocal()
    try:
        invs = db.query(Investment).filter_by(user_id=user_id).all()
        per_investment = [compute_investment_metrics(db, inv, user_id) for inv in invs]
        by_type = {}
        totals = {"current_value": 0.0, "cost_basis": 0.0, "unrealized_pl": 0.0}
        for row in per_investment:
            t = row["type"]
            by_type.setdefault(t, {"current_value": 0.0, "cost_basis": 0.0, "unrealized_pl": 0.0})
            by_type[t]["current_value"] += row["current_value"]
            by_type[t]["cost_basis"] += row["cost_basis"]
            by_type[t]["unrealized_pl"] += row["unrealized_pl"]
            totals["current_value"] += row["current_value"]
            totals["cost_basis"] += row["cost_basis"]
            totals["unrealized_pl"] += row["unrealized_pl"]
        for rec in by_type.values():
            rec["pl_percent"] = (rec["unrealized_pl"] / rec["cost_basis"] * 100.0) if rec["cost_basis"] > 0 else 0.0
        totals["pl_percent"] = (totals["unrealized_pl"] / totals["cost_basis"] * 100.0) if totals["cost_basis"] > 0 else 0.0
        return jsonify({"by_investment": per_investment, "by_type": by_type, "totals": totals})
    finally:
        db.close()

@app.get("/<path:p>")
def static_proxy(p):
    if os.path.exists(os.path.join(app.static_folder, p)):
        return send_from_directory(app.static_folder, p)
    return app.send_static_file("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
