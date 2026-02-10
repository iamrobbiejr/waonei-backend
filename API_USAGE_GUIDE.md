# API Documentation Guide

WAONEI Backend uses **FastAPI**, which provides interactive API documentation automatically generated from the code using [Swagger UI](https://github.com/swagger-api/swagger-ui) and [ReDoc](https://github.com/Redocly/redoc).

## 🚀 Accessing the Documentation

Ensure your backend server is running:

```bash
uvicorn app.main:app --reload
```

Once the server is running (default port `8000`), you can access:

1.  **Swagger UI (Interactive):** [http://localhost:8000/docs](http://localhost:8000/docs)
2.  **ReDoc (Static/Clean):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
3.  **OpenAPI JSON:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

## 🛠 Using Swagger UI

The Swagger UI (`/docs`) allows you to interact directly with the API endpoints from your browser.

### 1. Browse Endpoints
Endpoints are grouped by tags (e.g., **Authentication**, **Reports**, **Admin**). Click on a group to expand it and see the available operations.

### 2. Make Requests ("Try it out")
To test an endpoint:
1.  Click on the endpoint to expand it.
2.  Click the **Try it out** button on the right.
3.  Fill in the parameters or request body.
    - For JSON bodies, an example value is pre-filled. You can edit this.
    - For File uploads, you will see a file picker.
4.  Click **Execute**.

The system will send the request and show you:
- **Curl command**: The equivalent command to run in a terminal.
- **Request URL**: The exact URL called.
- **Server Response**: Status code, body, and headers.

### 3. Authentication
Some endpoints (like admin operations) require authentication.
1.  Use the `POST /auth/login` endpoint to get an `access_token`.
2.  Copy the token string (without quotes).
3.  Scroll to the top of the page and click the green **Authorize** button.
4.  Type `Bearer <your_token>` in the value box (or just the token if the UI handles the prefix, but standard is `Bearer ` + token).
5.  Click **Authorize** and then **Close**.

Now your requests will automatically include the `Authorization` header.

## 📄 ReDoc
ReDoc (`/redoc`) offers a beautiful, three-column layout that is excellent for reading and understanding the API structure, models, and examples. It is less interactive than Swagger UI but better for reading as a manual.
