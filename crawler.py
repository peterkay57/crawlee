import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

async def crawl_and_scrape(start_url, max_pages=100):
    """
    Crawls ANY website (follows links to ANY domain) AND scrapes ALL data.
    """
    
    visited = set()
    queue = [start_url]
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        while queue and len(results) < max_pages:
            url = queue.pop(0)
            
            if url in visited:
                continue
            
            visited.add(url)
            
            try:
                print(f"[{len(results)+1}/{max_pages}] Processing: {url[:80]}...")
                
                # Go to page
                await page.goto(url, timeout=30000, wait_until='networkidle')
                await asyncio.sleep(2)  # Wait for dynamic content
                
                # Get HTML
                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # SCRAPE EVERYTHING
                # Title
                title = await page.title()
                
                # All text content
                text_content = await page.evaluate('() => document.body.innerText')
                
                # All links
                all_links = await page.evaluate('() => Array.from(document.querySelectorAll("a[href]")).map(a => a.href)')
                
                # All images
                all_images = await page.evaluate('() => Array.from(document.querySelectorAll("img")).map(img => img.src)')
                
                # Price (if exists)
                price = ""
                price_selectors = ['.price', '.product-price', '.a-price-whole', '[data-testid="product-price"]']
                for selector in price_selectors:
                    price_elem = await page.query_selector(selector)
                    if price_elem:
                        price = await price_elem.inner_text()
                        break
                
                # Description
                description = ""
                desc_meta = soup.find('meta', {'name': 'description'})
                if desc_meta:
                    description = desc_meta.get('content', '')
                
                # Headings
                headings = await page.evaluate('() => Array.from(document.querySelectorAll("h1, h2, h3")).map(h => ({level: h.tagName, text: h.innerText}))')
                
                # Prepare scraped data
                scraped_data = {
                    'url': url,
                    'title': title[:500] if title else "No title",
                    'text_content': text_content[:5000] if text_content else "",
                    'description': description[:500] if description else "",
                    'price': price[:100] if price else "",
                    'headings': headings[:20],
                    'links': all_links[:100],
                    'images': all_images[:50]
                }
                
                results.append(scraped_data)
                
                # CRAWL: Add ALL new links from this page
                new_links = 0
                for link in all_links[:100]:  # Max 100 links per page
                    if link and link.startswith('http'):
                        # Clean the URL
                        clean_link = link.split('#')[0].split('?')[0]
                        if clean_link not in visited and clean_link not in queue:
                            queue.append(clean_link)
                            new_links += 1
                
                print(f"  Found {new_links} new links. Queue size: {len(queue)}")
                
                # Be nice to servers
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"  Error: {str(e)[:100]}")
                continue
        
        await browser.close()
    
    print(f"\n✅ Complete! Crawled {len(results)} pages")
    return results
