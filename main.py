from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Tuple, Optional
import requests
import numpy as np
import math
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Smart Route API", description="Route optimization API for deliveries")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Streamlit app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class Address(BaseModel):
    address: str

class GeocodeResponse(BaseModel):
    latitude: float
    longitude: float
    formatted_address: str

class RouteRequest(BaseModel):
    addresses: List[str]

class RouteResponse(BaseModel):
    coordinates: List[Tuple[float, float]]
    optimized_order: List[int]
    total_distance_km: float
    original_addresses: List[str]
    optimized_addresses: List[str]

class DirectionsResponse(BaseModel):
    directions: List[str]

# Helper functions
def geocode_address(address: str, api_key: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Geocode an address using Google Maps API"""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        
        results = resp.json().get("results")
        if results:
            location = results[0]["geometry"]["location"]
            formatted_address = results[0]["formatted_address"]
            return location["lat"], location["lng"], formatted_address
    except requests.RequestException as e:
        print(f"Geocoding error: {e}")
    
    return None, None, None

def get_distance_matrix(coords: List[Tuple[float, float]], api_key: str) -> Optional[np.ndarray]:
    """Get distance matrix using Google Maps API"""
    if not coords:
        return None
    
    origins = "|".join([f"{lat},{lng}" for lat, lng in coords])
    destinations = origins
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origins,
        "destinations": destinations,
        "key": api_key,
        "mode": "driving"
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        
        data = resp.json()
        n = len(coords)
        matrix = np.zeros((n, n))
        
        for i, row in enumerate(data["rows"]):
            for j, element in enumerate(row["elements"]):
                if element["status"] == "OK":
                    matrix[i][j] = element["distance"]["value"]
                else:
                    matrix[i][j] = np.inf
        
        return matrix
    except requests.RequestException as e:
        print(f"Distance matrix error: {e}")
    
    return None

def calculate_angle(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]) -> float:
    """Calculate angle between three points"""
    def to_vec(a, b):
        return (b[0] - a[0], b[1] - a[1])
    
    v1 = to_vec(p2, p1)
    v2 = to_vec(p2, p3)
    angle1 = math.atan2(v1[1], v1[0])
    angle2 = math.atan2(v2[1], v2[0])
    angle = math.degrees(angle2 - angle1)
    
    # Normalize angle to [-180, 180]
    while angle <= -180:
        angle += 360
    while angle > 180:
        angle -= 360
    
    return angle

def solve_tsp_nearest_neighbor_with_right_turn_penalty(
    coords: List[Tuple[float, float]], 
    matrix: np.ndarray, 
    right_turn_penalty: float = 500
) -> List[int]:
    """Solve TSP using nearest neighbor with right turn penalty"""
    n = len(matrix)
    unvisited = set(range(1, n))
    order = [0]
    current = 0
    prev = None
    
    while unvisited:
        min_cost = float('inf')
        next_city = None
        
        for city in unvisited:
            cost = matrix[current][city]
            
            # If this is not the first move, check for right turn
            if prev is not None:
                angle = calculate_angle(coords[prev], coords[current], coords[city])
                if -135 < angle < -45:  # Right turn
                    cost += right_turn_penalty
            
            if cost < min_cost:
                min_cost = cost
                next_city = city
        
        order.append(next_city)
        unvisited.remove(next_city)
        prev = current
        current = next_city
    
    return order

def get_route_directions(coords: List[Tuple[float, float]], order: List[int], api_key: str) -> List[str]:
    """Get step-by-step directions for the route"""
    if not order or len(order) < 2:
        return []
    
    directions = []
    
    for i in range(len(order) - 1):
        origin = f"{coords[order[i]][0]},{coords[order[i]][1]}"
        destination = f"{coords[order[i+1]][0]},{coords[order[i+1]][1]}"
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": origin,
            "destination": destination,
            "key": api_key,
            "mode": "driving"
        }
        
        try:
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            
            data = resp.json()
            if data["status"] == "OK":
                steps = data["routes"][0]["legs"][0]["steps"]
                for step in steps:
                    # Remove HTML tags from instructions
                    instruction = re.sub('<[^<]+?>', '', step["html_instructions"])
                    directions.append(f"{instruction} ({step['distance']['text']}, {step['duration']['text']})")
        except requests.RequestException as e:
            print(f"Directions error: {e}")
    
    return directions

# API endpoints
@app.get("/")
async def root():
    return {"message": "Smart Route API is running"}

@app.post("/geocode", response_model=GeocodeResponse)
async def geocode(address: Address):
    """Geocode a single address"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    lat, lng, formatted_address = geocode_address(address.address, api_key)
    
    if lat is None or lng is None:
        raise HTTPException(status_code=404, detail="Address not found")
    
    return GeocodeResponse(
        latitude=lat,
        longitude=lng,
        formatted_address=formatted_address or address.address
    )

@app.post("/optimize-route", response_model=RouteResponse)
async def optimize_route(request: RouteRequest):
    """Optimize route for given addresses"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    if len(request.addresses) < 2:
        raise HTTPException(status_code=400, detail="At least 2 addresses are required")
    
    # Geocode all addresses
    coords = []
    valid_addresses = []
    
    for addr in request.addresses:
        lat, lng, formatted_addr = geocode_address(addr, api_key)
        if lat is not None and lng is not None:
            coords.append((lat, lng))
            valid_addresses.append(formatted_addr or addr)
    
    if len(coords) < 2:
        raise HTTPException(status_code=400, detail="Could not geocode enough addresses")
    
    # Get distance matrix
    matrix = get_distance_matrix(coords, api_key)
    if matrix is None:
        raise HTTPException(status_code=500, detail="Could not retrieve distance matrix")
    
    # Optimize route
    order = solve_tsp_nearest_neighbor_with_right_turn_penalty(coords, matrix)
    
    # Calculate total distance
    total_distance = sum(matrix[order[i]][order[i+1]] for i in range(len(order)-1))
    
    # Prepare optimized addresses
    optimized_addresses = [valid_addresses[i] for i in order]
    
    return RouteResponse(
        coordinates=coords,
        optimized_order=order,
        total_distance_km=round(total_distance / 1000, 2),
        original_addresses=valid_addresses,
        optimized_addresses=optimized_addresses
    )

@app.post("/get-directions", response_model=DirectionsResponse)
async def get_directions(request: RouteRequest):
    """Get step-by-step directions for optimized route"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Google API key not configured")
    
    # First optimize the route
    route_response = await optimize_route(request)
    
    # Get directions
    directions = get_route_directions(
        route_response.coordinates, 
        route_response.optimized_order, 
        api_key
    )
    
    return DirectionsResponse(directions=directions)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running correctly"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)