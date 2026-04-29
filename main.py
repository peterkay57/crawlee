from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from contextlib import asynccontextmanager
from uuid import uuid4
from crawler import run_crawler
import asyncio

crawl_results = {}

class CrawlRequest(BaseModel):
    url: str

class CrawlResponse(BaseModel):
    request_id: str
    status: str
    message: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("FastAPI Crawler starting...")
    yield
    print("FastAPI Crawler shutting down...")

app = FastAPI(title="Web Crawler API", lifespan=lifespan)

async def run_background_crawl(url: str, request_id: str):
    try:
        results = await run_crawler(url)
        crawl_results[request_id] = {
            "status": "completed",
            "url": url,
            "results": results,
            "total_pages": len(results)
        }
        print(f"Crawl {request_id} completed")
    except Exception as e:
        crawl_results[request_id] = {"status": "failed", "error": str(e)}
        print(f"Crawl {request_id} failed: {e}")

@app.get("/")
async def root():
    return {"service": "FastAPI Web Crawler", "endpoints": {"/health": "GET", "/crawl": "POST", "/results": "GET"}}

@app.get("/health")
async def health():
    return {"status": "alive"}

@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    request_id = str(uuid4())
    crawl_results[request_id] = {"status": "pending", "url": request.url}
    background_tasks.add_task(run_background_crawl, request.url, request_id)
    return CrawlResponse(request_id=request_id, status="started", message=f"Crawl started for {request.url}")

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    if request_id in crawl_results:
        return crawl_results[request_id]
    return {"status": "not_found"}

@app.get("/results")
async def list_results():
    return {"total_crawls": len(crawl_results), "crawls": {k: v["status"] for k, v in crawl_results.items()}}
