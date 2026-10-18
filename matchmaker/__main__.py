"""Run with: python -m matchmaker"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "matchmaker.app:app",
        host=os.getenv("MATCHMAKER_HOST", "127.0.0.1"),
        port=int(os.getenv("MATCHMAKER_PORT", "8000")),
        reload=os.getenv("MATCHMAKER_RELOAD", "false").lower() == "true",
    )
