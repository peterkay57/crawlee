import asyncio
from crawlee.crawlers import PlaywrightCrawler

async def run_crawler(target_url: str):
    results = []
    crawler = PlaywrightCrawler(max_requests_per_crawl=5, headless=True)
    
    @crawler.router.default_handler
    async def handler(context):
        await context.page.wait_for_load_state('networkidle')
        title = await context.page.title()
        results.append({"url": context.request.url, "title": title})
        await context.enqueue_links()
    
    await crawler.run([target_url])
    return results
