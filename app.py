import sqlite3
import requests
import re
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI(title="Laptop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReviewModel(BaseModel):
    laptop_id: int
    user_name: str
    rating: int
    comment: str

class ChatMessage(BaseModel):
    message: str

def init_db():
    conn = sqlite3.connect("laptops.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS laptops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            ssd TEXT DEFAULT '512 GB NVMe SSD',
            hz TEXT DEFAULT '144 Hz',
            panel TEXT DEFAULT 'IPS Panel',
            battery TEXT DEFAULT '6-8 Saat Pil Ömrü'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id INTEGER,
            user_name TEXT,
            rating INTEGER,
            comment TEXT
        )
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM laptops")
    if cursor.fetchone()[0] == 0:
        url = "https://books.toscrape.com/"
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for card in soup.find_all("article", class_="product_pod"):
                title = card.h3.a["title"]
                price = card.find("p", class_="price_color").text.strip()
                cursor.execute(
                    "INSERT INTO laptops (title, price, ssd, hz, panel, battery) VALUES (?, ?, ?, ?, ?, ?)",
                    (title, price, "512 GB NVMe SSD", "144 Hz", "IPS Panel", "6-8 Saat Pil Ömrü")
                )
            conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def home():
    return {"status": "Basarili", "message": "API Calisiyor!"}

@app.get("/api/laptops")
def get_laptops(search: str = Query(None)):
    conn = sqlite3.connect("laptops.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if search:
        products = cursor.execute("SELECT * FROM laptops WHERE title LIKE ?", (f"%{search}%",)).fetchall()
    else:
        products = cursor.execute("SELECT * FROM laptops").fetchall()
        
    result = []
    for p in products:
        item = dict(p)
        
        reviews = cursor.execute("SELECT rating FROM reviews WHERE laptop_id = ?", (item['id'],)).fetchall()
        if reviews:
            item['avg_rating'] = round(sum(r['rating'] for r in reviews) / len(reviews), 1)
            item['review_count'] = len(reviews)
        else:
            item['avg_rating'] = 0
            item['review_count'] = 0

        try:
            clean_price_str = re.sub(r'[^\d.]', '', item['price'])
            base_price = float(clean_price_str) if clean_price_str else 20.0
        except Exception:
            base_price = 20.0

        item['stores'] = [
            {"name": "Trendyol", "price": f"₺{round(base_price * 1000, 2)}", "val": base_price * 1000, "url": "https://www.trendyol.com"},
            {"name": "Hepsiburada", "price": f"₺{round(base_price * 1050, 2)}", "val": base_price * 1050, "url": "https://www.hepsiburada.com"},
            {"name": "Amazon TR", "price": f"₺{round(base_price * 980, 2)}", "val": base_price * 980, "url": "https://www.amazon.com.tr"}
        ]
        
        cheapest = min(item['stores'], key=lambda x: x['val'])
        item['cheapest_store'] = cheapest['name']
        item['cheapest_price'] = cheapest['price']

        result.append(item)

    conn.close()
    return result

# SOHBET BOTU ÖNERİ ENDPOINT'İ
@app.post("/api/recommend")
def recommend_laptop(data: ChatMessage):
    msg = data.message.lower()
    conn = sqlite3.connect("laptops.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    all_products = cursor.execute("SELECT * FROM laptops").fetchall()
    conn.close()
    
    products = [dict(p) for p in all_products]
    filtered = []
    reply_text = ""

    if any(word in msg for word in ["oyun", "gaming", "fps", "grafik", "ekran kartı"]):
        filtered = [p for p in products if any(k in p['title'].lower() for k in ["rtx", "gtx", "i7", "ryzen 7"])]
        reply_text = "🤖 Oyun ve yüksek grafik performansı için şu güçlü cihazları önerebilirim:"
    elif any(word in msg for word in ["yazılım", "kodlama", "programlama", "developer"]):
        filtered = [p for p in products if any(k in p['title'].lower() for k in ["16gb", "32gb", "i7"])]
        reply_text = "🤖 Yazılım geliştirme ve rahat çoklu görev (Multitask) için şu bilgisayarlar biçilmiş kaftan:"
    elif any(word in msg for word in ["ofis", "iş", "excel", "word", "şarj", "pil"]):
        filtered = [p for p in products if any(k in p['title'].lower() for k in ["i5", "ryzen 5", "16gb"])]
        reply_text = "🤖 Ofis çalışmaları, belge yönetimi ve taşınabilir kullanım için en dengeli önerilerim:"
    else:
        filtered = products[:3]
        reply_text = "🤖 Aradığınız kriterlere uygun sistemimizdeki öne çıkan en popüler 3 cihaz:"

    top3 = filtered[:3] if filtered else products[:3]
    return {"reply": reply_text, "laptops": top3}

@app.get("/api/reviews/{laptop_id}")
def get_reviews(laptop_id: int):
    conn = sqlite3.connect("laptops.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    reviews = cursor.execute("SELECT * FROM reviews WHERE laptop_id = ? ORDER BY id DESC", (laptop_id,)).fetchall()
    conn.close()
    return [dict(r) for r in reviews]

@app.post("/api/reviews")
def add_review(review: ReviewModel):
    conn = sqlite3.connect("laptops.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (laptop_id, user_name, rating, comment) VALUES (?, ?, ?, ?)",
        (review.laptop_id, review.user_name, review.rating, review.comment)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Yorum eklendi"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)