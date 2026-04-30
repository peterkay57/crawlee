from flask import Flask, request, jsonify
from crawler import crawl_website
from uuid import uuid4

app = Flask(__name__)

# Store results
results_store = {}

@app.route('/')
def home():
    return {
        'message': 'Simple Crawler API',
        'endpoints': {
            '/health': 'GET - Health check',
            '/crawl': 'POST - Start crawl',
            '/results/<id>': 'GET - Get results'
        }
    }

@app.route('/health')
def health():
    return {'status': 'alive'}

@app.route('/crawl', methods=['POST'])
def start_crawl():
    data = request.get_json()
    url = data.get('url')
    max_pages = data.get('max_pages', 10)
    
    if not url:
        return jsonify({'error': 'url required'}), 400
    
    job_id = str(uuid4())[:8]
    
    # Run crawl
    results = crawl_website(url, max_pages)
    
    results_store[job_id] = {
        'status': 'completed',
        'start_url': url,
        'total_pages': len(results),
        'results': results
    }
    
    return jsonify({
        'job_id': job_id,
        'message': f'Crawled {len(results)} pages',
        'check_url': f'/results/{job_id}'
    })

@app.route('/results/<job_id>')
def get_results(job_id):
    if job_id not in results_store:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(results_store[job_id])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
