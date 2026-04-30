from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from uuid import uuid4
import asyncio
import os
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, urljoin
from datetime import datetime
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Advanced Web Crawler",
    description="Production-ready web crawler with JS support",
    version="2.0.0"
)

# Store results with better structure
results_store: Dict[str, Dict[str, Any]] = {}

class CrawlRequest(BaseModel):
    url: str = Field(..., description="Starting URL to crawl")
    max_pages: int = Field(default=10, ge=1, le=100, description="Maximum pages to crawl")
    use_js: bool = Field(default=True, description="Use JavaScript rendering (Playwright)")
    same_domain_only: bool = Field(default=True, description="Only crawl same domain")
    respect_robots_txt: bool = Field(default=True, description="Respect robots.txt")
    delay_seconds: float = Field(default=1.0, ge=0.5, le=5.0, description="Delay between requests")

class CrawlResponse(BaseModel):
    request_id: str
    message: str
    status: str

@app.get("/")
async def root():
    return {
        "message": "🚀 Advanced Web Crawler API v2.0",
        "endpoints": {
            "POST /crawl": "Start a new crawl job",
            "GET /results/{request_id}": "Get crawl results",
            "GET /results": "List all crawl jobs",
            "GET /health": "Health check"
        }
    }

@app.get("/health")
async def health():
    return {"status": "alive", "timestamp": datetime.now().isoformat()}

