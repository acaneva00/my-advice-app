import uvicorn
import os

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", 3001))
    
    # Run the FastAPI server
    uvicorn.run("backend.api:app", host="0.0.0.0", port=port, reload=True)
