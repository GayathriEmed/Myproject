import asyncio
import csv
import os
import redis
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, render_template
import aiofiles
from pymongo import MongoClient

app = Flask(__name__)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['search_queries']
collection = db['queries']

# Asynchronous function to read XML file and save each node as a separate key in Redis
async def read_xml(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        for main_term in root.iter('mainTerm'):
            title = main_term.find('title').text if main_term.find('title') is not None else ''
            for cell in main_term.findall('cell'):
                col_value = cell.text
                if col_value:
                    key = f"{file_path}_{col_value}"
                    value = f"{title} - {col_value}"
                    redis_client.set(key, value)
        return True
    except Exception as e:
        return {'error': str(e)}

# Asynchronous function to read CSV file and perform text searching
async def read_csv(file_path, search_query):
    try:
        async with aiofiles.open(file_path, mode='r', encoding='latin-1') as csvfile:
            reader = csv.DictReader(await csvfile.readlines())
            data = {}
            for row in reader:
                map_target = row.get('mapTarget', '')
                referenced_component_name = row.get('referencedComponentName', '')
                if search_query in map_target or search_query in referenced_component_name:
                    if file_path not in data:
                        data[file_path] = []
                    data[file_path].append((map_target, referenced_component_name))
            return data
    except Exception as e:
        return {'error': str(e)}

# Asynchronous function to read text file and perform text searching
async def read_text(file_path, search_query):
    try:
        async with aiofiles.open(file_path, 'r') as file:
            data = await file.readlines()
            filtered_data = [line.strip() for line in data if search_query in line]
            return filtered_data
    except Exception as e:
        return {'error': str(e)}

# Asynchronous function to search Redis for given query in XML keys
async def search_redis(search_query, xml_files):
    result = {xml_file: [] for xml_file in xml_files}
    try:
        keys = redis_client.keys()  # Get all keys stored in Redis
        for key in keys:
            value = redis_client.get(key)
            if search_query in value:
                for xml_file in xml_files:
                    if xml_file in key:
                        result[xml_file].append(value)
    except Exception as e:
        print(f"Error occurred while searching in Redis: {e}")
    return result

# API endpoint to read files and perform text searching within CSV, text, and XML files
@app.route('/read_files', methods=['POST'])
async def read_files():
    search_query = request.json['search_query']
    if len(search_query) < 3:
        return jsonify({'error': 'Search query must be at least 3 characters long'})

    # Save search query to MongoDB
    collection.insert_one({'search_query': search_query})

    # Get all CSV, text, and XML files in the current directory
    csv_files = [file for file in os.listdir() if file.endswith('.csv')]
    txt_files = [file for file in os.listdir() if file.endswith('.txt')]
    xml_files = [
        'icd10cm_drug_2023.xml',
        'icd10cm_eindex_2023.xml',
        'icd10cm_index_2023.xml',
        'icd10cm_neoplasm_2023.xml',
        'icd10cm_tabular_2023.xml'
    ]

    # Dictionary to store results
    result = {}

    # Iterate over CSV files and search for the query
    for csv_file in csv_files:
        data = await read_csv(csv_file, search_query)
        if data:
            result.update(data)

    # Iterate over text files and search for the query
    for txt_file in txt_files:
        data = await read_text(txt_file, search_query)
        if data:
            result[txt_file] = data

    # Iterate over XML files and read each file
    for xml_file in xml_files:
        await read_xml(xml_file)

    # Search Redis for the given query in XML files
    search_result = await search_redis(search_query, xml_files)
    result.update(search_result)

    return jsonify(result)

# Render redis_search.html template
@app.route('/')
def index():
    return render_template('redis_search.html')

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.run(debug=True))
