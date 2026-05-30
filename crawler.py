import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

def crawl_and_scrape(start_url, max_pages=50):
    """
    Simple crawler that works without Playwright.
    Uses requests + BeautifulSoup only.
    """
    
    visited = set()
    queue = [start_url]
    results = []
    start_domain = urlparse(start_url).netloc
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    while queue and len(results) < max_pages:
        url = queue.pop(0)
        
        if url in visited:
            continue
        
        visited.add(url)
        
        try:
            print(f"[{len(results)+1}/{max_pages}] Processing: {url[:80]}...")
            
            response = requests.get(url, timeout=30, headers=headers)
            
            if response.status_code != 200:
                print(f"  Failed: HTTP {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else "No title"
            
            # Extract all text
            text_content = soup.get_text(separator=' ', strip=True)
            
            # Extract all links
            all_links = []
            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href'])
                if full_url.startswith('http'):
                    all_links.append(full_url)
            
            # Extract all images
            all_images = []
            for img in soup.find_all('img', src=True):
                img_url = urljoin(url, img['src'])
                if img_url.startswith('http'):
                    all_images.append(img_url)
            
            # Prepare result
            scraped_data = {
                'url': url,
                'title': title[:500],
                'text_content': text_content[:5000],
                'links_count': len(all_links),
                'images_count': len(all_images)
            }
            
            results.append(scraped_data)
            
            # CRAWL: Add new links to queue
            new_links = 0
            for link in all_links[:50]:
                if link not in visited and link not in queue:
                    queue.append(link)
                    new_links += 1
            
            print(f"  Found {new_links} new links. Queue size: {len(queue)}")
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  Error: {str(e)[:100]}")
            continue
    
    print(f"\n✅ Complete! Processed {len(results)} pages")
    return results
