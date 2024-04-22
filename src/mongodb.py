import asyncio
import redis
import chardet
from aiohttp import web
from pymongo import MongoClient

# Initialize Redis connection
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Initialize MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['search_queries']
collection = db['queries']

async def save_data_to_redis():
    # Iterate over each file and save its data to Redis
    files = [
        "Alternate-Terms-2023.xlsx",
        "icd10cm_drug_2023.xml",
        "icd10cm_eindex_2023.xml",
        "icd10cm_index_2023.xml",
        "icd10cm_neoplasm_2023.xml",
        "icd10cm_order_2023.txt",
        "icd10cm_tabular_2023.xml"
    ]
    for file in files:
        # Read file content and detect encoding
        with open(file, 'rb') as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)['encoding']
        # Decode content with detected encoding
        with open(file, 'r', encoding=encoding, errors='ignore') as f:
            content = f.read()
        # Save content to Redis as a separate collection
        redis_client.set(file, content)


async def search_files(request):
    data = await request.json()
    search_query = data.get('search_query', '')

    # Save search query to MongoDB
    collection.insert_one({'search_query': search_query})

    # Perform text search on Redis collections
    search_results = {}
    files = [
        "Alternate-Terms-2023.xlsx",
        "icd10cm_drug_2023.xml",
        "icd10cm_eindex_2023.xml",
        "icd10cm_index_2023.xml",
        "icd10cm_neoplasm_2023.xml",
        "icd10cm_order_2023.txt",
        "icd10cm_tabular_2023.xml"
    ]
    for file in files:
        content = redis_client.get(file).decode('utf-8')
        if search_query in content:
            search_results[file] = "Match found"
        else:
            search_results[file] = "No match found"

    return web.json_response(search_results)

async def index(request):
    with open("templates/redis_search.html", "r") as f:
        html_content = f.read()
    return web.Response(text=html_content, content_type="text/html")

async def main():
    # Save data to Redis
    await save_data_to_redis()

    # Create web application and routes
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_post('/read_files', search_files)

    # Run web application
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    print("Web server started at http://localhost:8080")

    # Keep the event loop running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
