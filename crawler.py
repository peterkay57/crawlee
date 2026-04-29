import asyncio
from crawlee.crawlers import PlaywrightCrawler
from crawlee.storages import Dataset

async def run_crawler(target_url: str):
    results = []
    crawler = PlaywrightCrawler(max_requests_per_crawl=20, headless=True)
    
    @crawler.router.default_handler
    async def request_handler(context):
        await context.page.wait_for_load_state('networkidle')
        data = {
            'url': context.request.url,
            'title': await context.page.title(),
            'timestamp': str(asyncio.get_event_loop().time())
        }
        results.append(data)
        dataset = await Dataset.open()
        await dataset.push_data(data)
        await context.enqueue_links()
    
    await crawler.run([target_url])
    return results