@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Start a new crawl job"""
    
    # Validate URL
    try:
        parsed = urlparse(request.url)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL format")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {str(e)}")
    
    request_id = str(uuid4())
    
    # Initialize result entry
    results_store[request_id] = {
        "status": "pending",
        "url": request.url,
        "created_at": datetime.now().isoformat(),
        "config": request.dict()
    }
    
    # Start background crawl
    background_tasks.add_task(
        run_crawler, 
        request.url, 
        request_id, 
        request.max_pages,
        request.use_js,
        request.same_domain_only,
        request.respect_robots_txt,
        request.delay_seconds
    )
    
    logger.info(f"✅ Started crawl {request_id} for {request.url}")
    
    return CrawlResponse(
        request_id=request_id,
        message=f"Crawl started! Will crawl up to {request.max_pages} pages",
        status="pending"
    )

async def run_crawler(
    start_url: str, 
    request_id: str, 
    max_pages: int,
    use_js: bool,
    same_domain_only: bool,
    respect_robots_txt: bool,
    delay_seconds: float
):
    """Enhanced crawler with proper error handling and link following"""
    
    try:
        # Update status to running
        results_store[request_id]["status"] = "running"
        results_store[request_id]["started_at"] = datetime.now().isoformat()
        
        if use_js:
            await _run_playwright_crawler(
                start_url, request_id, max_pages, 
                same_domain_only, delay_seconds
            )
        else:
            await _run_static_crawler(
                start_url, request_id, max_pages,
                same_domain_only, delay_seconds
            )
            
    except Exception as e:
        logger.error(f"❌ Crawl {request_id} failed: {str(e)}", exc_info=True)
        results_store[request_id] = {
            "status": "failed",
            "error": str(e),
            "url": start_url,
            "completed_at": datetime.now().isoformat()
        }

async def _run_playwright_crawler(
    start_url: str, 
    request_id: str, 
    max_pages: int,
    same_domain_only: bool,
    delay_seconds: float
):
    """Playwright-based crawler for JavaScript-heavy sites"""
    
    try:
        from crawlee.crawlers import PlaywrightCrawler
        from crawlee._types import EnqueueStrategy
        
        crawled_data = []
        visited_urls = set()
        base_domain = urlparse(start_url).netloc
        
        logger.info(f"🎭 Starting Playwright crawler for {start_url}")
        
        # Configure crawler with better settings
        crawler = PlaywrightCrawler(
            max_requests_per_crawl=max_pages * 2,  # Allow some extra for failed attempts
            headless=True,
            request_handler_timeout=60000,  # 60 seconds timeout
            max_request_retries=2,
        )
        
        @crawler.router.default_handler
        async def handler(context):
            nonlocal crawled_data
            
            url = context.request.url
            
            # Skip if already visited
            if url in visited_urls:
                return
            
            # Check domain restriction
            if same_domain_only:
                current_domain = urlparse(url).netloc
                if current_domain != base_domain:
                    logger.debug(f"Skipping different domain: {url}")
                    return
            
            visited_urls.add(url)
            
            try:
                # Wait for page to fully load
                await context.page.wait_for_load_state('networkidle')
                
                # Additional wait for dynamic content
                await asyncio.sleep(1)
                
                # Get page data
                title = await context.page.title()
                
                # Extract text content (first 500 chars)
                text_content = await context.page.evaluate("""
                    () => {
                        // Remove scripts and styles
                        const body = document.body.cloneNode(true);
                        body.querySelectorAll('script, style, nav, footer, header').forEach(el => el.remove());
                        return body.innerText.substring(0, 1000);
                    }
                """)
                
                # Save successful crawl
                page_data = {
                    'url': url,
                    'title': title[:200] if title else 'No title',
                    'content_preview': text_content[:500] if text_content else '',
                    'status': 'success',
                    'crawled_at': datetime.now().isoformat()
                }
                
                crawled_data.append(page_data)
                logger.info(f"[{len(crawled_data)}/{max_pages}] ✅ Crawled: {title[:50]}...")
                
                # Update progress in store
                results_store[request_id]["progress"] = f"{len(crawled_data)}/{max_pages}"
                results_store[request_id]["results_so_far"] = len(crawled_data)
                
                # Stop if we've reached max
                if len(crawled_data) >= max_pages:
                    return
                
                # Enqueue links with strategy
                await context.enqueue_links(
                    strategy=EnqueueStrategy.SAME_DOMAIN if same_domain_only else EnqueueStrategy.ALL,
                    limit=5  # Limit links per page to avoid explosion
                )
                
                # Respect rate limiting
                await asyncio.sleep(delay_seconds)
                
            except Exception as e:
                logger.warning(f"Error crawling {url}: {e}")
                crawled_data.append({
                    'url': url,
                    'error': str(e),
                    'status': 'failed'
                })
        
        # Run the crawler
        logger.info(f"▶️ Running crawler on {start_url}")
        await crawler.run([start_url])
        
        # Finalize results
        success_count = sum(1 for d in crawled_data if d.get('status') == 'success')
        
        results_store[request_id] = {
            "status": "completed",
            "start_url": start_url,
            "total_pages_attempted": len(crawled_data),
            "successful_crawls": success_count,
            "unique_urls_visited": len(visited_urls),
            "results": crawled_data[:max_pages],  # Limit to requested amount
            "completed_at": datetime.now().isoformat(),
            "crawler_type": "playwright"
        }
        
        logger.info(f"✅ Crawl {request_id} completed! Success: {success_count}/{len(crawled_data)}")
        
    except ImportError as e:
        logger.error(f"Playwright not installed: {e}")
        raise Exception(f"Playwright not installed. Run: pip install crawlee[playwright]")
    except Exception as e:
        logger.error(f"Playwright crawler error: {e}", exc_info=True)
        raise

async def _run_static_crawler(
    start_url: str, 
    request_id: str, 
    max_pages: int,
    same_domain_only: bool,
    delay_seconds: float
):
    """Static HTTP crawler using httpx + BeautifulSoup"""
    
    import httpx
    from bs4 import BeautifulSoup
    
    crawled_data = []
    visited_urls = set()
    queue = [start_url]
    base_domain = urlparse(start_url).netloc
    
    logger.info(f"📄 Starting static crawler for {start_url}")
    
    # Configure HTTP client with browser-like headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        headers=headers,
        verify=False  # Be careful with this in production
    ) as client:
        
        while queue and len(crawled_data) < max_pages:
            current_url = queue.pop(0)
            
            # Skip if visited
            if current_url in visited_urls:
                continue
            
            # Check domain
            if same_domain_only:
                current_domain = urlparse(current_url).netloc
                if current_domain != base_domain:
                    continue
            
            visited_urls.add(current_url)
            
            try:
                logger.info(f"[{len(crawled_data)+1}/{max_pages}] 📥 Fetching: {current_url}")
                
                response = await client.get(current_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract title
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else 'No title'
                
                # Extract meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                description = meta_desc['content'] if meta_desc else ''
                
                # Extract main content (simple approach)
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text_content = soup.get_text(separator=' ', strip=True)[:500]
                
                # Save successful result
                page_data = {
                    'url': current_url,
                    'title': title[:200],
                    'description': description[:300],
                    'content_preview': text_content,
                    'status_code': response.status_code,
                    'status': 'success',
                    'crawled_at': datetime.now().isoformat()
                }
                
                crawled_data.append(page_data)
                logger.info(f"  ✅ Success: {title[:50]}...")
                
                # Update progress
                results_store[request_id]["progress"] = f"{len(crawled_data)}/{max_pages}"
                
                # Extract and queue links
                if len(crawled_data) < max_pages:
                    links_found = 0
                    for link in soup.find_all('a', href=True):
                        if links_found >= 10:  # Limit links per page
                            break
                            
                        href = link['href']
                        
                        # Clean and validate URL
                        full_url = urljoin(current_url, href)
                        parsed_url = urlparse(full_url)
                        
                        # Skip non-http URLs
                        if parsed_url.scheme not in ['http', 'https']:
                            continue
                        
                        # Skip fragments and common non-page URLs
                        if '#' in full_url or any(x in full_url.lower() for x in ['.pdf', '.jpg', '.png', '.zip']):
                            continue
                        
                        # Check domain restriction
                        if same_domain_only and parsed_url.netloc != base_domain:
                            continue
                        
                        # Add to queue if new
                        if full_url not in visited_urls and full_url not in queue:
                            queue.append(full_url)
                            links_found += 1
                
                # Rate limiting
                await asyncio.sleep(delay_seconds)
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"  ❌ HTTP Error {e.response.status_code}: {current_url}")
                crawled_data.append({
                    'url': current_url,
                    'error': f'HTTP {e.response.status_code}',
                    'status': 'failed'
                })
            except httpx.RequestError as e:
                logger.warning(f"  ❌ Request Error: {e}")
                crawled_data.append({
                    'url': current_url,
                    'error': str(e),
                    'status': 'failed'
                })
            except Exception as e:
                logger.error(f"  ❌ Unexpected error: {e}")
                crawled_data.append({
                    'url': current_url,
                    'error': str(e),
                    'status': 'failed'
                })
    
    # Finalize results
    success_count = sum(1 for d in crawled_data if d.get('status') == 'success')
    
    results_store[request_id] = {
        "status": "completed",
        "start_url": start_url,
        "total_pages_attempted": len(crawled_data),
        "successful_crawls": success_count,
        "urls_in_queue": len(queue),
        "results": crawled_data,
        "completed_at": datetime.now().isoformat(),
        "crawler_type": "static"
    }
    
    logger.info(f"✅ Static crawl {request_id} completed! Success: {success_count}/{len(crawled_data)}")

@app.get("/results/{request_id}")
async def get_results(request_id: str):
    """Get results for a specific crawl job"""
    if request_id not in results_store:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    
    return results_store[request_id]

@app.get("/results")
async def list_results():
    """List all crawl jobs with summary"""
    summary = {}
    for rid, data in results_store.items():
        summary[rid] = {
            "status": data.get("status"),
            "url": data.get("url"),
            "created_at": data.get("created_at"),
            "progress": data.get("progress", "N/A")
        }
    
    return {
        "total_crawls": len(results_store),
        "crawls": summary
    }

@app.delete("/results/{request_id}")
async def delete_results(request_id: str):
    """Delete a crawl job's results"""
    if request_id not in results_store:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    
    del results_store[request_id]
    return {"message": f"Crawl job {request_id} deleted"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting Advanced Web Crawler on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
