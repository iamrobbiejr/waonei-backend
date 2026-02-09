# Waonei - Crowdsourced Traffic Violation Detection Platform

Waonei is a web-based platform that allows citizens to capture and report traffic violations. The system uses an **AI-driven backend** to automatically verify reports and filter out false positives before forwarding valid data to authorities.

## 🏗️ Tech Stack & Architecture

This project is built using a modern, scalable architecture designed to handle high-concurrency uploads while performing heavy AI processing asynchronously.

### **Frontend (The User Interface)**

  * **React + Vite:** For a fast, responsive mobile-first web application.
  * **JavaScript:** Standard ES6+ JavaScript.
  * **Tailwind CSS:** For utility-first styling.

### **Backend (The Logic)**

  * **FastAPI (Python):** A high-performance web framework for building APIs with Python 3.6+.
  * **Celery:** A distributed task queue to handle background AI processing without blocking the user interface.

### **Infrastructure & Database**

  * **Supabase:** An open-source Firebase alternative. We use it for:
      * **PostgreSQL:** Storing report metadata and status.
      * **PostGIS:** Handling geolocation data (mapping hotspots).
      * **Storage:** Storing the uploaded images and video evidence.
  * **Upstash (Redis):** A serverless Redis database used as the message broker for Celery. It manages the queue of uploaded videos waiting to be processed by the AI.

### **AI Core**

  * **YOLOv8 (Ultralytics):** State-of-the-art object detection model used to identify vehicles, lane violations, and other traffic infractions.

-----

## 🚀 Getting Started

### Prerequisites

  * **Node.js** (v18+) & **npm**
  * **Python** (v3.9+)
  * **Supabase Account:** Create a project and get your URL and Service Role Key.
  * **Upstash Account:** Create a Redis database and get your Connection URL.

### 1\. Database Setup (Supabase)

Run the following SQL in your Supabase SQL Editor to create the reports table:

```sql
create table reports (
  id uuid default gen_random_uuid() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  file_url text not null,
  status text default 'pending_analysis', -- pending_analysis, verified, rejected
  violation_type text default 'unknown',
  confidence_score float default 0.0,
  latitude float,
  longitude float
);

-- Enable storage bucket
insert into storage.buckets (id, name) values ('evidence-uploads', 'evidence-uploads');
-- Note: Ensure you set RLS policies to allow public inserts if needed for the PoC.
```

### 2\. Backend Setup

Navigate to the backend directory.

1.  **Create a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the `waonei-backend` folder:

    ```ini
    # Supabase Secrets
    SUPABASE_URL="https://your-project-id.supabase.co"
    SUPABASE_KEY="your-service-role-key"

    # Upstash Redis URL (Ensure it starts with rediss:// for secure connection)
    # Get this from the Upstash Console -> Connect -> Python (copy the URL part)
    REDIS_URL="rediss://default:yourpassword@your-endpoint.upstash.io:6379"
    ```

### 3\. Frontend Setup

Navigate to the frontend directory.

1.  **Install dependencies:**
    ```bash
    cd waonei-web
    npm install
    ```

-----

## 🏃‍♂️ How to Run

To run the full system, you need **three** separate terminal windows running simultaneously.

**Terminal 1: The API Server**
Start the FastAPI server to accept user uploads.

```bash
# Inside waonei-backend/
uvicorn app.main:app --reload
# Server running at http://localhost:8000
```

**Terminal 2: The AI Worker**
Start the Celery worker to listen to Upstash and process the queue.

```bash
# Inside waonei-backend/
celery -A app.worker.celery_app worker --loglevel=info
```

**Terminal 3: The Frontend**
Start the React development server.

```bash
# Inside waonei-web/
npm run dev
# Frontend running at http://localhost:5173
```

-----

## 📂 Project Structure

```text
/
├── waonei-backend/         # Python API & Worker
│   ├── app/
│   │   ├── main.py         # FastAPI Endpoints
│   │   ├── worker.py       # Celery Config (Upstash connection)
│   │   └── tasks.py        # AI/YOLO Logic
│   ├── requirements.txt
│   └── .env
│
└── waonei-web/             # React Frontend
    ├── src/
    │   ├── components/
    │   │   └── ReportUpload.jsx
    │   └── App.jsx
    ├── package.json
    └── tailwind.config.js
```