"""
HTTP Server for Upwork Job Scraper API
Provides GET endpoint to search for jobs with query and limit parameters
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from main import main, logger
from utils.settings import config

# Initialize FastAPI app
app = FastAPI(
    title="Upwork Job Scraper API",
    description="API для поиска вакансий на Upwork",
    version="1.0.0"
)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Upwork Job Scraper API",
        "endpoints": {
            "/search": "GET /search?query=<search_text>&limit=<number>"
        }
    }


@app.get("/search")
async def search_jobs(
    query: str = Query(..., description="Search query text for jobs"),
    limit: int = Query(10, ge=1, le=100, description="Number of jobs to return (1-100)")
):
    """
    Search for jobs on Upwork
    
    :param query: Search query text
    :param limit: Number of jobs to return (1-100, default: 10)
    :return: JSON response with job results
    """
    try:
        logger.info(f"🔍 Received search request: query='{query}', limit={limit}")
        
        # Load credentials from config.toml
        credentials = {
            'username': config.get('Credentials', {}).get('username') if isinstance(config, dict) else None,
            'password': config.get('Credentials', {}).get('password') if isinstance(config, dict) else None
        }
        
        # Load default search parameters from config
        default_search = config.get('Search', {}) if isinstance(config, dict) else {}
        
        # Build input data for main() function
        # Override query and limit with request parameters
        input_data = {
            'credentials': credentials,
            'search': {
                **default_search,  # Keep all default search parameters
                'query': query,    # Override with request query
                'limit': limit     # Override with request limit
            },
            'general': {
                'save_csv': False  # Don't save CSV for API requests
            }
        }
        
        logger.info(f"🚀 Starting job scraping...")
        
        # Call main() function
        job_results = await main(input_data)
        
        logger.info(f"✅ Found {len(job_results)} jobs")
        
        # Return results as JSON
        return JSONResponse(content={
            "success": True,
            "query": query,
            "limit": limit,
            "count": len(job_results),
            "jobs": job_results
        })
        
    except Exception as e:
        logger.error(f"❌ Error during job search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error searching for jobs: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

