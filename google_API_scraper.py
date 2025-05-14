import requests, time, os, csv, pandas as pd
from tqdm import tqdm

API_KEY = os.getenv("GOOGLE_API_KEY") # Ensure you have set your Google API key in your environment variables

if not API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY not set in environment variables")

# -------------------------
# CONFIGURATION CONSTANTS
# -------------------------

# Population thresholds
POPULATION_MIN_THRESHOLD = 100_000         # Skip cities below this
POPULATION_PAGINATION_MIN = 1_000_000      # Enable 3-page search for cities in this range
POPULATION_PAGINATION_MAX = 5_000_000
POPULATION_GRID_SEARCH_MIN = 5_000_001     # Use grid search for cities above this

# Google Places search config
SEARCH_RADIUS_METERS = 5000                # Max 50,000; API max is 50km
GRID_STEP_DEGREES = 0.045                  # ~5 km resolution (smaller = finer grid)

# Deduplication & result control
MAX_RESULTS_PER_CITY = 60                  # Cap total results stored per city
ENABLE_DEDUPLICATION = True                # Track and skip repeated place_ids

# Logging and debugging
ENABLE_LOGGING = True                      # Save skipped or error cities to log file
LOG_FILE_PATH = "logs/skipped_cities.log"
SAVE_RESULTS_TO_JSON = True                # Optional: Save raw results per city
RESULTS_JSON_DIR = "json_results/"

# Testing and limits
ENABLE_TEST_MODE = False                   # Set to True to limit execution for test runs
TEST_CITY_LIMIT = 5                        # Number of cities to run in test mode

# -------------------------

# Load US city/town coordinates from Excel
df = pd.read_excel("us_all_cities_sample.xlsx")

# Convert to list of dicts for use in API loop
us_places = df.to_dict(orient='records')

# Function to handle API requests with retries
def safe_get(url, params):
    for attempt in range(3):
        try:
            return requests.get(url, params=params, timeout=10).json()
        except requests.exceptions.RequestException as e:
            print(f"API error: {e}. Retrying ({attempt + 1}/3)...")
            time.sleep(2)
    return {}

# Function to safely get JSON data from the API
def safe_get_json(url, params):
    for attempt in range(3):
        try:
            return requests.get(url, params=params, timeout=10).json()
        except requests.exceptions.RequestException as e:
            print(f"API error: {e}. Retrying ({attempt + 1}/3)...")
            time.sleep(2)
    return {}

# Function to search for places
def search_places(location, radius, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": "ramen",
        "location": location,
        "radius": radius,
        "key": api_key
    }
    return requests.get(url, params=params).json()

# Function to get place details
def get_place_details(place_id, api_key):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,rating,geometry,website,url",
        "key": api_key
    }
    return safe_get_json(url, params=params).json()

# Function to generate a Street View image URL
def get_street_view_url(lat, lng, api_key, size="600x300"):
    return f"https://maps.googleapis.com/maps/api/streetview?size={size}&location={lat},{lng}&key={api_key}"

# Loop through each city/town and search for ramen places
results = []

for place in tqdm(us_places, desc="Searching locations"):
    location = f"{place['lat']},{place['lng']}"
    print(f"Searching in: {place['city']}, {place['state']} {place['zipcode']}")
    response = search_places(location, 5000, API_KEY)
    
    if "error_message" in response:
        print(f"API error for {place['city']}, {place['state']}: {response['error_message']}")
        time.sleep(10)
        continue

    for result in response.get("results", []):
        place_id = result.get("place_id")
        details = get_place_details(place_id, API_KEY).get("result", {})
        name = details.get("name")
        address = details.get("formatted_address")
        phone = details.get("formatted_phone_number")
        rating = details.get("rating")
        lat = details.get("geometry", {}).get("location", {}).get("lat")
        lng = details.get("geometry", {}).get("location", {}).get("lng")
        website = details.get("website")
        street_view_url = get_street_view_url(lat, lng, API_KEY)
        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

        results.append({
            "City": place["city"],
            "Name": name,
            "Address": address,
            "State": place["state"],
            "Zip": place.get("zipcode", ""),
            "Country": "USA",
            "Phone": phone,
            "Rating": rating,
            "Latitude": lat,
            "Longitude": lng,
            "Website": website,
            "Maps URL": maps_url,
            "Street View URL": street_view_url,
            
        })
        time.sleep(2)  # Avoid hitting rate limits

# Finalize file path
script_dir = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(script_dir, "ramen_shops_usa.xlsx")

# Save to Excel
results_df = pd.DataFrame(results)
results_df.to_excel(excel_path, index=False)

print(f"Excel file saved at: {excel_path}")