# Smart-Route: Sustainable Delivery Optimization
A route optimization tool designed specifically for India's left-hand traffic system, reducing delivery times, fuel costs, and carbon emissions by minimizing inefficient right turns.

In left-hand drive countries like India:
Left turns = Free flow (no traffic wait)
Right turns = Idling at intersections → Wastes fuel, increases delivery time, and adds unnecessary pollution

Smart-Route solves this by algorithmically avoiding right turns wherever possible.

### How to use:
- Add addresses (In any order)
- Get optimized route (minimizing time and distance)

#### Try it out: [Smart-Route](https://smart-route-for-walmart.streamlit.app/)

### Features:
- Right-Turn Penalty System: Automatically favors left-turn routes, reducing idling time at intersections.
- Traffic-Aware Routing: Uses real-time traffic data to avoid congested right-turn intersections.

### Still working on:
- Fuel & Emission Reports: Estimates fuel savings and CO₂ reduction per optimized route.
- Navigation: (currently giving directions)
- Better algorithms for the TSP problem
