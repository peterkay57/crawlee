from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4
import asyncio
import os
import logging
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlparse, urljoin, urldefrag
from datetime import datetime
import time

# ====================== CONFIG & LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("crawler")

app = FastAPI(title="Web Crawler", version="5.0")

# Store results
results_store: Dict[str, Dict[str, Any]] = {}

# ====================== MODELS ======================
class CrawlRequest(BaseModel):
    url: str = Field(..., description="Starting URL")
    max_pages: int = Field(default=20, ge=1, le=100)
    use_js: bool = Field(default=False, description="Use JavaScript rendering")
    delay: float = Field(default=1.0, ge=0.3, le=3.0)

# ====================== HELPER FUNCTIONS ======================
def normalize_url(url: str) -> str:
    """Clean and normalize URL"""
    url = urldefrag(url)[0].rstrip('/')
    return url

def is_same_domain(url1: str, url2: str) -> bool:
    return urlparse(url1).netloc.lower() == urlparse(url2).netloc.lower()

def should_skip_url(url: str) -> bool:
    """Skip images, videos, etc."""
    skip_extensions = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
                       '.zip', '.rar', '.tar', '.gz', '.exe', '.mp4', '.mp3',
                       '.css', '.js', '.json', '.xml')
    return url.lower().endswith(skip_extensions)

# ====================== STATIC CRAWLER (Works on Wikipedia, Hacker News, etc.) ======================
async def crawl_static(
    job_id: str,
    start_url: str,
    max_pages: int,
    delay: float
) -> List[Dict]:
    
    import httpx
    from bs4 import BeautifulSoup

    results: List[Dict] = []
    visited: Set[str] = set()
    queue: List[str] = [start_url]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=30.0
    ) as client:

        while queue and len(results) < max_pages:
            current_url = queue.pop(0)
            current_url = normalize_url(current_url)

            if current_url in visited:
                continue
            
            if should_skip_url(current_url):
                continue

            visited.add(current_url)

            try:
                logger.info(f"[{job_id}] [{len(results)+1}/{max_pages}] → {current_url[:80]}")

                response = await client.get(current_url)
                
                if response.status_code != 200:
                    logger.warning(f"[{job_id}] HTTP {response.status_code} on {current_url}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract title
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True)[:200] if title_tag else "No Title"

                # Extract description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                description = meta_desc.get('content', '')[:300] if meta_desc else ""

                # Save result
                results.append({
                    "url": current_url,
                    "title": title,
                    "description": description,
                    "status": "success"
                })

                # ==========================================================
                # CRITICAL: FIND AND ADD NEW LINKS TO QUEUE
                # ==========================================================
                links_added = 0
                for link in soup.find_all('a', href=True):
                    if links_added >= 30:  # Limit per page
                        break
                        
                    href = link['href'].strip()
                    if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                        continue

                    full_url = normalize_url(urljoin(current_url, href))
                    
                    # Only stay on same domain
                    if not is_same_domain(full_url, start_url):
                        continue
                    
                    if should_skip_url(full_url):
                        continue
                    
                    if full_url not in visited and full_url not in queue:
                        queue.append(full_url)
                        links_added += 1

                if links_added > 0:
                    logger.info(f"[{job_id}] Found {links_added} new links. Queue size: {len(queue)}")

                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"[{job_id}] Error on {current_url}: {str(e)[:80]}")
                results.append({
                    "url": current_url,
                    "title": "Error",
                    "description": str(e)[:200],
                    "status": "failed"
                })

    return results


