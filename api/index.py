import os
from main import app  # Import your FastAPI app from main.py

# Vercel serverless handler (required for API Gateway)
def handler(request):
    from fastapi.testclient import TestClient
    from fastapi.responses import Response
    client = TestClient(app)
    response = client.request(
        request.method,
        request.path,
        headers=dict(request.headers),
        json=request.json,
        params=request.query_params,
        content=request.body,
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )

# Run uvicorn for local/dev (Vercel ignores this)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
