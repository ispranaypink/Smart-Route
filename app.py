import streamlit as st
from dotenv import load_dotenv
import os
import requests
import numpy as np

# --- Helpers ---
def geocode_address(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        results = resp.json().get("results")
        if results:
            location = results[0]["geometry"]["location"]
            return location["lat"], location["lng"]
    return None, None

def get_distance_matrix(coords, api_key):
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
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
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
    return None

def solve_tsp_nearest_neighbor_with_right_turn_penalty(coords, matrix, right_turn_penalty=500):  # penalty in meters
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

def get_coords_for_addresses(addresses, api_key):
    coords = []
    for addr in addresses:
        lat, lng = geocode_address(addr, api_key)
        if lat is not None and lng is not None:
            coords.append((lat, lng))
    return coords

def show_map(coords, order=None):
    if coords:
        markers_js = ""
        for lat, lng in coords:
            markers_js += f"L.marker([{lat}, {lng}]).addTo(map);\n"

        # Draw polyline for optimized route if order is provided
        polyline_js = ""
        if order and len(order) > 1:
            route_coords = [f"[{coords[i][0]}, {coords[i][1]}]" for i in order]
            polyline_js = (
                f"L.polyline([{', '.join(route_coords)}], "
                "{color: 'red', weight: 4, opacity: 0.7}).addTo(map);\n"
            )

        map_html = f"""
        <div id="map" style="height: 400px;"></div>
        <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
        <script>
        var map = L.map('map').setView([{coords[0][0]}, {coords[0][1]}], 12);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        {markers_js}
        {polyline_js}
        </script>
        """
        st.components.v1.html(map_html, height=400)
    else:
        st.info("Map will be displayed here after you add addresses.")

import math

def calculate_angle(p1, p2, p3):
    # p1, p2, p3 are (lat, lng)
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

def get_route_directions(coords, order, api_key):
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
        resp = requests.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data["status"] == "OK":
                steps = data["routes"][0]["legs"][0]["steps"]
                for step in steps:
                    # Remove HTML tags from instructions
                    import re
                    instruction = re.sub('<[^<]+?>', '', step["html_instructions"])
                    directions.append(f"{instruction} ({step['distance']['text']}, {step['duration']['text']})")
    return directions

# --- Main App ---
def main():
    load_dotenv()
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

    st.title("Smart Route for Walmart")

    st.header("Enter Addresses")
    address = st.text_input("Enter address")
    if 'addresses' not in st.session_state:
        st.session_state['addresses'] = []

    if st.button("Add Address"):
        if address:
            st.session_state['addresses'].append(address)
            st.rerun()

    if st.session_state['addresses']:
        st.write("Addresses:")
        for i, addr in enumerate(st.session_state['addresses'], 1):
            st.write(f"{i}. {addr}")

    coords = get_coords_for_addresses(st.session_state['addresses'], GOOGLE_API_KEY)

    # Calculate order before showing the map
    order = None
    if coords and len(coords) > 1:
        matrix = get_distance_matrix(coords, GOOGLE_API_KEY)
        if matrix is not None:
            order = solve_tsp_nearest_neighbor_with_right_turn_penalty(coords, matrix, right_turn_penalty=500)  # Adjust penalty as needed

    st.header("Route Map")
    show_map(coords, order)

    st.header("Route Details")
    if coords and len(coords) > 1 and order is not None:
        total_distance = sum(matrix[order[i]][order[i+1]] for i in range(len(order)-1))
        st.write("**Original Order:**")
        for i, idx in enumerate(range(len(coords)), 1):
            st.write(f"{i}. {st.session_state['addresses'][idx]}")
        st.write("**Optimized Order (Nearest Neighbor):**")
        for i, idx in enumerate(order, 1):
            st.write(f"{i}. {st.session_state['addresses'][idx]}")
        st.write(f"**Total Distance:** {total_distance/1000:.2f} km")
    elif coords and len(coords) > 1:
        st.warning("Could not retrieve distance matrix from Google API.")
    else:
        st.info("Add at least two addresses to optimize the route.")

        st.header("Step-by-Step Directions")
    directions = get_route_directions(coords, order, GOOGLE_API_KEY)
    if directions:
        for i, step in enumerate(directions, 1):
            st.write(f"{i}. {step}")
    else:
        st.info("Directions will appear here after route optimization.")

if __name__ == "__main__":
    main()