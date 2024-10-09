from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import random
import csv
import json
import logging
from pydantic import BaseModel
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

logger.info("Starting API initialization")

# Load product codes
try:
    with open('product_codes.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        PRODUCT_CODES = [row[0] for row in reader]
    logger.info(f"Loaded {len(PRODUCT_CODES)} product codes")
except Exception as e:
    logger.error(f"Error loading product codes: {str(e)}")
    PRODUCT_CODES = []

# Load product graph
try:
    with open('productGraph.json', 'r') as f:
        PRODUCT_GRAPH = json.load(f)
        # Ensure PRODUCT_GRAPH is a dictionary
        if isinstance(PRODUCT_GRAPH, list):
            PRODUCT_GRAPH = {str(item['product_code']): item for item in PRODUCT_GRAPH}
        logger.info(f"Loaded product graph with {len(PRODUCT_GRAPH)} items")
except Exception as e:
    logger.error(f"Error loading product graph: {str(e)}")
    PRODUCT_GRAPH = {}

# Define generic clusters
GENERIC_CLUSTERS = [
    "Outdoor Adventure", "Water Sports", "Team Sports", "Fitness Equipment",
    "Winter Sports", "Cycling", "Running", "Camping", "Hiking", "Yoga",
    "Martial Arts", "Racquet Sports", "Golf", "Climbing", "Fishing",
    "Skateboarding", "Surfing", "Swimming", "Athletics", "Gym Workout"
]
logger.info(f"Defined {len(GENERIC_CLUSTERS)} generic clusters")

class SearchSample(BaseModel):
    product_codes: List[str]
    clusters: List[str]
    associations: Dict[str, List[str]]

def generate_sample():
    # Sample 20-50 unique product codes
    num_products = random.randint(20, 50)
    sampled_product_codes = random.sample(PRODUCT_CODES, num_products)
    logger.info(f"Sampled {len(sampled_product_codes)} unique product codes")

    # Sample 5 unique clusters
    sampled_clusters = random.sample(GENERIC_CLUSTERS, 5)
    logger.info(f"Sampled clusters: {sampled_clusters}")

    # Generate random associations
    associations = {}
    for cluster in sampled_clusters:
        num_associated = min(random.randint(3, 10), len(sampled_product_codes))
        associations[cluster] = random.sample(sampled_product_codes, num_associated)
    logger.info(f"Generated associations for {len(associations)} clusters")

    return SearchSample(
        product_codes=sampled_product_codes,
        clusters=sampled_clusters,
        associations=associations
    )

async def get_search_sample():
    if not hasattr(app.state, 'current_sample'):
        app.state.current_sample = generate_sample()
    return app.state.current_sample

async def stream_cluster_names(clusters):
    logger.info("Starting to stream cluster names")
    for cluster in clusters:
        logger.debug(f"Streaming cluster: {cluster}")
        yield f"{cluster}\n"
        await asyncio.sleep(0.1)  # Simulate some delay
    logger.info("Finished streaming cluster names")

async def stream_products(product_codes):
    logger.info("Starting to stream products")
    for product_code in product_codes:
        product_info = PRODUCT_GRAPH.get(str(product_code), {})
        product_name = product_info.get('product_name', f"Product {product_code}")
        price = product_info.get('price', 'N/A')
        review_score = product_info.get('review_score', 'None')
        image_sign_kit = product_info.get('image_sign_kit', '')
        sport = product_info.get('sport', 'N/A')
        brand = product_info.get('brand', 'N/A')
        logger.info(f"Streaming product: {product_name} ({product_code})")
        yield f"{product_name}|{product_code}|{price}|{review_score}|{image_sign_kit}|{sport}|{brand}\n"
        await asyncio.sleep(0.1)  # Simulate some delay
    logger.info("Finished streaming products")

async def stream_associations(associations):
    logger.info("Starting to stream associations")
    for cluster, products in associations.items():
        logger.debug(f"Streaming association for cluster: {cluster}")
        yield f"{cluster}: {','.join(products)}\n"
        await asyncio.sleep(0.1)  # Simulate some delay
    logger.info("Finished streaming associations")

@app.get("/clusters")
async def get_clusters(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for clusters (streaming)")
    return StreamingResponse(stream_cluster_names(sample.clusters), media_type="text/plain")

@app.get("/products")
async def get_products(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for products (streaming)")
    return StreamingResponse(stream_products(sample.product_codes), media_type="text/plain")

@app.get("/associations")
async def get_associations(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for associations (streaming)")
    return StreamingResponse(stream_associations(sample.associations), media_type="text/plain")

@app.get("/clusters_non_streaming")
async def get_clusters_non_streaming(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for clusters (non-streaming)")
    return JSONResponse(content=sample.clusters)

@app.get("/products_non_streaming")
async def get_products_non_streaming(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for products (non-streaming)")
    products = []
    for product_code in sample.product_codes:
        product_info = PRODUCT_GRAPH.get(str(product_code), {})
        products.append({
            "name": product_info.get('product_name', f"Product {product_code}"),
            "id": product_code,
            "price": product_info.get('price', 'N/A'),
            "review_score": product_info.get('review_score', 'None'),
            "image_sign_kit": product_info.get('image_sign_kit', ''),
            "sport": product_info.get('sport', 'N/A'),
            "brand": product_info.get('brand', 'N/A')
        })
    logger.info(f"Returning {len(products)} products")
    return JSONResponse(content=products)

@app.get("/associations_non_streaming")
async def get_associations_non_streaming(sample: SearchSample = Depends(get_search_sample)):
    logger.info("Received request for associations (non-streaming)")
    return JSONResponse(content=sample.associations)

@app.post("/new_search")
async def new_search():
    app.state.current_sample = generate_sample()
    return {"message": "New search sample generated"}

@app.on_event("startup")
async def startup_event():
    logger.info("API is starting up")
    app.state.current_sample = generate_sample()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("API is shutting down")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server")
    uvicorn.run(app, host="0.0.0.0", port=8066)