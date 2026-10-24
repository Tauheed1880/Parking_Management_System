# Smart Parking Management System

The FastAPI app detects vehicle and plate images, assigns an available parking slot, and stores entry and exit records. The original Streamlit app is also included.

## Run on Windows

Open PowerShell in the project folder:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/>. To run the optional Streamlit app, stop FastAPI and use:

```powershell
.\venv\Scripts\python.exe -m streamlit run app.py
```

## Model-driven parking layouts

Parking-space inference uses `models/parking_lot.pt` and the base images in `output/parking_layout/`. On first startup, the model detects spaces for car, bus, and motorcycle images. Detected boxes are deduplicated, grouped into rows, named by row and column, and saved in `database/smart_parking.db` with the image hash. The saved slot IDs and coordinates are reused after restart.

New vehicle records, layouts, and slots are stored in `database/smart_parking.db`. Annotated live images are written as `*_live_layout.jpg` beside the base images. Previous data is retained under `backup_old_data/` and is not used by the app.

Slots can be regenerated manually with `generate_parking_layout("car")`, `generate_parking_layout("bus")`, or `generate_parking_layout("motorcycle")` from `src.parking.parking_layout`. Regeneration is refused while that layout has active vehicle assignments.
