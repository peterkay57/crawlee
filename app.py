from fastapi import FastAPI
from pydantic import BaseModel
from uuid import uuid4
import asyncio
import os

app = FastAPI()

# Store results
results_store = {}

class CrawlRequest(BaseModel):
    url: str

@app.get("/")
async def root():
    return {"message": "Crawler API is running", "endpoints": {"/health": "GET", "/crawl": "POST", "/results/{id}": "GET"}}

@app.get("/health")
async def health():
    return {"status": "alive"}

@app.post("/crawl")
async def start_crawl(request: CrawlRequest):
    request_id = str(uuid4())
    results_store[request_id] = {"status": "pending", "url": request.url}
    
    # Start crawler in background
    asyncio.create_task(run_crawler_job(request.url, request_id))
    
    return {"request_id": request_id, "message": "Crawl started"}

async def run_crawler_job(url: str, request_id: str):
    try:
        # This is where the crawling happens
        results = await simple_crawler(url)
        results_store[request_id] = {
            "status": "completed",
            "url": url,
            "results": results,
            "total_pages": len(results)
        }
        print(f"Crawl {request_id} completed")
    except Exception as e:
        results_store[request_id] = {"status": "failed", "error": str(e)}
        print(f"Crawl {request_id} failed: {e}")

async def simple_crawler(target_url: str):
    """Simple crawler that uses requests and BeautifulSoup - no complex dependencies"""
    results = []
    
    try:
        import httpx
        from bs4 import BeautifulSoup
        
        async with httpx.AsyncClient() as client:
            response = await client.get(target_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract data
            title = soup.find('title')
            data = {
                'url': target_url,
                'title': title.get_text() if title else 'No title',
                'status': 'success'
            }
            results.append(data)
            
    except Exception as e:
        results.append({
            'url': target_url,
            'error': str(e),
            'status': 'failed'
        })
    
    return results

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    if request_id in results_store:
        return results_store[request_id]
    return {"status": "not_found", "message": f"No crawl found with ID {request_id}"}

@app.get("/results")
async def list_results():
    return {"total_crawls": len(results_store), "crawls": list(results_store.keys())}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
