# -------------------------
# CONFIGURATION CONSTANTS
# -------------------------

POPULATION_MIN_THRESHOLD = 100_000
POPULATION_PAGINATION_MIN = 1_000_000
POPULATION_PAGINATION_MAX = 5_000_000
POPULATION_GRID_SEARCH_MIN = 5_000_001

SEARCH_RADIUS_METERS = 5000
GRID_STEP_DEGREES = 0.045  # Approx ~5km

MAX_RESULTS_PER_CITY = 60
ENABLE_DEDUPLICATION = True

ENABLE_LOGGING = True
LOG_FILE_PATH = "logs/skipped_cities.log"
SAVE_RESULTS_TO_JSON = True
RESULTS_JSON_DIR = "json_results/"

ENABLE_TEST_MODE = False
TEST_CITY_LIMIT = 5

CITY_DATA_FILE_PATH = "us_all_cities_sample.xlsx"  # Configurable path to Excel input

# -------------------------
# IMPORTS AND SETUP
# -------------------------

import os
import time
import json
import requests
import pandas as pd
from tqdm import tqdm

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY not set in environment variables")

# -------------------------
# DATA LOAD AND INITIALIZATION
# -------------------------

os.makedirs("images", exist_ok=True)
os.makedirs("logs", exist_ok=True)
os.makedirs(RESULTS_JSON_DIR, exist_ok=True)

seen_place_ids = set()
results = []

# Load city data
city_df = pd.read_excel(CITY_DATA_FILE_PATH)
if ENABLE_TEST_MODE:
    city_df = city_df.head(TEST_CITY_LIMIT)
us_places = city_df.to_dict(orient="records")

# -------------------------
# HELPER FUNCTIONS
# -------------------------

def log_skip(place, reason):
    if ENABLE_LOGGING:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{place['city']}, {place['state']} — {reason}\n")

def save_raw_json(city_name, data):
    if SAVE_RESULTS_TO_JSON:
        file_path = os.path.join(RESULTS_JSON_DIR, f"{city_name.replace(' ', '_')}.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

def search_places(location, radius, api_key, page_token=None):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": "ramen",
        "location": location,
        "radius": radius,
        "key": api_key
    }
    if page_token:
        params["pagetoken"] = page_token
    return requests.get(url, params=params).json()

def get_place_details(place_id, api_key):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,rating,geometry,website,url",
        "key": api_key
    }
    return requests.get(url, params=params).json()

def get_street_view_url(lat, lng, api_key, size="600x300"):
    return f"https://maps.googleapis.com/maps/api/streetview?size={size}&location={lat},{lng}&key={api_key}"

def fetch_with_pagination(location):
    all_results = []
    response = search_places(location, SEARCH_RADIUS_METERS, API_KEY)
    all_results.extend(response.get("results", []))
    token = response.get("next_page_token")

    for _ in range(2):
        if not token:
            break
        time.sleep(2)
        paged_response = search_places(location, SEARCH_RADIUS_METERS, API_KEY, page_token=token)
        all_results.extend(paged_response.get("results", []))
        token = paged_response.get("next_page_token")

    return all_results, response.get("error_message")

def generate_grid(center_lat, center_lng):
    offsets = [-GRID_STEP_DEGREES, 0, GRID_STEP_DEGREES]
    return [(center_lat + dx, center_lng + dy) for dx in offsets for dy in offsets]

def fetch_grid(place):
    all_results = []
    for lat, lng in generate_grid(place["lat"], place["lng"]):
        location = f"{lat},{lng}"
        response = search_places(location, SEARCH_RADIUS_METERS, API_KEY)
        all_results.extend(response.get("results", []))
        time.sleep(2)
    return all_results

# -------------------------
# MAIN EXECUTION LOOP
# -------------------------

for place in tqdm(us_places, desc="Processing cities"):
    pop = place.get("population", 0)
    if pop < POPULATION_MIN_THRESHOLD:
        log_skip(place, "Population below threshold")
        continue

    location = f"{place['lat']},{place['lng']}"

    if POPULATION_PAGINATION_MIN <= pop <= POPULATION_PAGINATION_MAX:
        raw_results, error = fetch_with_pagination(location)
    elif pop >= POPULATION_GRID_SEARCH_MIN:
        raw_results = fetch_grid(place)
        error = None
    else:
        response = search_places(location, SEARCH_RADIUS_METERS, API_KEY)
        raw_results = response.get("results", [])
        error = response.get("error_message")

    if error:
        log_skip(place, f"API error: {error}")
        continue

    if not raw_results:
        log_skip(place, "No results returned")
        continue

    save_raw_json(place["city"], raw_results)

    for result in raw_results:
        place_id = result.get("place_id")
        if ENABLE_DEDUPLICATION and place_id in seen_place_ids:
            continue
        seen_place_ids.add(place_id)

        details = get_place_details(place_id, API_KEY).get("result", {})
        lat = details.get("geometry", {}).get("location", {}).get("lat")
        lng = details.get("geometry", {}).get("location", {}).get("lng")

        results.append({
            "City": place["city"],
            "State": place["state"],
            "Zip": place.get("zipcode", ""),
            "Name": details.get("name"),
            "Address": details.get("formatted_address"),
            "Phone": details.get("formatted_phone_number"),
            "Rating": details.get("rating"),
            "Latitude": lat,
            "Longitude": lng,
            "Website": details.get("website"),
            "Maps URL": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
            "Street View URL": get_street_view_url(lat, lng, API_KEY),
        })

        if len(results) >= MAX_RESULTS_PER_CITY:
            break

# -------------------------
# SAVE FINAL OUTPUT
# -------------------------

output_df = pd.DataFrame(results)
script_dir = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(script_dir, "ramen_shops_usa.xlsx")
output_df.to_excel(excel_path, index=False)
print(f"Excel file saved at: {excel_path}")
