```python
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from contextlib import asynccontextmanager
from uuid import uuid4
from crawler import run_crawler
import asyncio

# Store crawl results
crawl_results = {}

class CrawlRequest(BaseModel):
    url: str

class CrawlResponse(BaseModel):
    request_id: str
    status: str
    message: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 FastAPI Crawler starting...")
    yield
    print("👋 FastAPI Crawler shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Web Crawler API",
    description="FastAPI + Crawlee web crawler",
    lifespan=lifespan
)

async def run_background_crawl(url: str, request_id: str):
    """Run crawler in background"""
    try:
        results = await run_crawler(url)
        crawl_results[request_id] = {
            "status": "completed",
            "url": url,
            "results": results,
            "total_pages": len(results)
        }
        print(f"✅ Crawl {request_id} completed with {len(results)} pages")
    except Exception as e:
        crawl_results[request_id] = {
            "status": "failed",
            "error": str(e)
        }
        print(f"❌ Crawl {request_id} failed: {e}")

@app.get("/")
async def root():
    return {
        "service": "FastAPI Web Crawler",
        "version": "1.0.0",
        "endpoints": {
            "/": "This help message",
            "/health": "Health check",
            "/docs": "Interactive API documentation",
            "/crawl": "POST - Start a crawl (send {'url': 'https://example.com'})",
            "/results/{request_id}": "GET - Get crawl results",
            "/results": "GET - List all crawl results"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "alive",
        "service": "crawler",
        "timestamp": str(asyncio.get_event_loop().time())
    }

@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Start a new crawl for the given URL"""
    
    request_id = str(uuid4())
    
    # Store initial status
    crawl_results[request_id] = {
        "status": "pending",
        "url": request.url,
        "started_at": str(asyncio.get_event_loop().time())
    }
    
    # Run crawler in background
    background_tasks.add_task(run_background_crawl, request.url, request_id)
    
    return CrawlResponse(
        request_id=request_id,
        status="started",
        message=f"Crawl started for {request.url}. Check /results/{request_id}"
    )

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    """Get results of a completed crawl"""
    if request_id in crawl_results:
        return crawl_results[request_id]
    return {
        "status": "not_found",
        "message": f"No crawl found with ID {request_id}"
    }

@app.get("/results")
async def list_results():
    """List all crawl results"""
    return {
        "total_crawls": len(crawl_results),
        "crawls": {k: v["status"] for k, v in crawl_results.items()}
    }

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```
  
