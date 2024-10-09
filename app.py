import streamlit as st
import aiohttp
import asyncio
from streamlit_lottie import st_lottie
import requests
import time
import json
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Set page config
st.set_page_config(page_title="Decathlon AI Gear Explorer", layout="wide", initial_sidebar_state="expanded")

# Custom CSS (unchanged)
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

:root {
    --decathlon-blue: #0082C3;
    --decathlon-dark-blue: #005C8F;
    --background-color: #F8FAFC;
    --text-color: #1E293B;
    --card-background: #FFFFFF;
}

.stApp {
    font-family: 'Inter', sans-serif;
    color: var(--text-color);
    background-color: var(--background-color);
}

.main .block-container {
    padding-top: 2rem;
    max-width: 1000px;
}

h1, h2, h3, h4, h5, h6 {
    font-weight: 600;
    color: var(--decathlon-dark-blue);
}

.subtitle {
    font-size: 1.1em;
    color: #64748B;
    margin-bottom: 2rem;
}

.search-container {
    background-color: var(--card-background);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    margin-bottom: 2rem;
}

.search-container .stTextInput {
    margin-bottom: 0;
}

.search-container .stTextInput > div > div {
    border: none;
    background-color: transparent;
}

.product-card {
    background-color: var(--card-background);
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.product-card img {
    width: 100%;
    height: 200px;
    object-fit: cover;
    border-radius: 4px;
    margin-bottom: 1rem;
}

.product-name {
    font-weight: 600;
    font-size: 1em;
    margin-bottom: 0.5rem;
    flex-grow: 1;
}

.product-price {
    color: var(--decathlon-blue);
    font-weight: 700;
    font-size: 1.1em;
}

.product-brand, .product-sport {
    font-size: 0.9em;
    color: #64748B;
    margin-bottom: 0.5rem;
}

.ai-badge {
    background-color: var(--decathlon-blue);
    color: white;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: 600;
    margin-left: 0.5rem;
}

/* Sidebar styles */
.sidebar .stRadio > div {
    flex-direction: column;
}

.sidebar .stRadio label {
    padding: 0.5rem;
    background-color: var(--card-background);
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    cursor: pointer;
    transition: all 0.3s ease;
}

.sidebar .stRadio label:hover {
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.sidebar .stRadio label[data-baseweb="radio"] > div::before {
    background-color: var(--decathlon-blue);
    border-color: var(--decathlon-blue);
}
</style>
"""

async def fetch_stream(session, url, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=f"HTTP Status {response.status}",
                        headers=response.headers,
                    )
                async for line in response.content:
                    yield line.decode().strip()
        except (aiohttp.ClientError, aiohttp.ClientPayloadError) as e:
            logger.error(f"Error in fetch_stream: {str(e)}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1)  # Wait before retrying

async def fetch_data(query):
    async with aiohttp.ClientSession() as session:
        try:
            # Call new_search endpoint to generate a new sample
            async with session.post("http://localhost:8066/new_search") as response:
                if response.status != 200:
                    raise Exception("Failed to start a new search")

            clusters_task = fetch_stream(session, "http://localhost:8066/clusters")
            products_task = fetch_stream(session, "http://localhost:8066/products")
            associations_task = fetch_stream(session, "http://localhost:8066/associations")

            clusters = []
            products = []
            associations = {}

            async for cluster in clusters_task:
                if cluster not in clusters:
                    clusters.append(cluster)
                    logger.debug(f"Received cluster: {cluster}")
                    yield {"type": "cluster", "data": cluster}

            async for product in products_task:
                product_dict = dict(zip(['name', 'id', 'price', 'review_score', 'image_sign_kit', 'sport', 'brand'], product.split('|')))
                if product_dict['id'] not in [p['id'] for p in products]:
                    products.append(product_dict)
                    logger.info(f"Received product: {product_dict}")
                    yield {"type": "product", "data": product_dict}

            async for association in associations_task:
                cluster, product_ids = association.split(': ')
                associations[cluster] = product_ids.split(',')
                logger.info(f"Received association: {cluster} - {product_ids}")
                yield {"type": "association", "data": {cluster: product_ids.split(',')}}

            yield {"type": "complete", "data": {
                "clusters": clusters,
                "products": products,
                "associations": associations
            }}
            logger.info("Data fetching complete")

        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            yield {"type": "error", "data": str(e)}

def  get_review_stars(review_score):
    if review_score is None or review_score == 'None':
        return "No reviews yet"
    
    try:
        score = float(review_score)
        return '⭐' * int(round(score))
    except ValueError:
        logger.warning(f"Invalid review score: {review_score}")
        return "Invalid review score"

def get_image_url(image_sign_kit):
    if not image_sign_kit or image_sign_kit == 'N/A':
        return "https://via.placeholder.com/600x600?text=No+Image"
    
    image_pixel_id = image_sign_kit if image_sign_kit.startswith("p") else f"p{image_sign_kit}"
    return f"https://contents.mediadecathlon.com/{image_pixel_id}/?format=png&quality=100&f=600x600"

@st.cache_data
def load_lottie_url(url: str):
    try:
        r = requests.get(url)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error(f"Error loading Lottie animation: {str(e)}")
        return None

def initialize_session_state():
    if 'clusters' not in st.session_state:
        st.session_state.clusters = []
    if 'products' not in st.session_state:
        st.session_state.products = []
    if 'associations' not in st.session_state:
        st.session_state.associations = {}
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'last_search_query' not in st.session_state:
        st.session_state.last_search_query = ""
    if 'debug_data' not in st.session_state:
        st.session_state.debug_data = {}
    if 'active_cluster' not in st.session_state:
        st.session_state.active_cluster = "All Products"

def debug_print_state():
    logger.debug("Current state:")
    logger.debug(f"Total products: {len(st.session_state.products)}")
    logger.debug(f"Clusters: {st.session_state.clusters}")
    logger.debug(f"Associations: {st.session_state.associations}")
    for product in st.session_state.products[:5]:  # Print first 5 products for debugging
        logger.debug(f"Product: {product}")

def filter_products(cluster):
    logger.debug(f"Filtering products for cluster: {cluster}")
    if not cluster or cluster == "All Products":
        logger.debug(f"Returning all products: {len(st.session_state.products)}")
        return st.session_state.products
    
    associated_product_ids = set(st.session_state.associations.get(cluster, []))
    logger.debug(f"Associated product IDs for {cluster}: {associated_product_ids}")
    
    filtered_products = [
        product for product in st.session_state.products
        if product['id'] in associated_product_ids
    ]
    logger.debug(f"Filtered products: {len(filtered_products)}")
    if len(filtered_products) == 0:
        logger.warning(f"No products found after filtering for cluster: {cluster}")
        logger.debug("Product IDs in main list vs. association:")
        for product in st.session_state.products[:10]:  # Check first 10 products
            logger.debug(f"Product ID: {product['id']}, In association: {product['id'] in associated_product_ids}")
    return filtered_products

async def perform_search(query):
    logger.info(f"Performing search for query: {query}")
    st.session_state.clusters = []
    st.session_state.products = []
    st.session_state.associations = {}
    st.session_state.active_cluster = "All Products"

    progress_bar = st.progress(0)
    status_text = st.empty()
    product_container = st.empty()

    async def stream_data():
        async for item in fetch_data(query):
            if item["type"] == "cluster":
                st.session_state.clusters.append(item["data"])
            elif item["type"] == "product":
                st.session_state.products.append(item["data"])
                display_products(st.session_state.products, product_container)
            elif item["type"] == "association":
                st.session_state.associations.update(item["data"])
            elif item["type"] == "complete":
                logger.debug("Data fetching complete. Final state:")
                debug_print_state()
            
            progress = min(100, int(len(st.session_state.products) / 20 * 100))  # Assuming max 20 products
            progress_bar.progress(progress)
            status_text.text(f"Loading... {progress}%")

        progress_bar.empty()
        status_text.empty()
        st.session_state.search_performed = True
        st.session_state.last_search_query = query
        logger.info(f"Search complete. Found {len(st.session_state.products)} products across {len(st.session_state.clusters)} categories.")
        st.success(f"Found {len(st.session_state.products)} products across {len(st.session_state.clusters)} categories.")

    await stream_data()

def display_products(products, container):
    logger.debug(f"Displaying {len(products)} products")
    container.empty()  # Clear the previous content
    with container:
        if products:
            st.subheader(f"Recommended Gear ({len(products)} items)")
            cols = st.columns(4)
            for i, product in enumerate(products):
                with cols[i % 4]:
                    with st.container():
                        st.image(get_image_url(product['image_sign_kit']), use_column_width=True)
                        st.markdown(f"**{product['name']}**")
                        st.write(f"Brand: {product['brand']}")
                        st.write(f"Sport: {product['sport']}")
                        st.write(get_review_stars(product['review_score']))
                        st.markdown(f"**${product['price']}**")
        else:
            st.info("No products found. Try adjusting your search or filters.")

def main():
    logger.info("Starting Decathlon Gear Explorer")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("Decathlon Gear Explorer")
    st.markdown('<span class="ai-badge">AI-Powered</span>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Discover the perfect outdoor equipment for your next adventure</p>', unsafe_allow_html=True)

    initialize_session_state()

    # Load Lottie animation
    lottie_url = "https://assets5.lottiefiles.com/packages/lf20_uwWgICKCxj.json"
    lottie_json = load_lottie_url(lottie_url)

    # Search input
    st.markdown('<div class="search-container">', unsafe_allow_html=True)
    col1, col2 = st.columns([6, 1])
    with col1:
        search_query = st.text_input("", placeholder="Describe your ideal outdoor activity or gear needs...", key="search_input")
    st.markdown('</div>', unsafe_allow_html=True)

    if search_query and search_query != st.session_state.last_search_query:
        asyncio.run(perform_search(search_query))

    if st.session_state.search_performed:
        debug_print_state()  # Add this line to print debug information

        # Sidebar for cluster selection and logs
        st.sidebar.title("Filter by Category")
        cluster_options = ["All Products"] + st.session_state.clusters
        selected_cluster = st.sidebar.radio("Select a category:", cluster_options, key="cluster_selector")

        if selected_cluster != st.session_state.active_cluster:
            st.session_state.active_cluster = selected_cluster

        filtered_products = filter_products(st.session_state.active_cluster)
        
        # Main content area for product display
        product_container = st.empty()
        display_products(filtered_products, product_container)

        # Log of product IDs and cluster associations
        st.sidebar.title("Product and Cluster Log")
        
        # Product IDs log
        st.sidebar.subheader("Retrieved Product IDs")
        product_ids = [product['id'] for product in st.session_state.products]
        st.sidebar.code("\n".join(product_ids))

        # Cluster associations log
        st.sidebar.subheader("Cluster Associations")
        for cluster, associated_products in st.session_state.associations.items():
            st.sidebar.write(f"**{cluster}**")
            st.sidebar.code("\n".join(associated_products))

    elif not st.session_state.search_performed:
        # Display Lottie animation when no search has been performed
        if lottie_json:
            st_lottie(lottie_json, height=300, key="lottie")
        st.markdown("<h3 style='text-align: center;'>Ready to find your perfect gear?</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Describe your outdoor activity or gear needs, and let our AI guide you to the best equipment.</p>", unsafe_allow_html=True)

    logger.info("Decathlon Gear Explorer UI rendering complete")

if __name__ == "__main__":
    main()