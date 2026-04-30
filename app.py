from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4
import asyncio
import os
import logging
import json
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlparse, urljoin, urldefrag
from datetime import datetime
import time
import re

# ====================== CONFIG & LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ultimate-crawler")

app = FastAPI(
    title="Ultimate Web Crawler v5.0",
    description="Advanced, production-grade crawler with smart link extraction and fallbacks",
    version="5.0"
)

# In-memory store (use Redis in production)
results_store: Dict[str, Dict[str, Any]] = {}

# ====================== MODELS ======================
class CrawlRequest(BaseModel):
    url: str = Field(..., description="Starting URL")
    max_pages: int = Field(default=20, ge=1, le=100)
    mode: str = Field(default="auto", pattern="^(auto|static|browser)$")
    delay: float = Field(default=1.2, ge=0.3, le=5.0)
    same_domain: bool = Field(default=True)
    respect_robots: bool = Field(default=False)  # Future extension
    max_depth: Optional[int] = Field(default=None, ge=1)


# ====================== HELPER FUNCTIONS ======================
def normalize_url(url: str) -> str:
    """Clean and normalize URL properly"""
    url = urldefrag(url)[0].rstrip('/')  # Remove fragment and trailing slash
    return url


def is_same_domain(url1: str, url2: str) -> bool:
    return urlparse(url1).netloc.lower() == urlparse(url2).netloc.lower()


def should_skip_url(url: str) -> bool:
    """Advanced URL filtering"""
    parsed = urlparse(url)
    lower_url = url.lower()
    
    skip_extensions = {
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
        '.zip', '.rar', '.tar', '.gz', '.exe', '.dmg', '.mp4',
        '.css', '.js', '.json', '.xml', '.rss', '.atom'
    }
    
    if any(lower_url.endswith(ext) for ext in skip_extensions):
        return True
    
    # Skip common non-content paths
    skip_patterns = [
        r'/login', r'/signup', r'/auth', r'/account', r'/cart',
        r'/checkout', r'/api/', r'/admin', r'/wp-admin', r'/feed',
        r'/tag/', r'/category/', r'/page/\d+'
    ]
    
    return any(re.search(pattern, lower_url) for pattern in skip_patterns)


def log(job_id: str, message: str, level: str = "info"):
    msg = f"[{job_id}] {message}"
    if level == "error":
        logger.error(msg)
    elif level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)
    
    if job_id in results_store:
        if "logs" not in results_store[job_id]:
            results_store[job_id]["logs"] = []
        results_store[job_id]["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")


# ====================== STATIC CRAWLER (Recommended for most sites) ======================
async def crawl_static(
    job_id: str,
    start_url: str,
    max_pages: int,
    delay: float,
    same_domain: bool,
    max_depth: Optional[int] = None
) -> Dict[str, Any]:
    
    import httpx
    from bs4 import BeautifulSoup

    results: List[Dict] = []
    visited: Set[str] = set()
    queue: List[tuple[str, int]] = [(start_url, 0)]  # (url, depth)
    base_domain = urlparse(start_url).netloc.lower()
    total_links_found = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(25.0, connect=10.0),
        verify=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
    ) as client:

        while queue and len(results) < max_pages:
            current_url, depth = queue.pop(0)
            current_url = normalize_url(current_url)

            if current_url in visited:
                continue

            if same_domain and not is_same_domain(current_url, start_url):
                continue

            if max_depth and depth >= max_depth:
                continue

            visited.add(current_url)

            try:
                log(job_id, f"[{len(results)+1}/{max_pages}] Fetching → {current_url[:90]}")

                response = await client.get(current_url)
                
                if response.status_code != 200:
                    log(job_id, f"HTTP {response.status_code} on {current_url}", "warning")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract metadata
                title = soup.find('title')
                title_text = title.get_text(strip=True)[:200] if title else "No Title"

                meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                           soup.find('meta', attrs={'property': 'og:description'})
                description = meta_desc.get('content', '')[:350] if meta_desc else ""

                # Clean content
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()

                content_preview = soup.get_text(separator=' ', strip=True)[:550]

                page_result = {
                    "url": current_url,
                    "title": title_text,
                    "description": description,
                    "content_preview": content_preview,
                    "status": "success",
                    "status_code": response.status_code,
                    "depth": depth
                }

                results.append(page_result)
                log(job_id, f"✅ Success: {title_text[:70]}...")

                # === ADVANCED LINK EXTRACTION ===
                if len(results) < max_pages:
                    added_this_page = 0
                    
                    for a_tag in soup.find_all('a', href=True):
                        if added_this_page >= 25:  # Limit per page to avoid explosion
                            break
                            
                        href = a_tag['href'].strip()
                        if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                            continue

                        full_url = normalize_url(urljoin(current_url, href))

                        if should_skip_url(full_url):
                            continue

                        if same_domain and not is_same_domain(full_url, start_url):
                            continue

                        if full_url not in visited and full_url not in [u[0] for u in queue]:
                            queue.append((full_url, depth + 1))
                            added_this_page += 1
                            total_links_found += 1

                await asyncio.sleep(delay)

            except Exception as e:
                log(job_id, f"Error fetching {current_url}: {str(e)[:100]}", "error")

    return {
        "mode": "static",
        "results": results,
        "links_found": total_links_found,
        "pages_visited": len(visited)
    }


