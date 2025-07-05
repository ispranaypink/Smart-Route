import requests

API_KEY = "AIzaSyAc89Dp1Njs1ROy05tfConahro6IAUFRv4"
address = "New York, NY"
url = "https://maps.googleapis.com/maps/api/geocode/json"
params = {"address": address, "key": API_KEY}
resp = requests.get(url, params=params)
print(resp.json())