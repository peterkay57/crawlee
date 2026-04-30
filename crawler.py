import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

def crawl_website(start_url, max_pages=10):
    """Simple working crawler that follows links"""
    
    visited = set()
    queue = [start_url]
    results = []
    
    while queue and len(results) < max_pages:
        url = queue.pop(0)
        
        if url in visited:
            continue
        
        visited.add(url)
        
        try:
            print(f"Crawling ({len(results)+1}/{max_pages}): {url}")
            
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Get title
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else "No title"
            
            # Save result
            results.append({
                'url': url,
                'title': title_text
            })
            
            # Find links to crawl next
            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href'])
                # Only stay on same website
                if urlparse(full_url).netloc == urlparse(start_url).netloc:
                    if full_url not in visited and full_url not in queue:
                        queue.append(full_url)
            
            time.sleep(0.5)  # Be nice to the server
            
        except Exception as e:
            print(f"Error: {e}")
            continue
    
    return results