# ====================== BROWSER CRAWLER (For heavy JS sites) ======================
async def crawl_browser(
    job_id: str,
    start_url: str,
    max_pages: int,
    delay: float,
    same_domain: bool,
    max_depth: Optional[int] = None
) -> Dict[str, Any]:
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log(job_id, "Playwright not installed. Run: pip install playwright && playwright install chromium", "error")
        return {"mode": "browser", "results": [], "links_found": 0}

    results: List[Dict] = []
    visited: Set[str] = set()
    queue: List[tuple[str, int]] = [(start_url, 0)]
    base_domain = urlparse(start_url).netloc.lower()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )

        page = await context.new_page()

        while queue and len(results) < max_pages:
            current_url, depth = queue.pop(0)
            current_url = normalize_url(current_url)

            if current_url in visited:
                continue
            if same_domain and not is_same_domain(current_url, start_url):
                continue
            if max_depth and depth >= max_depth:
                continue

            visited.add(current_url)

            try:
                log(job_id, f"[{len(results)+1}/{max_pages}] Browser → {current_url[:85]}")

                await page.goto(current_url, wait_until='domcontentloaded', timeout=45000)
                await asyncio.sleep(1.5)  # Allow JS to render

                title = await page.title()
                description = await page.evaluate("""() => {
                    const meta = document.querySelector('meta[name="description"], meta[property="og:description"]');
                    return meta ? meta.content : '';
                }""")

                content_preview = await page.evaluate("""() => {
                    const body = document.body.cloneNode(true);
                    body.querySelectorAll('script, style, nav, footer, header, aside').forEach(el => el.remove());
                    return body.innerText.substring(0, 550).replace(/\s+/g, ' ');
                }""")

                results.append({
                    "url": current_url,
                    "title": (title or "No Title")[:200],
                    "description": (description or "")[:350],
                    "content_preview": content_preview,
                    "status": "success",
                    "depth": depth
                })

                log(job_id, f"✅ Browser success: {title[:65]}...")

                # Extract links using JavaScript (more accurate for JS-rendered links)
                if len(results) < max_pages:
                    links = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(href => {
                                if (!href || href.startsWith('javascript:') || 
                                    href.startsWith('mailto:') || href.startsWith('#')) return false;
                                return !/\\.(pdf|jpg|jpeg|png|gif|zip|rar|css|js)$/i.test(href);
                            });
                    }""")

                    added = 0
                    for link in links:
                        if added >= 20:
                            break
                        clean_link = normalize_url(link)
                        if (same_domain and not is_same_domain(clean_link, start_url)) or should_skip_url(clean_link):
                            continue
                        if clean_link not in visited and clean_link not in [u[0] for u in queue]:
                            queue.append((clean_link, depth + 1))
                            added += 1

                await asyncio.sleep(delay)

            except Exception as e:
                log(job_id, f"Browser error on {current_url}: {str(e)[:100]}", "error")

        await browser.close()

    return {
        "mode": "browser",
        "results": results,
        "links_found": len(visited) - 1,  # rough estimate
        "pages_visited": len(visited)
    }


# ====================== MAIN EXECUTOR WITH SMART FALLBACKS ======================
async def execute_crawl_with_fallbacks(
    job_id: str,
    start_url: str,
    max_pages: int,
    mode: str,
    delay: float,
    same_domain: bool,
    max_depth: Optional[int]
):
    start_time = time.time()

    try:
        results_store[job_id]["status"] = "running"
        log(job_id, f"Starting crawl | Mode: {mode} | Max Pages: {max_pages}")

        result_data = None

        if mode == "auto":
            domain = urlparse(start_url).netloc.lower()
            static_friendly = any(x in domain for x in ['wikipedia', 'github', 'stackoverflow', 'medium', 'dev.to'])

            if static_friendly:
                log(job_id, "Auto → Using STATIC mode first")
                result_data = await crawl_static(job_id, start_url, max_pages, delay, same_domain, max_depth)
            else:
                log(job_id, "Auto → Trying BROWSER first")
                result_data = await crawl_browser(job_id, start_url, max_pages, delay, same_domain, max_depth)

        elif mode == "static":
            result_data = await crawl_static(job_id, start_url, max_pages, delay, same_domain, max_depth)
        elif mode == "browser":
            result_data = await crawl_browser(job_id, start_url, max_pages, delay, same_domain, max_depth)

        duration = round(time.time() - start_time, 2)

        final_result = {
            "status": "completed",
            "url": start_url,
            "mode_used": result_data.get("mode", mode),
            "total_found": len(result_data.get("results", [])),
            "successful": len([r for r in result_data.get("results", []) if r.get("status") == "success"]),
            "results": result_data.get("results", []),
            "links_discovered": result_data.get("links_found", 0),
            "pages_visited": result_data.get("pages_visited", 0),
            "duration_seconds": duration,
            "completed_at": datetime.now().isoformat(),
            "logs": results_store[job_id].get("logs", [])
        }

        results_store[job_id] = final_result
        log(job_id, f"✅ CRAWL COMPLETED | {final_result['successful']} pages in {duration}s")

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        log(job_id, f"❌ CRAWL FAILED: {str(e)}", "error")
        results_store[job_id] = {
            "status": "error",
            "url": start_url,
            "error": str(e),
            "duration_seconds": duration,
            "completed_at": datetime.now().isoformat(),
            "logs": results_store[job_id].get("logs", [])
        }


# ====================== ROUTES ======================
@app.post("/crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    try:
        parsed = urlparse(request.url)
        if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    job_id = str(uuid4())[:12]

    results_store[job_id] = {
        "status": "queued",
        "url": request.url,
        "mode": request.mode,
        "max_pages": request.max_pages,
        "created_at": datetime.now().isoformat(),
        "logs": []
    }

    background_tasks.add_task(
        execute_crawl_with_fallbacks,
        job_id, request.url, request.max_pages, request.mode,
        request.delay, request.same_domain, request.max_depth
    )

    return {
        "job_id": job_id,
        "status": "accepted",
        "message": "Crawl started successfully",
        "check_results": f"/results/{job_id}"
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
                "url": data.get("url", "")[:80],
                "found": data.get("total_found", 0),
                "created_at": data.get("created_at")
            }
            for jid, data in results_store.items()
        }
    }


@app.get("/")
async def root():
    return {
        "message": "🕷️ Ultimate Web Crawler v5.0 - Advanced Edition",
        "features": [
            "Smart link normalization & deduplication",
            "Depth control",
            "Advanced URL filtering",
            "Better fallback logic",
            "Improved static + browser modes"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
