from flask import Flask, request, jsonify, render_template
from crawler import crawl_and_scrape
from uuid import uuid4
import asyncio

app = Flask(__name__)
results_store = {}

@app.route('/')
def home():
    return {
        'message': 'Universal Crawler + Scraper API',
        'endpoints': {
            '/web': 'GET - Beautiful web interface',
            '/health': 'GET - Health check',
            '/crawl': 'POST - Start crawl (max 100 pages)',
            '/results/<id>': 'GET - Get results'
        }
    }

@app.route('/web')
def web_interface():
    return render_template('index.html')

@app.route('/health')
def health():
    return {'status': 'alive'}

@app.route('/crawl', methods=['POST'])
def start_crawl():
    data = request.get_json()
    url = data.get('url')
    max_pages = data.get('max_pages', 50)
    
    if not url:
        return jsonify({'error': 'url required'}), 400
    
    # Limit to 100 pages
    if max_pages > 100:
        max_pages = 100
    
    job_id = str(uuid4())[:8]
    
    # Run async crawler
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(crawl_and_scrape(url, max_pages))
    
    results_store[job_id] = {
        'status': 'completed',
        'start_url': url,
        'total_pages': len(results),
        'results': results
    }
    
    return jsonify({
        'job_id': job_id,
        'message': f'Crawled and scraped {len(results)} pages',
        'check_url': f'/results/{job_id}'
    })

@app.route('/results/<job_id>')
def get_results(job_id):
    if job_id not in results_store:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(results_store[job_id])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
