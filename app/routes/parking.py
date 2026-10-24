from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from src.parking.draw_parking_layout import draw_parking_layout
from src.parking.parking_reconciliation import (
    ParkingError,
    get_category,
    initialize_layouts,
    reconcile_layout,
)
from src.parking.parking_service import MAX_UPLOAD_BYTES, process_vehicle_image
from src.parking import vehicle_database


router = APIRouter(prefix="/api")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@router.on_event("startup")
def initialize_model_layouts():
    reports = initialize_layouts()
    for report in reports:
        print(
            f"{report['category']}: {report['slots_detected']} slots across "
            f"{report['rows_found']} rows; row groups={report['rows']}"
        )
        draw_parking_layout(report["category"])


def error_response(error):
    return JSONResponse(
        status_code=error.status_code,
        content={
            "ok": False,
            "error": {"code": error.code, "message": str(error)},
            "data": error.data,
        },
    )


@router.post("/process-vehicle")
async def process_vehicle(file: UploadFile = File(...)):
    filename = file.filename or ""
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        return error_response(
            ParkingError("invalid_upload", "Upload a JPG, JPEG, or PNG image.", 415)
        )

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if not contents:
        return error_response(ParkingError("invalid_upload", "The uploaded file is empty.", 400))
    if len(contents) > MAX_UPLOAD_BYTES:
        return error_response(
            ParkingError("invalid_upload", "The uploaded image exceeds the 10 MB limit.", 413)
        )

    try:
        result = process_vehicle_image(contents, filename)
        return {"ok": True, "error": None, "data": result}
    except ParkingError as error:
        return error_response(error)


@router.get("/layouts/{vehicle_type}")
def get_layout_status(vehicle_type: str):
    try:
        category = get_category(vehicle_type)
        result = reconcile_layout(vehicle_type)
        return {
            "ok": True,
            "error": None,
            "data": {
                "vehicle_type": vehicle_type.lower(),
                "category": category,
                "selected_layout": result["layout"],
                "occupancy": result["occupancy"],
                "counts": {
                    "total": result["occupancy"]["total"],
                    "empty": result["occupancy"]["empty"],
                    "occupied": result["occupancy"]["occupied"],
                },
                "generation": result["generation"],
            },
        }
    except ParkingError as error:
        return error_response(error)


@router.get("/vehicles")
def get_vehicle_records():
    try:
        records = vehicle_database.load_database().to_dict(orient="records")
        return {"ok": True, "error": None, "data": {"records": records}}
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": {"code": "record_error", "message": "Vehicle records could not be loaded."},
                "data": None,
            },
        )


@router.get("/layouts/{vehicle_type}/slots")
def get_layout_slots(vehicle_type: str):
    try:
        category = get_category(vehicle_type)
        result = reconcile_layout(vehicle_type)
        slots = []
        for _, source in result["slots"].iterrows():
            slots.append(
                {
                    "slot": str(source.get("slot", "")),
                    "row": str(source.get("row", "")),
                    "column": int(source.get("column", 0)),
                    "status": str(source.get("status", "")),
                    "x1": float(source.get("x1", 0)),
                    "y1": float(source.get("y1", 0)),
                    "x2": float(source.get("x2", 0)),
                    "y2": float(source.get("y2", 0)),
                }
            )
        return {
            "ok": True,
            "error": None,
            "data": {
                "vehicle_type": vehicle_type.lower(),
                "category": category,
                "selected_layout": result["layout"],
                "counts": {
                    "total": result["occupancy"]["total"],
                    "empty": result["occupancy"]["empty"],
                    "occupied": result["occupancy"]["occupied"],
                },
                "occupancy": result["occupancy"],
                "slots": slots,
            },
        }
    except ParkingError as error:
        return error_response(error)


@router.get("/summary")
def get_summary():
    try:
        records = vehicle_database.load_database()
        statuses = records["status"].astype(str).str.casefold() if not records.empty else []
        inside = records[statuses == "inside"] if not records.empty else records
        exited_count = int((statuses == "exited").sum()) if not records.empty else 0
        vehicles_inside = {"cars": 0, "buses": 0, "motorcycles": 0}
        for vehicle_type in inside.get("vehicle_type", []):
            category = get_category(str(vehicle_type))
            if category == "car":
                vehicles_inside["cars"] += 1
            elif category == "bus":
                vehicles_inside["buses"] += 1
            elif category == "motorcycle":
                vehicles_inside["motorcycles"] += 1

        counts = {"total": 0, "empty": 0, "occupied": 0}
        for vehicle_type in ("car", "bus", "motorcycle"):
            result = reconcile_layout(vehicle_type)
            occupancy = result["occupancy"]
            counts["total"] += int(occupancy["total"])
            counts["occupied"] += int(occupancy["occupied"])
            counts["empty"] += int(occupancy["empty"])

        occupancy_percent = (
            round(100 * counts["occupied"] / counts["total"], 1)
            if counts["total"]
            else 0.0
        )
        return {
            "ok": True,
            "error": None,
            "data": {
                **counts,
                "occupancy_percent": occupancy_percent,
                "total_slots": counts["total"],
                "usable_empty": counts["empty"],
                "vehicles_inside": vehicles_inside,
                "vehicle_totals": {
                    "entries": int(len(records)),
                    "exits": exited_count,
                    "inside": int(len(inside)),
                },
            },
        }
    except ParkingError as error:
        return error_response(error)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": {"code": "summary_error", "message": "Parking summary could not be loaded."},
                "data": None,
            },
        )
