
```python
import asyncio
from crawlee.crawlers import PlaywrightCrawler
from crawlee.storages import Dataset

async def run_crawler(target_url: str):
    """Run crawler and return extracted data"""
    
    results = []
    
    crawler = PlaywrightCrawler(
        max_requests_per_crawl=20,
        headless=True,
    )
    
    @crawler.router.default_handler
    async def request_handler(context):
        context.log.info(f'Processing {context.request.url}')
        
        # Wait for page to load
        await context.page.wait_for_load_state('networkidle')
        
        # Extract data
        data = {
            'url': context.request.url,
            'title': await context.page.title(),
            'content': await context.page.evaluate('''
                () => {
                    const main = document.querySelector('main, article, .content, body');
                    return main ? main.innerText.slice(0, 1000) : '';
                }
            '''),
            'timestamp': str(asyncio.get_event_loop().time())
        }
        
        results.append(data)
        
        # Save to dataset
        dataset = await Dataset.open()
        await dataset.push_data(data)
        
        # Find and queue more links
        await context.enqueue_links()
    
    # Run the crawler
    await crawler.run([target_url])
    
    return results
```
