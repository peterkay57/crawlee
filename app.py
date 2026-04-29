from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from uuid import uuid4
import asyncio
import os
from urllib.parse import urlparse

app = FastAPI()

# Store results
results_store = {}

class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 10
    use_js: bool = True

@app.get("/")
async def root():
    return {"message": "Advanced BBC Crawler - Works with JavaScript"}

@app.get("/health")
async def health():
    return {"status": "alive"}

@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    request_id = str(uuid4())
    results_store[request_id] = {"status": "pending", "url": request.url}
    background_tasks.add_task(run_crawler, request.url, request_id, request.max_pages, request.use_js)
    return {"request_id": request_id, "message": f"Crawl started. Will crawl up to {request.max_pages} pages"}

async def run_crawler(start_url: str, request_id: str, max_pages: int, use_js: bool):
    """Complete working crawler that actually follows links"""
    
    try:
        if use_js:
            # For JavaScript sites like BBC
            from crawlee.crawlers import PlaywrightCrawler
            
            crawled_data = []
            visited_urls = set()
            
            crawler = PlaywrightCrawler(
                max_requests_per_crawl=max_pages,
                headless=True,
            )
            
            @crawler.router.default_handler
            async def handler(context):
                url = context.request.url
                
                if url in visited_urls:
                    return
                    
                visited_urls.add(url)
                
                # Wait for page to load
                await context.page.wait_for_load_state('networkidle')
                
                # Get title
                title = await context.page.title()
                
                # Save data
                crawled_data.append({
                    'url': url,
                    'title': title[:200] if title else 'No title',
                    'status': 'success'
                })
                
                print(f"[{len(crawled_data)}/{max_pages}] Crawled: {url}")
                
                # IMPORTANT: This finds and follows links automatically
                await context.enqueue_links()
            
            # Run the crawler
            await crawler.run([start_url])
            
            # Save results
            results_store[request_id] = {
                "status": "completed",
                "start_url": start_url,
                "total_pages_crawled": len(crawled_data),
                "results": crawled_data,
                "completed_at": str(asyncio.get_event_loop().time())
            }
            print(f"✅ Crawl {request_id} completed! Crawled {len(crawled_data)} pages")
            
        else:
            # For static sites
            import httpx
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            
            crawled_data = []
            visited_urls = set()
            queue = [start_url]
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                while queue and len(crawled_data) < max_pages:
                    current_url = queue.pop(0)
                    
                    if current_url in visited_urls:
                        continue
                    
                    visited_urls.add(current_url)
                    
                    try:
                        response = await client.get(current_url)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        title = soup.find('title')
                        crawled_data.append({
                            'url': current_url,
                            'title': title.get_text() if title else 'No title',
                            'status': 'success'
                        })
                        
                        print(f"[{len(crawled_data)}/{max_pages}] Crawled: {current_url}")
                        
                        # Find and queue links
                        for link in soup.find_all('a', href=True):
                            full_url = urljoin(current_url, link['href'])
                            if urlparse(full_url).netloc == urlparse(start_url).netloc:
                                if full_url not in visited_urls and full_url not in queue:
                                    queue.append(full_url)
                        
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        crawled_data.append({'url': current_url, 'error': str(e), 'status': 'failed'})
            
            results_store[request_id] = {
                "status": "completed",
                "start_url": start_url,
                "total_pages_crawled": len(crawled_data),
                "results": crawled_data,
                "completed_at": str(asyncio.get_event_loop().time())
            }
            print(f"✅ Crawl {request_id} completed! Crawled {len(crawled_data)} pages")
            
    except Exception as e:
        results_store[request_id] = {"status": "failed", "error": str(e)}
        print(f"❌ Crawl {request_id} failed: {e}")

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
