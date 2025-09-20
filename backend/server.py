from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
import bcrypt
import os
import uuid
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'futura-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Create the main app and router
app = FastAPI(title="FUTURA Budget Tracker API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Models
class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    currency: str = "₹"
    monthly_budget: float = 10000.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TransactionCreate(BaseModel):
    type: str  # "income" or "expense"
    amount: float
    category: str
    description: str
    payment_type: str = "Cash"  # Cash, Card, UPI
    tags: List[str] = []
    date: Optional[datetime] = None
    
    @validator('type')
    def validate_type(cls, v):
        if v not in ['income', 'expense']:
            raise ValueError('Type must be income or expense')
        return v
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: str
    amount: float
    category: str
    description: str
    payment_type: str = "Cash"
    tags: List[str] = []
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deleted: bool = False
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class BudgetCreate(BaseModel):
    category: str
    limit: float
    period: str = "monthly"  # daily, weekly, monthly

class Budget(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    category: str
    limit: float
    period: str = "monthly"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class DashboardData(BaseModel):
    total_income: float
    total_expenses: float
    balance: float
    budget_used_percent: float
    recent_transactions: List[Transaction]
    category_breakdown: Dict[str, float]
    monthly_trend: List[Dict[str, Any]]

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise credentials_exception
    return User(**user)

def prepare_for_mongo(data):
    """Convert datetime objects to ISO strings for MongoDB storage"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
    return data

def parse_from_mongo(item):
    """Parse datetime strings back from MongoDB"""
    if isinstance(item, dict):
        for key, value in item.items():
            if key in ['date', 'created_at'] and isinstance(value, str):
                try:
                    item[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except:
                    pass
    return item

# Auth endpoints
@api_router.post("/auth/register")
async def register(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        name=user_data.name,
        email=user_data.email
    )
    
    user_dict = user.dict()
    user_dict["password_hash"] = hashed_password
    user_dict = prepare_for_mongo(user_dict)
    
    await db.users.insert_one(user_dict)
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@api_router.post("/auth/login")
async def login(user_data: UserLogin):
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": user["id"]})
    user_obj = User(**user)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_obj
    }

# User endpoints
@api_router.get("/user/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user

@api_router.put("/user/settings", response_model=User)
async def update_user_settings(
    settings: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": settings}
    )
    
    updated_user = await db.users.find_one({"id": current_user.id})
    return User(**updated_user)

# Transaction endpoints
@api_router.post("/transactions", response_model=Transaction)
async def create_transaction(
    transaction_data: TransactionCreate,
    current_user: User = Depends(get_current_user)
):
    transaction_dict = transaction_data.dict()
    if transaction_dict.get('date') is None:
        transaction_dict['date'] = datetime.now(timezone.utc)
    
    transaction = Transaction(
        user_id=current_user.id,
        **transaction_dict
    )
    
    transaction_dict = prepare_for_mongo(transaction.dict())
    await db.transactions.insert_one(transaction_dict)
    
    return transaction

@api_router.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    limit: int = 100,
    offset: int = 0,
    category: Optional[str] = None,
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    query = {"user_id": current_user.id, "deleted": False}
    
    if category:
        query["category"] = category
    if type:
        query["type"] = type
    
    transactions = await db.transactions.find(query).sort("date", -1).skip(offset).limit(limit).to_list(length=None)
    
    return [Transaction(**parse_from_mongo(t)) for t in transactions]

@api_router.put("/transactions/{transaction_id}", response_model=Transaction)
async def update_transaction(
    transaction_id: str,
    transaction_data: TransactionCreate,
    current_user: User = Depends(get_current_user)
):
    result = await db.transactions.update_one(
        {"id": transaction_id, "user_id": current_user.id},
        {"$set": prepare_for_mongo(transaction_data.dict())}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    updated_transaction = await db.transactions.find_one({"id": transaction_id})
    return Transaction(**parse_from_mongo(updated_transaction))

@api_router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.transactions.update_one(
        {"id": transaction_id, "user_id": current_user.id},
        {"$set": {"deleted": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {"message": "Transaction deleted successfully"}

# Dashboard endpoint
@api_router.get("/dashboard", response_model=DashboardData)
async def get_dashboard_data(
    period: str = "monthly",
    current_user: User = Depends(get_current_user)
):
    # Calculate date range
    now = datetime.now(timezone.utc)
    if period == "monthly":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = now - timedelta(days=7)
    else:
        start_date = now - timedelta(days=30)
    
    # Get transactions for the period
    transactions = await db.transactions.find({
        "user_id": current_user.id,
        "deleted": False,
        "date": {"$gte": start_date.isoformat()}
    }).sort("date", -1).to_list(length=None)
    
    transactions = [Transaction(**parse_from_mongo(t)) for t in transactions]
    
    # Calculate totals
    total_income = sum(t.amount for t in transactions if t.type == "income")
    total_expenses = sum(t.amount for t in transactions if t.type == "expense")
    balance = total_income - total_expenses
    
    # Budget calculation
    budget_used_percent = min((total_expenses / current_user.monthly_budget) * 100, 100) if current_user.monthly_budget > 0 else 0
    
    # Category breakdown
    category_breakdown = {}
    for t in transactions:
        if t.type == "expense":
            category_breakdown[t.category] = category_breakdown.get(t.category, 0) + t.amount
    
    # Monthly trend (last 7 days)
    monthly_trend = []
    for i in range(7):
        day = now - timedelta(days=i)
        day_transactions = [t for t in transactions if t.date.date() == day.date()]
        daily_expenses = sum(t.amount for t in day_transactions if t.type == "expense")
        monthly_trend.append({
            "date": day.strftime("%Y-%m-%d"),
            "amount": daily_expenses
        })
    
    return DashboardData(
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        budget_used_percent=budget_used_percent,
        recent_transactions=transactions[:10],
        category_breakdown=category_breakdown,
        monthly_trend=list(reversed(monthly_trend))
    )

# Budget endpoints
@api_router.post("/budgets", response_model=Budget)
async def create_budget(
    budget_data: BudgetCreate,
    current_user: User = Depends(get_current_user)
):
    budget = Budget(
        user_id=current_user.id,
        **budget_data.dict()
    )
    
    budget_dict = prepare_for_mongo(budget.dict())
    await db.budgets.insert_one(budget_dict)
    
    return budget

@api_router.get("/budgets", response_model=List[Budget])
async def get_budgets(current_user: User = Depends(get_current_user)):
    budgets = await db.budgets.find({"user_id": current_user.id}).to_list(length=None)
    return [Budget(**parse_from_mongo(b)) for b in budgets]

# Insights endpoint (rule-based AI tips)
@api_router.get("/insights")
async def get_insights(current_user: User = Depends(get_current_user)):
    # Get last 30 days transactions
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=30)
    
    transactions = await db.transactions.find({
        "user_id": current_user.id,
        "deleted": False,
        "date": {"$gte": start_date.isoformat()}
    }).to_list(length=None)
    
    transactions = [Transaction(**parse_from_mongo(t)) for t in transactions]
    expenses = [t for t in transactions if t.type == "expense"]
    
    if not expenses:
        return {
            "tips": ["Start tracking your expenses to get personalized insights!"],
            "projection": {"balance": 0, "message": "No data available"}
        }
    
    total_expenses = sum(t.amount for t in expenses)
    
    # Category analysis
    category_totals = {}
    for t in expenses:
        category_totals[t.category] = category_totals.get(t.category, 0) + t.amount
    
    tips = []
    
    # Tip 1: Top spending category
    if category_totals:
        top_category = max(category_totals, key=category_totals.get)
        top_amount = category_totals[top_category]
        percentage = (top_amount / total_expenses) * 100
        if percentage > 30:
            tips.append(f"You spent {percentage:.0f}% on {top_category}. Consider setting a monthly limit to track this category better.")
    
    # Tip 2: Frequent small expenses
    small_expenses = [t for t in expenses if t.amount < 100]
    if len(small_expenses) > 10:
        small_total = sum(t.amount for t in small_expenses)
        tips.append(f"You made {len(small_expenses)} small purchases totaling ₹{small_total:.0f}. These add up quickly!")
    
    # Tip 3: Budget comparison
    if total_expenses > current_user.monthly_budget:
        overspend = total_expenses - current_user.monthly_budget
        tips.append(f"You're ₹{overspend:.0f} over budget this month. Try to reduce discretionary spending.")
    else:
        savings = current_user.monthly_budget - total_expenses
        tips.append(f"Great job! You're ₹{savings:.0f} under budget. Consider saving this amount.")
    
    # Projection for month-end
    days_in_month = (now.replace(month=now.month+1, day=1) - timedelta(days=1)).day
    days_passed = now.day
    avg_daily_spend = total_expenses / days_passed if days_passed > 0 else 0
    projected_monthly_spend = avg_daily_spend * days_in_month
    projected_balance = current_user.monthly_budget - projected_monthly_spend
    
    projection = {
        "projected_spend": projected_monthly_spend,
        "projected_balance": projected_balance,
        "message": f"At your current rate, you'll spend ₹{projected_monthly_spend:.0f} this month."
    }
    
    return {
        "tips": tips[:3],  # Limit to 3 tips
        "projection": projection
    }

# Include router
app.include_router(api_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()