# ====================== BROWSER CRAWLER (For JavaScript-heavy sites) ======================
async def crawl_browser(
    job_id: str,
    start_url: str,
    max_pages: int,
    delay: float
) -> List[Dict]:
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("[{}] Playwright not installed".format(job_id))
        return []

    results: List[Dict] = []
    visited: Set[str] = set()
    queue: List[str] = [start_url]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()

        while queue and len(results) < max_pages:
            current_url = queue.pop(0)
            current_url = normalize_url(current_url)

            if current_url in visited:
                continue

            visited.add(current_url)

            try:
                logger.info(f"[{job_id}] [{len(results)+1}/{max_pages}] Browser → {current_url[:80]}")

                await page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(1)  # Let JavaScript render

                title = await page.title()
                
                # Get description
                description = await page.evaluate("""() => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.content : '';
                }""")

                results.append({
                    "url": current_url,
                    "title": title[:200] if title else "No Title",
                    "description": description[:300] if description else "",
                    "status": "success"
                })

                # Extract links
                if len(results) < max_pages:
                    links = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(href => {
                                if (!href || href.startsWith('javascript:') || href.startsWith('mailto:')) return false;
                                return true;
                            });
                    }""")

                    added = 0
                    for link in links[:50]:  # Limit per page
                        clean_link = normalize_url(link)
                        if not is_same_domain(clean_link, start_url):
                            continue
                        if should_skip_url(clean_link):
                            continue
                        if clean_link not in visited and clean_link not in queue:
                            queue.append(clean_link)
                            added += 1

                    if added > 0:
                        logger.info(f"[{job_id}] Found {added} new links. Queue size: {len(queue)}")

                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"[{job_id}] Browser error: {str(e)[:80]}")
                results.append({
                    "url": current_url,
                    "title": "Error",
                    "description": str(e)[:200],
                    "status": "failed"
                })

        await browser.close()

    return results


# ====================== MAIN EXECUTOR ======================
async def execute_crawl(
    job_id: str,
    start_url: str,
    max_pages: int,
    use_js: bool,
    delay: float
):
    start_time = time.time()

    try:
        results_store[job_id]["status"] = "running"
        logger.info(f"[{job_id}] Starting crawl | JS: {use_js} | Max: {max_pages}")

        if use_js:
            results = await crawl_browser(job_id, start_url, max_pages, delay)
            mode_used = "browser"
        else:
            results = await crawl_static(job_id, start_url, max_pages, delay)
            mode_used = "static"

        duration = round(time.time() - start_time, 2)
        successful = len([r for r in results if r.get("status") == "success"])

        final_result = {
            "status": "completed",
            "start_url": start_url,
            "mode_used": mode_used,
            "total_pages_crawled": len(results),
            "successful_pages": successful,
            "failed_pages": len(results) - successful,
            "results": results,
            "duration_seconds": duration,
            "completed_at": datetime.now().isoformat()
        }

        results_store[job_id] = final_result
        logger.info(f"[{job_id}] ✅ COMPLETED | {successful} pages in {duration}s")

    except Exception as e:
        logger.error(f"[{job_id}] ❌ FAILED: {str(e)}")
        results_store[job_id] = {
            "status": "failed",
            "start_url": start_url,
            "error": str(e),
            "duration_seconds": round(time.time() - start_time, 2),
            "completed_at": datetime.now().isoformat()
        }


# ====================== ROUTES ======================
@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    # Validate URL
    try:
        parsed = urlparse(request.url)
        if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    job_id = str(uuid4())[:12]

    results_store[job_id] = {
        "status": "queued",
        "start_url": request.url,
        "max_pages": request.max_pages,
        "use_js": request.use_js,
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(
        execute_crawl,
        job_id, request.url, request.max_pages, request.use_js, request.delay
    )

    return {
        "job_id": job_id,
        "message": f"Crawl started. Will crawl up to {request.max_pages} pages",
        "check_url": f"/results/{job_id}"
    }


@app.get("/results/{job_id}")
async def get_results(job_id: str):
    if job_id not in results_store:
        raise HTTPException(status_code=404, detail="Job not found")
    return results_store[job_id]


@app.get("/results")
async def list_jobs():
    return {
        "total_jobs": len(results_store),
        "jobs": {
            jid: {
                "status": data.get("status"),
                "url": data.get("start_url", "")[:60],
                "pages": data.get("total_pages_crawled", 0),
                "created_at": data.get("created_at")
            }
            for jid, data in results_store.items()
        }
    }


@app.get("/")
async def root():
    return {
        "message": "Web Crawler API",
        "endpoints": {
            "/": "This help",
            "/health": "Health check",
            "/docs": "Interactive API docs",
            "/crawl": "POST - Start crawl",
            "/results": "GET - List all crawls",
            "/results/{job_id}": "GET - Get specific crawl results"
        }
    }


@app.get("/health")
async def health():
    return {"status": "alive", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
