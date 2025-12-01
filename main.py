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
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # Lightweight sentiment replacement
import asyncio  # For async if needed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PropPulse API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Redis
try:
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    r.ping()
    logger.info("✅ Redis connected")
except Exception as e:
    logger.error(f"❌ Redis failed: {e}")
    r = None

# Config
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "86720666e4202df7735a13c083551a40")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
BASE_URL = "https://api.the-odds-api.com/v4"

# Models
class Prop(BaseModel):
    player: str
    prop: str
    line: float
    odds: Dict[str, float]
    adjusted_prob: float
    risk_score: float
    tweets: List[Dict]

# Lazy sentiment analyzer (VADER - tiny & fast)
analyzer = None

def get_sentiment_analyzer():
    global analyzer
    if analyzer is None:
        analyzer = SentimentIntensityAnalyzer()
    return analyzer

def fetch_odds(sport_key: str) -> Optional[List[Dict]]:
    """Fetch odds from API, cache in Redis"""
    cache_key = f"odds:{sport_key}"
    if r and r.exists(cache_key):
        return json.loads(r.get(cache_key))
    try:
        url = f"{BASE_URL}/sports/{sport_key}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "player_points,player_rebounds,player_assists",
            "oddsFormat": "decimal"
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if r:
            r.setex(cache_key, 300, json.dumps(data))  # 5min cache
        return data
    except Exception as e:
        logger.error(f"Fetch odds error: {e}")
        return None

def get_injury_tweets(player: str) -> Dict:
    """Pull X tweets, score sentiment for risk (sync version)"""
    if not X_BEARER_TOKEN:
        return {"risk_score": 0, "tweets": []}
    try:
        headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {
            "query": f'({player} (injury OR practice OR questionable OR load OR rest)) (from:wojespn OR from:ShamsCharania OR from:AdrianDorr OR from:MarcJSpears) -is:retweet',
            "max_results": 5,
            "tweet.fields": "text,created_at"
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        tweets = resp.json().get('data', [])
        sentiments = []
        analyzer = get_sentiment_analyzer()
        for t in tweets:
            score = analyzer.polarity_scores(t['text'])
            # VADER compound is -1 (neg) to +1 (pos); map neg to 0-1 risk
            neg_score = max(0, -score['compound'])  # Inverted for injury risk
            sentiments.append({'text': t['text'][:100], 'score': neg_score})
        risk = sum(s['score'] for s in sentiments) / max(1, len(sentiments))
        return {'risk_score': round(risk * 100, 1), 'tweets': sentiments}
    except Exception as e:
        logger.error(f"Tweet error for {player}: {e}")
        return {"risk_score": 0, "tweets": []}

def detect_prop_arb(props: List[Dict]) -> List[Dict]:
    """Simple arb: Cross-book O/U diffs"""
    arbs = []
    for prop in props:
        odds = prop.get('odds', {})
        over_odds = [o for o in odds.values() if isinstance(o, dict) and 'over' in o]
        under_odds = [o for o in odds.values() if isinstance(o, dict) and 'under' in o]
        if over_odds and under_odds:
            best_over = max([o.get('over', 1) for o in over_odds])
            best_under = max([o.get('under', 1) for o in under_odds])
            if best_over > 1 and best_under > 1 and (1/best_over + 1/best_under) < 0.98:
                margin = round((1 - (1/best_over + 1/best_under)) * 100, 2)
                arbs.append({'prop': prop['player'], 'margin': margin})
    return arbs

@app.get("/")
async def root():
    return {"message": "PropPulse MVP - NBA Props w/ X Edge", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "redis": r is not None}

@app.get("/nba/props", response_model=List[Prop])
async def get_nba_props():
    """Live NBA player props w/ X adjustments"""
    odds_data = fetch_odds("basketball_nba")
    if not odds_data:
        raise HTTPException(500, "Failed to fetch odds")
    props = []
    for event in odds_data[:5]:  # Top 5 games
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if 'player' in market['key'] and len(market['outcomes']) >= 2:
                    player_name = market['outcomes'][0]['name'].split(' - ')[0]  # e.g., "LeBron James"
                    line = float(market['outcomes'][0]['point'])
                    odds = {bookmaker['title']: {o['name'].lower(): o['price'] for o in market['outcomes']}}
                    tweets = get_injury_tweets(player_name)
                    base_prob = 50  # Dummy baseline (replace with historical API later)
                    adjusted = base_prob - tweets['risk_score']
                    props.append(Prop(
                        player=player_name,
                        prop=market['key'],
                        line=line,
                        odds=odds,
                        adjusted_prob=round(adjusted, 1),
                        risk_score=tweets['risk_score'],
                        tweets=tweets['tweets']
                    ))
                    break  # One prop per player for MVP
    # Cache props
    if r:
        r.setex("nba_props", 300, json.dumps([p.dict() for p in props]))
    # Add arbs
    arbs = detect_prop_arb([p.dict() for p in props])
    if arbs:
        logger.info(f"Found {len(arbs)} arb ops")
    return props[:10]  # Limit

@app.get("/ncaab/props", response_model=List[Prop])
async def get_ncaab_props():
    """Live NCAAB player props (similar to NBA)"""
    odds_data = fetch_odds("basketball_ncaab")
    if not odds_data:
        raise HTTPException(500, "Failed to fetch odds")
    props = []
    for event in odds_data[:5]:  # Top 5 games
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if 'player' in market['key'] and len(market['outcomes']) >= 2:
                    player_name = market['outcomes'][0]['name'].split(' - ')[0]
                    line = float(market['outcomes'][0]['point'])
                    odds = {bookmaker['title']: {o['name'].lower(): o['price'] for o in market['outcomes']}}
                    tweets = get_injury_tweets(player_name)
                    base_prob = 50
                    adjusted = base_prob - tweets['risk_score']
                    props.append(Prop(
                        player=player_name,
                        prop=market['key'],
                        line=line,
                        odds=odds,
                        adjusted_prob=round(adjusted, 1),
                        risk_score=tweets['risk_score'],
                        tweets=tweets['tweets']
                    ))
                    break
    if r:
        r.setex("ncaab_props", 300, json.dumps([p.dict() for p in props]))
    return props[:10]

@app.post("/alert")
async def send_alert(data: Dict):
    """Stub Discord alert (call from frontend for VIP)"""
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        raise HTTPException(400, "No webhook")
    try:
        resp = requests.post(webhook, json={"content": f"🚨 {data.get('player', 'Unknown')} {data.get('prop', 'Prop')} @ {data.get('line', 0)} (Risk: {data.get('risk_score', 0):.1f}%)"})
        resp.raise_for_status()
        return {"status": "Alert sent"}
    except Exception as e:
        logger.error(f"Alert error: {e}")
        raise HTTPException(500, "Alert failed")

# Run: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
