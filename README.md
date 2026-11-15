# Smart Parking Management System

The FastAPI app accepts vehicle images, detects vehicles and license plates, assigns parking slots from model-generated layouts, and stores vehicle records in SQLite. The dashboard is served from the same app.

## Run on Windows

From the project folder, start the app with:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/>. Install dependencies in the existing virtual environment with `pip install -r requirements.txt` when setting it up.

## Data locations

- `database/smart_parking.db`: layouts, slots, and vehicle entry/exit records.
- `output/parking_layout/`: canonical `*_base_layout.jpg` images and generated `*_live_layout.jpg` images.
- `output/vehicle_uploads/`: uploaded vehicle images.
- `models/`: vehicle, plate, and parking-space model files.
- `legacy_streamlit/`: archived Streamlit code and old data; the FastAPI app does not use it.

## Project structure

```text
app/                   FastAPI application and routes
static/                HTML, CSS, and JavaScript dashboard
src/detection/         Vehicle, plate, and OCR modules
src/parking/           SQLite-backed parking service and allocation
models/                Existing model weights
database/              Runtime SQLite database
output/                Layout images and uploaded files
legacy_streamlit/      Archived Streamlit files and old data
```
