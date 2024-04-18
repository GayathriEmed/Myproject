import pandas as pd
import xml.etree.ElementTree as ET
import json
import asyncio
import aiofiles
import redis
import pymongo
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Connect to MongoDB
mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["your_database_name"]
search_collection = mongo_db["search_history"]

# Function to save search text to MongoDB
async def save_to_mongodb(search_query):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, search_collection.insert_one, {"search_query": search_query})
        return "Data saved in MongoDB successfully."
    except Exception as e:
        return f"Error saving to MongoDB: {e}"


# Function to read XML files asynchronously
async def read_xml(file_path, search_query):
    cached_result = await asyncio.get_event_loop().run_in_executor(None, redis_client.get, search_query)
    if cached_result:
        return json.loads(cached_result)

    tree = ET.parse(file_path)
    root = tree.getroot()
    data = []

    # Function to recursively extract text content from XML elements
    def extract_text(element):
        text = element.text or ''
        for child in element:
            text += extract_text(child)
        return text

    # Traverse through XML tree and check for search query in text content
    for child in root:
        text = extract_text(child)
        if search_query in text:
            data.append(text)

    await asyncio.get_event_loop().run_in_executor(None, redis_client.setex, search_query, 3600, json.dumps(data))

    return data

# Function to read Excel file asynchronously
async def read_excel(file_path, search_query):
    try:
        df = pd.read_excel(file_path)
        # Search for the query in all columns and rows
        mask = df.apply(lambda x: x.astype(str).str.contains(search_query, case=False)).any(axis=1)
        data = df[mask].to_dict(orient='records')
        return data
    except Exception as e:
        return {'error': str(e)}

# Function to read text file asynchronously
async def read_text(file_path, search_query):
    try:
        async with aiofiles.open(file_path, 'r') as file:
            data = await file.readlines()
            filtered_data = [line.strip() for line in data if search_query in line]
            return filtered_data
    except Exception as e:
        return {'error': str(e)}

# API endpoint to read files
@app.route('/read_files', methods=['POST'])
async def read_files():
    search_query = request.json['search_query']
    if len(search_query) < 3:
        return jsonify({'error': 'Search query must be at least 3 characters long'})

    # Save search text to MongoDB
    save_msg = await save_to_mongodb(search_query)
    print(save_msg)  # Print the save message to console

    data = {}

    # Call read_xml function with search_query
    xml_files = [
        'icd10cm_drug_2023.xml',
        'icd10cm_eindex_2023.xml',
        'icd10cm_index_2023.xml',
        'icd10cm_neoplasm_2023.xml',
        'icd10cm_tabular_2023.xml'
    ]
    for xml_file in xml_files:
        data[xml_file] = await read_xml(xml_file, search_query)

    data['Alternate-Terms-2023.xlsx'] = await read_excel('Alternate-Terms-2023.xlsx', search_query)
    data['icd10cm_order_2023.txt'] = await read_text('icd10cm_order_2023.txt', search_query)

    return jsonify(data)

# Accessing data from MongoDB
async def get_search_history():
    try:
        search_history = []
        cursor = search_collection.find({})
        async for document in cursor:
            search_history.append(document['search_query'])
        return search_history
    except Exception as e:
        return f"Error retrieving search history from MongoDB: {e}"


# Render redis_search.html template
@app.route('/')
def index():
    return render_template('redis_search.html')


# API endpoint to get search history from MongoDB
@app.route('/search_history', methods=['GET'])
async def get_search_history_endpoint():
    search_history = await get_search_history()
    return jsonify({'search_history': search_history})

if __name__ == '__main__':
    app.run(debug=True)