
from fastapi.openapi.utils import get_openapi
from app.main import app

def check_docs():
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    print("OpenAPI Schema generated successfully.")
    print(f"Title: {openapi_schema['info']['title']}")
    print(f"Tags found: {[tag['name'] for tag in openapi_schema.get('tags', [])]}")

if __name__ == "__main__":
    check_docs()
