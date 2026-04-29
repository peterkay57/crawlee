from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from uuid import uuid4
import asyncio
import os
import random
from urllib.parse import urljoin, urlparse
from datetime import datetime

app = FastAPI()

# Store results
results_store = {}

class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 100
    use_js: bool = False  # Set True for JavaScript sites like BBC

# Advanced crawler with real browser support
async def advanced_crawler(start_url: str, request_id: str, max_pages: int = 100, use_js: bool = False):
    """ADVANCED crawler with JavaScript support, retries, and human-like behavior"""
    
    try:
        crawled_data = []
        visited_urls = set()
        queue = [start_url]
        
        # User agents to rotate (avoid detection)
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0'
        ]
        
        if use_js:
            # For JavaScript-heavy sites like BBC
            from crawlee.crawlers import PlaywrightCrawler
            
            crawler = PlaywrightCrawler(
                max_requests_per_crawl=max_pages,
                headless=True,
            )
            
            @crawler.router.default_handler
            async def handler(context):
                url = context.request.url
                if url not in visited_urls:
                    visited_urls.add(url)
                    await context.page.wait_for_load_state('networkidle')
                    title = await context.page.title()
                    crawled_data.append({'url': url, 'title': title, 'method': 'js'})
                    await context.enqueue_links()
            
            await crawler.run([start_url])
            
        else:
            # For static sites (faster)
            import httpx
            from bs4 import BeautifulSoup
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                while queue and len(crawled_data) < max_pages:
                    current_url = queue.pop(0)
                    
                    if current_url in visited_urls:
                        continue
                    
                    visited_urls.add(current_url)
                    
                    # Random delay (1-3 seconds) - look human
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    # Rotate user agent
                    headers = {'User-Agent': random.choice(user_agents)}
                    
                    # Retry logic (3 attempts)
                    for attempt in range(3):
                        try:
                            response = await client.get(current_url, headers=headers)
                            soup = BeautifulSoup(response.text, 'html.parser')
                            
                            title = soup.find('title')
                            page_data = {
                                'url': current_url,
                                'title': title.get_text() if title else 'No title',
                                'status': 'success',
                                'method': 'static'
                            }
                            crawled_data.append(page_data)
                            
                            # Extract ALL links
                            for link in soup.find_all('a', href=True):
                                full_url = urljoin(current_url, link['href'])
                                if urlparse(full_url).netloc == urlparse(start_url).netloc:
                                    if full_url not in visited_urls and full_url not in queue:
                                        queue.append(full_url)
                            
                            print(f"[{len(crawled_data)}/{max_pages}] Crawled: {current_url} | Queue: {len(queue)}")
                            break  # Success, exit retry loop
                            
                        except Exception as e:
                            if attempt == 2:  # Last attempt failed
                                crawled_data.append({'url': current_url, 'error': str(e), 'status': 'failed'})
                                print(f"Failed after 3 attempts: {current_url}")
                            else:
                                await asyncio.sleep(2)  # Wait before retry
        
        results_store[request_id] = {
            "status": "completed",
            "start_url": start_url,
            "total_pages_crawled": len(crawled_data),
            "unique_urls_visited": len(visited_urls),
            "results": crawled_data[:100],  # Return first 100 results
            "completed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        results_store[request_id] = {"status": "failed", "error": str(e)}

# FastAPI endpoints
app = FastAPI(title="Advanced Crawler API")

@app.get("/")
async def root():
    return {"message": "ADVANCED Crawler - Supports JavaScript, retries, rate limiting"}

@app.get("/health")
async def health():
    return {"status": "alive"}

@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    request_id = str(uuid4())
    results_store[request_id] = {"status": "pending", "url": request.url}
    background_tasks.add_task(advanced_crawler, request.url, request_id, request.max_pages, request.use_js)
    return {"request_id": request_id, "message": f"Advanced crawl started. Will crawl up to {request.max_pages} pages"}

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    return results_store.get(request_id, {"status": "not_found"})

@app.get("/results")
async def list_results():
    return {"total_crawls": len(results_store), "crawls": list(results_store.keys())}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
