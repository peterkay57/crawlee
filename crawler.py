import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re

def crawl_and_scrape(start_url, max_pages=50):
    """
    Crawls websites AND scrapes meaningful data from each page.
    - Finds links (crawling)
    - Extracts titles, prices, descriptions, images (scraping)
    """
    
    visited = set()
    queue = [start_url]
    results = []
    
    # Common patterns for scraping different types of websites
    def extract_product_data(soup, url):
        """Extract product/e-commerce data"""
        data = {}
        
        # Title (universal)
        title_tag = soup.find('title')
        data['title'] = title_tag.get_text(strip=True) if title_tag else "No title"
        
        # Price - try multiple common patterns
        price_selectors = [
            '.price', '.product-price', '.a-price-whole', '.offers-price',
            '[data-testid="product-price"]', '.price__current', '.sale-price'
        ]
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                data['price'] = price_elem.get_text(strip=True)[:50]
                break
        if 'price' not in data:
            data['price'] = "N/A"
        
        # Description
        desc_selectors = [
            'meta[name="description"]', '.description', '.product-description',
            '[data-testid="product-description"]', '#description'
        ]
        for selector in desc_selectors:
            if selector.startswith('meta'):
                desc_elem = soup.find('meta', {'name': 'description'})
                if desc_elem:
                    data['description'] = desc_elem.get('content', '')[:200]
                    break
            else:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    data['description'] = desc_elem.get_text(strip=True)[:200]
                    break
        if 'description' not in data:
            data['description'] = ""
        
        # Rating
        rating_selectors = [
            '.rating', '.review-score', '.a-icon-alt', '.star-rating',
            '[data-testid="rating"]'
        ]
        for selector in rating_selectors:
            rating_elem = soup.select_one(selector)
            if rating_elem:
                data['rating'] = rating_elem.get_text(strip=True)[:20]
                break
        if 'rating' not in data:
            data['rating'] = "N/A"
        
        # Images
        img_tags = soup.find_all('img', limit=3)
        data['images'] = []
        for img in img_tags:
            img_url = img.get('src') or img.get('data-src')
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                data['images'].append(img_url)
        
        return data
    
    def extract_instruction_data(soup, url):
        """Extract instruction/how-to data for device manuals"""
        data = {}
        
        # Title
        title_tag = soup.find('title')
        data['title'] = title_tag.get_text(strip=True) if title_tag else "No title"
        
        # Find all step-like elements
        steps = []
        step_selectors = [
            '.step', '.steps li', '.instruction-step', '.procedure li',
            '.how-to-step', 'ol li', '.numbered-list li'
        ]
        
        for selector in step_selectors:
            step_elements = soup.select(selector)
            if step_elements:
                for idx, elem in enumerate(step_elements[:20]):
                    step_text = elem.get_text(strip=True)
                    if len(step_text) > 10:  # Meaningful step
                        steps.append({
                            'step_number': idx + 1,
                            'instruction': step_text[:300]
                        })
                break
        
        data['steps'] = steps if steps else []
        
        # Extract all paragraphs (useful content)
        paragraphs = soup.find_all('p')
        data['content'] = [p.get_text(strip=True)[:500] for p in paragraphs[:10] if len(p.get_text(strip=True)) > 50]
        
        # Find images (screenshots)
        images = []
        for img in soup.find_all('img', limit=10):
            img_url = img.get('src') or img.get('data-src')
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                images.append(img_url)
        data['images'] = images[:5]
        
        return data
    
    def detect_page_type(url, soup):
        """Automatically detect if page is product page or instruction page"""
        url_lower = url.lower()
        
        # Product site indicators
        if any(x in url_lower for x in ['amazon', 'product', 'shop', 'buy', 'price']):
            return 'product'
        
        # Check for price in page
        if soup.find(class_=re.compile(r'price|Price|PRICE')):
            return 'product'
        
        # Instruction/manual indicators
        if any(x in url_lower for x in ['guide', 'manual', 'support', 'help', 'how-to', 'tutorial']):
            return 'instruction'
        
        # Check for step-by-step structure
        if soup.find(class_=re.compile(r'step|Step|STEP')):
            return 'instruction'
        
        return 'general'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
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
            
            # Detect page type and extract appropriate data
            page_type = detect_page_type(url, soup)
            
            if page_type == 'product':
                scraped_data = extract_product_data(soup, url)
                scraped_data['page_type'] = 'product'
            elif page_type == 'instruction':
                scraped_data = extract_instruction_data(soup, url)
                scraped_data['page_type'] = 'instruction'
            else:
                # General page: just get title and description
                title_tag = soup.find('title')
                scraped_data = {
                    'title': title_tag.get_text(strip=True) if title_tag else "No title",
                    'page_type': 'general',
                    'description': ''
                }
                desc_meta = soup.find('meta', {'name': 'description'})
                if desc_meta:
                    scraped_data['description'] = desc_meta.get('content', '')[:200]
            
            scraped_data['url'] = url
            results.append(scraped_data)
            
            # CRAWLING: Find more links to visit
            links_found = 0
            start_domain = urlparse(start_url).netloc
            
            for link in soup.find_all('a', href=True):
                if links_found >= 30:  # Limit per page
                    break
                    
                href = link['href'].strip()
                if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue
                
                full_url = urljoin(url, href)
                full_url = full_url.split('#')[0].split('?')[0]  # Remove fragments and query params
                
                # Stay on same domain (or related for Amazon)
                link_domain = urlparse(full_url).netloc
                if link_domain == start_domain or ('amazon' in link_domain and 'amazon' in start_domain):
                    if full_url not in visited and full_url not in queue:
                        queue.append(full_url)
                        links_found += 1
            
            if links_found > 0:
                print(f"  Found {links_found} new links. Queue size: {len(queue)}")
            
            # Be respectful to servers
            time.sleep(0.5)
            
        except requests.exceptions.Timeout:
            print(f"  Timeout: {url}")
            continue
        except Exception as e:
            print(f"  Error: {str(e)[:100]}")
            continue
    
    print(f"\n✅ Crawl complete! Processed {len(results)} pages")
    return results
