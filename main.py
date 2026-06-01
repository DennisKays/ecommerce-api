from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
import os
import requests
import uuid
from passlib.context import CryptContext

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:yourpassword@localhost:5432/postgres")

# Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gecyngirlsbevbnsafch.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category TEXT,
        image_url TEXT,
        stock INTEGER DEFAULT 10
    )''')
    
    # Orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        customer_name TEXT,
        customer_email TEXT,
        total REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Order items table
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER
    )''')
    
    # Users table - DROP AND RECREATE to ensure it exists
    c.execute('''DROP TABLE IF EXISTS users CASCADE''')
    c.execute('''CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Subscriptions table - DROP AND RECREATE
    c.execute('''DROP TABLE IF EXISTS subscriptions CASCADE''')
    c.execute('''CREATE TABLE subscriptions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        plan TEXT NOT NULL,
        status TEXT DEFAULT 'inactive',
        starts_at TIMESTAMP,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Payments table - DROP AND RECREATE
    c.execute('''DROP TABLE IF EXISTS payments CASCADE''')
    c.execute('''CREATE TABLE payments (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        method TEXT,
        reference_code TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'pending',
        verified_at TIMESTAMP,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Seed sample data if empty
    c.execute("SELECT COUNT(*) FROM products")
    count = c.fetchone()[0]
    
    if count == 0:
        sample_products = [
            ("Wireless Headphones", "Premium noise-cancelling headphones", 89.99, "Electronics", "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400", 15),
            ("Running Shoes", "Lightweight breathable running shoes", 129.99, "Sports", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400", 20),
            ("Coffee Maker", "Automatic drip coffee maker", 59.99, "Home", "https://images.unsplash.com/photo-1517668808822-9ebb02f2a0e6?w=400", 8),
            ("Laptop Stand", "Adjustable aluminum laptop stand", 45.99, "Electronics", "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400", 25),
            ("Yoga Mat", "Non-slip exercise yoga mat", 29.99, "Sports", "https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?w=400", 30),
            ("Desk Lamp", "LED desk lamp with wireless charging", 39.99, "Home", "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=400", 12),
        ]
        c.executemany("INSERT INTO products (name, description, price, category, image_url, stock) VALUES (%s, %s, %s, %s, %s, %s)", sample_products)
        conn.commit()
    
    conn.close()

app = FastAPI(title="E-commerce API")

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on first request
@app.get("/init")
def force_init():
    try:
        init_db()
        return {"message": "Database initialized successfully"}
    except Exception as e:
        return {"error": str(e)}

class Product(BaseModel):
    id: Optional[int] = None
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int = 10

class OrderItem(BaseModel):
    product_id: int
    quantity: int

class Order(BaseModel):
    customer_name: str
    customer_email: str
    items: List[OrderItem]
    total: float

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class PaymentCreate(BaseModel):
    user_id: int
    amount: float
    method: str
    reference_code: str

def upload_to_supabase(file: UploadFile):
    """Upload file to Supabase Storage and return public URL"""
    if not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase key not configured")
    
    file_extension = file.filename.split('.')[-1]
    file_name = f"{uuid.uuid4()}.{file_extension}"
    
    file_content = file.file.read()
    
    upload_url = f"{SUPABASE_URL}/storage/v1/object/product-images/{file_name}"
    
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": file.content_type or "application/octet-stream"
    }
    
    response = requests.post(upload_url, headers=headers, data=file_content)
    
    if response.status_code not in [200, 201]:
        raise HTTPException(status_code=500, detail=f"Upload failed: {response.text}")
    
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/product-images/{file_name}"
    return public_url

@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload image and return URL"""
    try:
        image_url = upload_to_supabase(file)
        return {"image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products")
def get_products(category: Optional[str] = None):
    conn = get_db_connection()
    c = conn.cursor()
    
    if category:
        c.execute("SELECT * FROM products WHERE category = %s", (category,))
    else:
        c.execute("SELECT * FROM products")
    
    columns = [desc[0] for desc in c.description]
    products = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return products

@app.get("/products/{product_id}")
def get_product(product_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    columns = [desc[0] for desc in c.description]
    return dict(zip(columns, row))

@app.get("/categories")
def get_categories():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return categories

@app.post("/products")
def create_product(product: Product):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, description, price, category, image_url, stock) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
              (product.name, product.description, product.price, product.category, product.image_url, product.stock))
    product_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": product_id, **product.dict()}

@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    conn.close()
    return {"message": "Product deleted"}

@app.post("/orders")
def create_order(order: Order):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("INSERT INTO orders (customer_name, customer_email, total) VALUES (%s, %s, %s) RETURNING id",
              (order.customer_name, order.customer_email, order.total))
    order_id = c.fetchone()[0]
    
    for item in order.items:
        c.execute("INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                  (order_id, item.product_id, item.quantity))
    
    conn.commit()
    conn.close()
    return {"message": "Order placed successfully", "order_id": order_id}

@app.get("/orders")
def get_orders():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY created_at DESC")
    columns = [desc[0] for desc in c.description]
    orders = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return orders

# AUTH ENDPOINTS
@app.post("/auth/register")
def register_user(user: UserCreate):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE email = %s", (user.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Truncate password to 72 bytes for bcrypt compatibility
    password_bytes = user.password.encode('utf-8')[:72]
    password_hash = pwd_context.hash(password_bytes)
    
    c.execute("INSERT INTO users (email, password_hash, full_name, phone) VALUES (%s, %s, %s, %s) RETURNING id",
              (user.email, password_hash, user.full_name, user.phone))
    user_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    return {"message": "User registered", "user_id": user_id}

@app.post("/auth/login")
def login_user(credentials: UserLogin):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, password_hash FROM users WHERE email = %s", (credentials.email,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Truncate password to 72 bytes for bcrypt compatibility
    password_bytes = credentials.password.encode('utf-8')[:72]
    if not pwd_context.verify(password_bytes, row[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {"message": "Login successful", "user_id": row[0]}

@app.get("/auth/user/{user_id}")
def get_user(user_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, email, full_name, phone, created_at FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    columns = [desc[0] for desc in c.description]
    return dict(zip(columns, row))

# SUBSCRIPTION ENDPOINTS
@app.post("/subscriptions/create")
def create_subscription(user_id: int, plan: str):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM subscriptions WHERE user_id = %s AND status = 'active'", (user_id,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="User already has active subscription")
    
    c.execute("INSERT INTO subscriptions (user_id, plan, status) VALUES (%s, %s, %s) RETURNING id",
              (user_id, plan, 'inactive'))
    sub_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    return {"message": "Subscription created", "subscription_id": sub_id}

@app.get("/subscriptions/user/{user_id}")
def get_user_subscription(user_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return {"status": "no_subscription"}
    
    columns = [desc[0] for desc in c.description]
    return dict(zip(columns, row))

# PAYMENT ENDPOINTS
@app.post("/payments/create")
def create_payment(payment: PaymentCreate):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("INSERT INTO payments (user_id, amount, method, reference_code) VALUES (%s, %s, %s, %s) RETURNING id",
              (payment.user_id, payment.amount, payment.method, payment.reference_code))
    payment_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    return {"message": "Payment recorded", "payment_id": payment_id}

@app.post("/payments/verify")
def verify_payment(reference_code: str, notes: Optional[str] = None):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, user_id FROM payments WHERE reference_code = %s", (reference_code,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment_id, user_id = row
    
    c.execute("UPDATE payments SET status = 'verified', verified_at = CURRENT_TIMESTAMP, notes = %s WHERE id = %s",
              (notes, payment_id))
    
    c.execute("UPDATE subscriptions SET status = 'active', starts_at = CURRENT_TIMESTAMP, expires_at = CURRENT_TIMESTAMP + INTERVAL '30 days' WHERE user_id = %s",
              (user_id,))
    
    conn.commit()
    conn.close()
    
    return {"message": "Payment verified and subscription activated"}

@app.get("/payments/pending")
def get_pending_payments():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT p.*, u.email, u.full_name FROM payments p JOIN users u ON p.user_id = u.id WHERE p.status = 'pending' ORDER BY p.created_at DESC")
    columns = [desc[0] for desc in c.description]
    payments = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return payments

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
