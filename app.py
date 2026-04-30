from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4
import asyncio
import os
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse, urljoin
from datetime import datetime
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Advanced Web Crawler v3.0")

# Store results
results_store: Dict[str, Dict[str, Any]] = {}

class CrawlRequest(BaseModel):
    url: str = Field(..., description="Starting URL")
    max_pages: int = Field(default=10, ge=1, le=50)
    use_js: bool = Field(default=True)
    same_domain_only: bool = Field(default=True)
    delay_seconds: float = Field(default=1.0, ge=0.5, le=3.0)

@app.get("/")
async def root():
    return {"message": "🚀 Advanced Web Crawler v3.0 - Fixed Version"}

@app.get("/health")
async def health():
    return {"status": "alive", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Start crawl job"""
    
    # Validate URL properly
    try:
        parsed = urlparse(request.url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {str(e)}")
    
    request_id = str(uuid4())[:8]  # Short ID
    
    # Initialize with SIMPLE string timestamps (no datetime objects!)
    results_store[request_id] = {
        "status": "pending",
        "url": request.url,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "max_pages": request.max_pages,
            "use_js": request.use_js
        }
    }
    
    # Start background task
    background_tasks.add_task(
        run_crawler_safe,
        request_id,
        request.url,
        request.max_pages,
        request.use_js,
        request.same_domain_only,
        request.delay_seconds
    )
    
    return {
        "request_id": request_id,
        "message": f"Crawl started! Max {request.max_pages} pages",
        "status": "pending",
        "check_results": f"/results/{request_id}"
    }

async def run_crawler_safe(
    request_id: str,
    start_url: str,
    max_pages: int,
    use_js: bool,
    same_domain_only: bool,
    delay_seconds: float
):
    """Safe crawler wrapper that catches ALL errors"""
    
    try:
        # Update status
        results_store[request_id]["status"] = "running"
        results_store[request_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        logger.info(f"▶️ Starting crawl {request_id}: {start_url}")
        
        if use_js:
            await run_playwright_mode(request_id, start_url, max_pages, same_domain_only, delay_seconds)
        else:
            await run_static_mode(request_id, start_url, max_pages, same_domain_only, delay_seconds)
            
    except Exception as e:
        logger.error(f"❌ Crawl {request_id} FAILED: {str(e)}", exc_info=True)
        
        # Store failure with simple timestamp
        results_store[request_id] = {
            "status": "failed",
            "error": str(e),
            "url": start_url,
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "Check logs for details"
        }

async def run_static_mode(
    request_id: str,
    start_url: str,
    max_pages: int,
    same_domain_only: bool,
    delay_seconds: float
):
    """STATIC MODE - Uses httpx + BeautifulSoup (RELIABLE)"""
    
    import httpx
    from bs4 import BeautifulSoup
    
    crawled_data = []
    visited_urls = set()
    queue = [start_url]
    base_domain = urlparse(start_url).netloc.lower()
    
    # Browser-like headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    logger.info(f"📄 Using STATIC mode for {start_url}")
    
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=30.0  # Simple timeout value, NO complex objects!
    ) as client:
        
        while queue and len(crawled_data) < max_pages:
            current_url = queue.pop(0)
            
            # Normalize URL
            current_url = current_url.split('#')[0].rstrip('/')
            
            if current_url in visited_urls:
                continue
                
            # Check domain
            if same_domain_only:
                current_domain = urlparse(current_url).netloc.lower()
                if current_domain != base_domain:
                    continue
            
            visited_urls.add(current_url)
            
            try:
                # Update progress
                results_store[request_id]["progress"] = f"{len(crawled_data)+1}/{max_pages}"
                results_store[request_id]["current_url"] = current_url
                
                logger.info(f"[{len(crawled_data)+1}/{max_pages}] 📥 {current_url[:60]}...")
                
                # Fetch page
                response = await client.get(current_url)
                
                # Check status code
                if response.status_code != 200:
                    crawled_data.append({
                        "url": current_url,
                        "title": f"HTTP Error {response.status_code}",
                        "status": "failed"
                    })
                    continue
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract title
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True)[:200] if title_tag else "No Title"
                
                # Extract description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                description = meta_desc['content'][:300] if meta_desc and meta_desc.get('content') else ""
                
                # Clean text content
                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    tag.decompose()
                
                text = soup.get_text(separator=' ', strip=True)[:500]
                
                # SUCCESS! Add to results
                page_result = {
                    "url": current_url,
                    "title": title,
                    "description": description,
                    "content_preview": text,
                    "status_code": response.status_code,
                    "status": "success"
                }
                
                crawled_data.append(page_result)
                logger.info(f"  ✅ {title[:50]}...")
                
                # Extract links ONLY if we need more pages
                if len(crawled_data) < max_pages:
                    links_added = 0
                    
                    for a_tag in soup.find_all('a', href=True):
                        if links_added >= 15:  # Limit links per page
                            break
                        
                        href = a_tag['href']
                        
                        # Build full URL
                        full_url = urljoin(current_url, href)
                        
                        # Parse and validate
                        parsed = urlparse(full_url)
                        
                        # Skip non-HTTP
                        if parsed.scheme not in ['http', 'https']:
                            continue
                        
                        # Skip files/images
                        if any(ext in full_url.lower() for ext in ['.pdf', '.jpg', '.png', '.gif', '.zip', '.css', '.js']):
                            continue
                        
                        # Skip fragments
                        if '#' in full_url:
                            full_url = full_url.split('#')[0]
                        
                        # Domain check
                        if same_domain_only:
                            if parsed.netloc.lower() != base_domain:
                                continue
                        
                        # Add if new
                        normalized = full_url.rstrip('/')
                        if normalized not in visited_urls and normalized not in queue:
                            queue.append(normalized)
                            links_added += 1
                
                # Rate limit
                await asyncio.sleep(delay_seconds)
                
            except httpx.TimeoutException:
                logger.warning(f"  ⏰ Timeout: {current_url}")
                crawled_data.append({
                    "url": current_url,
                    "error": "Request timeout",
                    "status": "failed"
                })
            except Exception as e:
                logger.error(f"  ❌ Error: {e}")
                crawled_data.append({
                    "url": current_url,
                    "error": str(e)[:200],
                    "status": "failed"
                })
    
    # FINAL RESULTS - Use only strings and basic types!
    success_count = sum(1 for d in crawled_data if d['status'] == 'success')
    
    final_result = {
        "status": "completed",
        "start_url": start_url,
        "crawler_type": "static",
        "total_attempted": len(crawled_data),
        "successful": success_count,
        "unique_visited": len(visited_urls),
        "results": crawled_data,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": "N/A",  # Avoid timedelta calculations
        "message": f"✅ Crawled {success_count} pages successfully!"
    }
    
    results_store[request_id] = final_result
    logger.info(f"✅ Crawl {request_id} DONE! Success: {success_count}/{len(crawled_data)}")

async def run_playwright_mode(
    request_id: str,
    start_url: str,
    max_pages: int,
    same_domain_only: bool,
    delay_seconds: float
):
    """PLAYWRIGHT MODE - For JavaScript sites"""
    
    try:
        from crawlee.crawlers import PlaywrightCrawler
        from crawlee._types import EnqueueStrategy
        
    except ImportError:
        raise ImportError("Playwright not installed! Run: pip install 'crawlee[playwright]' && playwright install chromium")
    
    crawled_data = []
    visited_urls = set()
    base_domain = urlparse(start_url).netloc.lower()
    
    logger.info(f"🎭 Using PLAYWRIGHT mode for {start_url}")
    
    crawler = PlaywrightCrawler(
        max_requests_per_crawl=max_pages * 2,
        headless=True,
    )
    
    @crawler.router.default_handler
    async def handler(context):
        nonlocal crawled_data
        
        url = context.request.url
        
        if url in visited_urls:
            return
            
        if same_domain_only:
            if urlparse(url).netloc.lower() != base_domain:
                return
        
        visited_urls.add(url)
        
        try:
            # Wait for load
            await context.page.wait_for_load_state('networkidle')
            await asyncio.sleep(0.5)
            
            # Get data
            title = await context.page.title()
            
            text = await context.page.evaluate("""
                () => {
                    const body = document.body.cloneNode(true);
                    body.querySelectorAll('script, style, nav, footer').forEach(el => el.remove());
                    return body.innerText.substring(0, 500);
                }
            """)
            
            # Add result
            crawled_data.append({
                "url": url,
                "title": (title or "No Title")[:200],
                "content_preview": (text or "")[:500],
                "status": "success"
            })
            
            logger.info(f"[{len(crawled_data)}] ✅ {(title or '')[:50]}...")
            
            # Update progress
            results_store[request_id]["progress"] = f"{len(crawled_data)}/{max_pages}"
            
            # Enqueue links if needed
            if len(crawled_data) < max_pages:
                strategy = EnqueueStrategy.SAME_DOMAIN if same_domain_only else EnqueueStrategy.ALL
                await context.enqueue_links(strategy=strategy, limit=5)
            
            await asyncio.sleep(delay_seconds)
            
        except Exception as e:
            logger.warning(f"Error on {url}: {e}")
            crawled_data.append({"url": url, "error": str(e)[:200], "status": "failed"})
    
    # Run crawler
    await crawler.run([start_url])
    
    # Finalize
    success_count = sum(1 for d in crawled_data if d['status'] == 'success')
    
    results_store[request_id] = {
        "status": "completed",
        "start_url": start_url,
        "crawler_type": "playwright",
        "total_attempted": len(crawled_data),
        "successful": success_count,
        "results": crawled_data[:max_pages],
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": f"✅ Crawled {success_count} pages!"
    }

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    """Get specific crawl results"""
    if request_id not in results_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    data = results_store[request_id]
    
    # Add helpful info
    if data["status"] == "running":
        data["message"] = "Still crawling... Check back soon!"
    elif data["status"] == "failed":
        data["message"] = f"❌ Failed: {data.get('error', 'Unknown error')}"
    
    return data

@app.get("/results")
async def list_all_results():
    """List all crawl jobs"""
    summary = {}
    
    for rid, data in results_store.items():
        summary[rid] = {
            "status": data.get("status"),
            "url": data.get("url", "")[:50],
            "created": data.get("created_at"),
            "progress": data.get("progress", "N/A"),
            "has_results": "results" in data
        }
    
    return {
        "total_jobs": len(results_store),
        "jobs": summary
    }

@app.delete("/results/{request_id}")
async def delete_job(request_id: str):
    """Delete a completed job"""
    if request_id not in results_store:
        raise HTTPException(status_code=404, detail="Not found")
    
    del results_store[request_id]
    return {"deleted": True, "id": request_id}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    print(f"Test: curl -X POST http://localhost:{port}/crawl -d '{{\"url\":\"https://example.com\",\"use_js\":false}}'")
    uvicorn.run(app, host="0.0.0.0", port=port)
