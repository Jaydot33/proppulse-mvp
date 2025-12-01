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
from transformers import pipeline
from dotenv import load_dotenv
import traceback
from mangum import Mangum  # Vercel handler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("DEBUG: PropPulse API starting (Vercel cold start check)")

# Env validation (crash preventer)
required_vars = ['ODDS_API_KEY', 'X_BEARER_TOKEN']
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print(f"ERROR: Missing env vars: {missing} - Set in Vercel dashboard!")
    raise ValueError(f"Missing env vars: {missing}")

app = FastAPI(title="PropPulse API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Redis
try:
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    r.ping()
    print("DEBUG: Redis OK")
except Exception as e:
    print(f"WARN: Redis fallback: {e}")
    r = None

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
BASE_URL = "https://api.the-odds-api.com/v4"

class Prop(BaseModel):
    player: str
    prop: str
    line: float
    odds: Dict[str, float]
    adjusted_prob: float
    risk_score: float
    tweets: List[Dict]

sentiment_pipeline = None
def get_sentiment_pipeline():
    global sentiment_pipeline
    if sentiment_pipeline is None:
        try:
            sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
            print("DEBUG: ML pipeline loaded (2-5s cold)")
        except Exception as e:
            print(f"ERROR: ML fallback (using dummy sentiment): {e}")
            sentiment_pipeline = lambda text: [{'label': 'NEUTRAL', 'score': 0.5}]  # No-crash dummy
    return sentiment_pipeline

def fetch_odds(sport_key: str) -> Optional[List[Dict]]:
    cache_key = f"odds:{sport_key}"
    if r and r.exists(cache_key):
        return json.loads(r.get(cache_key))
    try:
        url = f"{BASE_URL}/sports/{sport_key}/odds/"
        params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "player_points,player_rebounds,player_assists", "oddsFormat": "decimal"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if r: r.setex(cache_key, 300, json.dumps(data))
        return data
    except Exception as e:
        print(f"ERROR: Odds fetch: {e}")
        return None

def get_injury_tweets(player: str) -> Dict:
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
        pipeline = get_sentiment_pipeline()
        sentiments = []
        for t in tweets:
            score = pipeline(t['text'])[0]
            neg_score = score['score'] if score['label'] == 'NEGATIVE' else 0
            sentiments.append({'text': t['text'][:100], 'score': neg_score})
        risk = sum(s['score'] for s in sentiments) / max(1, len(sentiments))
        return {'risk_score': round(risk * 100, 1), 'tweets': sentiments}
    except Exception as e:
        print(f"ERROR: Tweets for {player}: {e}")
        return {"risk_score": 0, "tweets": []}

def detect_prop_arb(props: List[Dict]) -> List[Dict]:
    arbs = []
    for prop in props:
        odds = prop.get('odds', {})
        over_odds = [o_types.get('over', 1) for o_types in odds.values() if isinstance(o_types, dict)]
        under_odds = [o_types.get('under', 1) for o_types in odds.values() if isinstance(o_types, dict)]
        if over_odds and under_odds:
            best_over = max(over_odds)
            best_under = max(under_odds)
            vig = 1/best_over + 1/best_under
            if vig < 0.98:
                margin = round((1 - vig) * 100, 2)
                arbs.append({'prop': prop['player'], 'margin': margin, 'vig': round(vig * 100, 1)})
    return sorted(arbs, key=lambda x: x['margin'], reverse=True)[:3]

@app.get("/")
async def root():
    print("DEBUG: Root hit")
    return {"message": "PropPulse MVP Live!", "version": "1.0.0"}

@app.get("/health")
async def health():
    print("DEBUG: Health check")
    return {
        "status": "healthy",
        "redis": r is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/nba/props", response_model=List[Prop])
async def get_nba_props():
    print("DEBUG: NBA props request")
    odds_data = fetch_odds("basketball_nba")
    if not odds_data:
        raise HTTPException(500, "Odds fetch failed")
    props = []
    seen_players = set()
    for event in odds_data[:5]:
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if 'player' in market['key'] and len(market['outcomes']) >= 2:
                    player_name = market['outcomes'][0]['name'].split(' - ')[0]
                    if player_name in seen_players: continue
                    seen_players.add(player_name)
                    line = float(market['outcomes'][0]['point'])
                    odds = {bookmaker['title']: {o['name'].lower(): o['price'] for o in market['outcomes']}}
                    tweets = get_injury_tweets(player_name)
                    base_prob = 50
                    adjusted = max(0, base_prob - tweets['risk_score'])
                    props.append(Prop(
                        player=player_name, prop=market['key'], line=line, odds=odds,
                        adjusted_prob=round(adjusted, 1), risk_score=tweets['risk_score'], tweets=tweets['tweets']
                    ))
    if r: r.setex("nba_props", 300, json.dumps([p.dict() for p in props]))
    return props[:10]

# Similar for /ncaab/props (copy from previous)
@app.get("/ncaab/props", response_model=List[Prop])
async def get_ncaab_props():
    print("DEBUG: NCAAB props request")
    odds_data = fetch_odds("basketball_ncaab")
    if not odds_data:
        raise HTTPException(500, "Odds fetch failed")
    # ... (mirror NBA logic, replace sport_key)
    props = []  # Implement as above
    return props[:10]

@app.post("/alert")
async def send_alert(data: Dict):
    print("DEBUG: Alert post")
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        raise HTTPException(400, "No webhook")
    try:
        resp = requests.post(webhook, json={"content": f"Alert: {data.get('player')} {data.get('prop')} @ {data.get('line')} (Risk: {data.get('risk_score'):.1f}%)"})
        resp.raise_for_status()
        return {"status": "Sent"}
    except Exception as e:
        print(f"ERROR: Alert: {e}")
        raise HTTPException(500, "Alert failed")

# Vercel handler
handler = Mangum(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
