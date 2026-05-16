import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        app="scraper.service:app",
        host="0.0.0.0",
        port=int(os.getenv("RAIDMETRICS_SCRAPER_PORT", 8001)),
        reload=os.getenv("RAIDMETRICS_SCRAPER_RELOAD", "false").lower() == "true",
        log_level="info",
    )
