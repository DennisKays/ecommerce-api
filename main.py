from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
import os
from urllib.parse import urlparse

app = FastAPI(title="E-commerce API")

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection - uses environment variable or falls back to local
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:yourpassword@localhost:5432/postgres")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category TEXT,
        image_url TEXT,
        stock INTEGER DEFAULT 10
    )''')
    
    # Create orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        customer_name TEXT,
        customer_email TEXT,
        total REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Create order items table
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER
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

@app.on_event("startup")
async def startup():
    init_db()

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
