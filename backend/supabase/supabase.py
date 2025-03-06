import os
from dotenv import load_dotenv
import httpx

load_dotenv()

# Get Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

class SupabaseClient:
    def __init__(self, url=SUPABASE_URL, key=SUPABASE_KEY):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(
            base_url=url,
            headers=self.headers,
            timeout=30.0
        )
    
    async def query(self, endpoint, method="GET", data=None, params=None):
        if method == "GET":
            response = await self.client.get(endpoint, params=params)
        elif method == "POST":
            response = await self.client.post(endpoint, json=data)
        elif method == "PUT":
            response = await self.client.put(endpoint, json=data)
        elif method == "DELETE":
            response = await self.client.delete(endpoint, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        await self.client.aclose()

# Create a singleton instance
supabase = SupabaseClient()