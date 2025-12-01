import os
import json
import redis
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from transformers import pipeline  # For sentiment
from dotenv import load_dotenv
import traceback  # NEW: For error logging

load_dotenv()  # Load env vars

# Configure logging (Vercel captures stdout)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("DEBUG: main.py loaded - FastAPI starting")  # Cold start marker

app = FastAPI(title="PropPulse API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis (with fallback)
try:
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    r.ping()
    print("DEBUG: Redis connected")
    logger.info("Redis connected")
except Exception as e:
    print(f"DEBUG: Redis failed (fallback to no-cache): {e}")
    logger.error(f"Redis failed: {e}")
    r = None

# Config
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
if not ODDS_API_KEY:
    print("WARN: ODDS_API_KEY missing - odds fetch will fail")
BASE_URL = "https://api.the-odds-api.com/v4"

# Models (unchanged)
class Prop(BaseModel):
    player: str
    prop: str
    line: float
    odds: Dict[str, float]
    adjusted_prob: float
    risk_score: float
    tweets: List[Dict]

# Lazy sentiment (with error wrap)
sentiment_pipeline = None
def get_sentiment_pipeline():
    global sentiment_pipeline
    if sentiment_pipeline is None:
        try:
            sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
            print("DEBUG: Sentiment pipeline loaded")
        except Exception as e:
            print(f"ERROR: Pipeline load failed: {e}")
            logger.error(f"Pipeline error: {traceback.format_exc()}")
            sentiment_pipeline = None  # Fallback to dummy
    return sentiment_pipeline

# Rest of functions unchanged (fetch_odds, get_injury_tweets, detect_prop_arb, endpoints)
# ... [Paste your existing fetch_odds, get_injury_tweets, detect_prop_arb, @app.get("/") , /health, /nba/props, /ncaab/props, /alert]

# NEW: Vercel serverless handler (Mangum for ASGI)
from mangum import Mangum
handler = Mangum(app)

# Run locally
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
