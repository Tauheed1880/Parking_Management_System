import os
import html
from datetime import datetime

import cv2
import numpy as np
import pandas as pd
import streamlit as st

# -----------------------------
# Detection Modules
# -----------------------------

from src.detection.vehicle_detection import detect_vehicle
from src.detection.plate_detection import detect_plate
from src.detection.ocr import read_plate

# -----------------------------
# Parking Modules
# -----------------------------

from src.parking.parking_allocation import (
    allocate_parking,
    free_slot
)

from src.parking.draw_parking_layout import draw_parking_layout

from src.parking.vehicle_database import (
    is_vehicle_inside,
    get_assigned_slot,
    assign_slot,
    update_exit_time,
    remove_slot,
    add_vehicle,
    get_vehicle
)

# -----------------------------
# PAGE CONFIGURATION
# -----------------------------

st.set_page_config(
    page_title="Smart Parking Management System",
    page_icon="\U0001f697",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------
# LOAD CSS
# -----------------------------

with open("assets/style.css") as css:
    st.markdown(
        f"<style>{css.read()}</style>",
        unsafe_allow_html=True
    )


# -----------------------------
# CONSTANT PATHS
# -----------------------------

PARKING_LAYOUT_CSV = "output/parking_layout/parking_layout.csv"

VEHICLE_DATABASE = "data/vehicles.csv"

OCR_RESULTS = "output/ocr_results/plate_results.csv"

PARKING_LAYOUT_IMAGE = "output/parking_layout/car_parking_layout.jpg"

VEHICLE_LAYOUT_MAP = {
    "car": "car",
    "motorcycle": "motorcycle",
    "bus": "bus",
    "truck": "bus",
}

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

# def load_parking_layout():

#     if os.path.exists(PARKING_LAYOUT_CSV):
#         return pd.read_csv(PARKING_LAYOUT_CSV)

#     return pd.DataFrame()
def load_parking_layout_for_type(vehicle_type):

    path = f"output/parking_layout/{vehicle_type}_parking_layout.csv"

    if not os.path.exists(path):
        return pd.DataFrame()

    parking_df = pd.read_csv(path)
    parking_df["vehicle_type"] = vehicle_type
    return parking_df


def load_parking_layout():

    dfs = [
        load_parking_layout_for_type(vehicle_type)
        for vehicle_type in ["car", "motorcycle", "bus"]
    ]
    dfs = [parking_df for parking_df in dfs if not parking_df.empty]

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def load_vehicle_database():

    if os.path.exists(VEHICLE_DATABASE):
        return pd.read_csv(VEHICLE_DATABASE, dtype=str).fillna("")

    return pd.DataFrame()


def load_ocr_results():

    if os.path.exists(OCR_RESULTS):
        return pd.read_csv(OCR_RESULTS)

    return pd.DataFrame()


# -----------------------------
# -----------------------------
# SESSION STATE
# -----------------------------

defaults = {
    "uploaded_image": None,
    "vehicle_type": None,
    "vehicle_detection": None,
    "vehicle_crop": None,
    "plate_detection": None,
    "plate_crop": None,
    "parking_layout": None,
    "assigned_slot": None,
    "ocr_record": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def parking_counts(parking_df):

    if parking_df.empty or "status" not in parking_df:
        return 0, 0, 0

    statuses = parking_df["status"].astype(str).str.lower()
    total = len(parking_df)
    occupied = int(statuses.eq("occupied").sum())
    available = int(statuses.eq("empty").sum())
    return total, occupied, available


def render_page_header(subtitle):

    now = datetime.now()
    st.markdown(
        f"""
<div class="dashboard-header">
  <div>
    <div class="dashboard-title">Smart Parking Management System</div>
    <div class="dashboard-subtitle">{subtitle}</div>
  </div>
  <div class="dashboard-right">
    <div class="status-online">Online</div>
    <div>{now.strftime("%d %B %Y")}</div>
    <div>{now.strftime("%I:%M:%S %p")}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def display_vehicle_table(records, columns):

    available_columns = [column for column in columns if column in records.columns]
    labels = {
        "plate_number": "Plate Number",
        "vehicle_type": "Vehicle Type",
        "assigned_slot": "Assigned Slot",
        "entry_time": "Entry Time",
        "exit_time": "Exit Time",
        "status": "Status",
    }
    st.dataframe(
        records[available_columns].rename(columns=labels),
        width="stretch",
        hide_index=True,
    )


def current_vehicle_type_counts(records):

    if records.empty or "status" not in records or "vehicle_type" not in records:
        return {"Cars": 0, "Buses": 0, "Motorcycles": 0}

    active = records[records["status"].astype(str).str.lower().eq("inside")]
    types = active["vehicle_type"].astype(str).str.lower().replace({"truck": "bus"})
    return {
        "Cars": int(types.eq("car").sum()),
        "Buses": int(types.eq("bus").sum()),
        "Motorcycles": int(types.eq("motorcycle").sum()),
    }


def sort_by_entry_time(records):

    if records.empty or "entry_time" not in records:
        return records

    sorted_records = records.copy()
    sorted_records["_entry_sort"] = pd.to_datetime(
        sorted_records["entry_time"], errors="coerce"
    )
    return sorted_records.sort_values(
        "_entry_sort", ascending=False, na_position="last"
    ).drop(columns="_entry_sort")


# -----------------------------
# SIDEBAR NAVIGATION
# -----------------------------

st.sidebar.markdown("## Smart Parking")
st.sidebar.caption("Management System")
active_page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Vehicle Detection",
        "Vehicle Records",
        "Parking Layout",
        "Parking History / Reports",
    ],
    label_visibility="collapsed",
)

parking_df = load_parking_layout()
vehicle_df = load_vehicle_database()
total_slots, occupied_slots, empty_slots = parking_counts(parking_df)
occupancy = occupied_slots / total_slots if total_slots else 0


# ==========================================================
# DASHBOARD
# ==========================================================

if active_page == "Dashboard":

    render_page_header("System overview")
    st.subheader("Parking Summary")

    metric_columns = st.columns(4)
    summary = [
        ("Total Slots", total_slots),
        ("Occupied Slots", occupied_slots),
        ("Available Slots", empty_slots),
        ("Occupancy", f"{occupancy * 100:.1f}%"),
    ]
    for column, (label, value) in zip(metric_columns, summary):
        column.metric(label, value)

    st.progress(occupancy)
    st.caption(f"{occupancy * 100:.1f}% of parking slots are occupied")
    st.divider()

    st.subheader("Vehicles Currently Inside")
    type_counts = current_vehicle_type_counts(vehicle_df)
    type_columns = st.columns(3)
    for column, (label, value) in zip(type_columns, type_counts.items()):
        column.metric(label, value)

    st.divider()
    st.subheader("Recent Activity")
    if not vehicle_df.empty:
        recent_records = sort_by_entry_time(vehicle_df).head(8)
        display_vehicle_table(
            recent_records,
            ["plate_number", "vehicle_type", "assigned_slot", "entry_time", "status"],
        )
    else:
        st.info("No parking activity is available yet.")


# ==========================================================
# VEHICLE DETECTION
# ==========================================================

elif active_page == "Vehicle Detection":

    render_page_header("Vehicle image processing")
    st.subheader("Upload Vehicle Image")
    st.caption("Supported formats: JPG, JPEG, PNG")

    uploaded_file = st.file_uploader(
        "Vehicle image",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key="vehicle_image_upload",
    )

    uploaded_image = None
    if uploaded_file is not None:
        uploaded_image = cv2.imdecode(
            np.frombuffer(uploaded_file.getbuffer(), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )

    process_button = st.button(
        "Process Vehicle",
        type="primary",
        width="stretch",
    )

    # Keep the existing detection, OCR, record, entry/exit, and slot pipeline.
    if process_button:

        if uploaded_image is None:
            st.warning("Please upload an image.")

        else:

            with st.spinner("Processing vehicle..."):

                st.session_state["uploaded_image"] = uploaded_image.copy()

                vehicle_detection_image, vehicle_images, vehicle_type = detect_vehicle(
                    uploaded_image,
                    uploaded_file.name,
                )

                if len(vehicle_type) > 0:
                    st.session_state["vehicle_type"] = vehicle_type[0]

                st.session_state["vehicle_detection"] = vehicle_detection_image

                if len(vehicle_images) > 0:
                    st.session_state["vehicle_crop"] = vehicle_images

                plate_detection_images, plate_images = detect_plate(vehicle_images)

                if len(plate_detection_images) > 0:
                    st.session_state["plate_detection"] = plate_detection_images

                if len(plate_images) > 0:
                    st.session_state["plate_crop"] = plate_images[0]

                _, ocr_records = read_plate(plate_images)

                if len(ocr_records) > 0:
                    st.session_state["ocr_record"] = ocr_records[0]

                plate_number = ""
                if len(ocr_records) > 0:
                    plate_number = ocr_records[0]["plate_number"]

                layout_vehicle_type = "car"
                if plate_number != "":

                    if is_vehicle_inside(plate_number):

                        vehicle_record = get_vehicle(plate_number)
                        layout_vehicle_type = VEHICLE_LAYOUT_MAP.get(
                            vehicle_record["vehicle_type"], "car"
                        )

                        assigned_slot = get_assigned_slot(plate_number)
                        if assigned_slot:
                            free_slot(assigned_slot, layout_vehicle_type)

                        update_exit_time(plate_number)
                        st.session_state["assigned_slot"] = assigned_slot

                    else:

                        add_vehicle(plate_number, st.session_state["vehicle_type"])
                        layout_vehicle_type = VEHICLE_LAYOUT_MAP.get(
                            st.session_state["vehicle_type"], "car"
                        )
                        assigned_slot = allocate_parking(layout_vehicle_type)

                        if assigned_slot is None:
                            st.error("Parking is full.")
                            st.stop()

                        assign_slot(plate_number, assigned_slot)
                        st.session_state["assigned_slot"] = assigned_slot

                    updated_layout = draw_parking_layout(layout_vehicle_type)
                    st.session_state["parking_layout"] = updated_layout

        st.success("Vehicle processed successfully.")
        st.rerun()

    st.divider()
    st.subheader("Detection Results")
    image_columns = st.columns(2)
    with image_columns[0]:
        st.markdown("**Original Vehicle Image**")
        if st.session_state["uploaded_image"] is not None:
            st.image(
                st.session_state["uploaded_image"],
                channels="BGR",
                width="stretch",
            )
        else:
            st.info("The uploaded image will appear here after processing.")

    with image_columns[1]:
        st.markdown("**Detected Vehicle Image**")
        if st.session_state["vehicle_detection"]:
            st.image(
                st.session_state["vehicle_detection"],
                width="stretch",
            )
        else:
            st.info("Vehicle detection result will appear here.")

    detected_type = st.session_state["vehicle_type"] or "Not available"
    st.metric("Detected Vehicle Type", detected_type)

    plate_columns = st.columns(2)
    with plate_columns[0]:
        st.markdown("**Detected License Plate**")
        plate_detections = st.session_state["plate_detection"]
        if plate_detections:
            st.image(plate_detections[0], width="stretch")
        else:
            st.info("License plate detection result will appear here.")

    with plate_columns[1]:
        st.markdown("**Plate Crop**")
        if st.session_state["plate_crop"]:
            st.image(st.session_state["plate_crop"], width="stretch")
        else:
            st.info("Plate crop will appear here.")

    ocr = st.session_state["ocr_record"]
    ocr_columns = st.columns(2)
    ocr_columns[0].metric(
        "Plate Number",
        ocr.get("plate_number", "Not available") if ocr else "Not available",
    )
    confidence = ocr.get("confidence") if ocr else None
    ocr_columns[1].metric(
        "OCR Confidence",
        f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "Not available",
    )

    st.divider()
    st.subheader("Vehicle Information")
    plate_number = ocr.get("plate_number", "") if ocr else ""
    if plate_number and not vehicle_df.empty and "plate_number" in vehicle_df:
        matching_vehicle = vehicle_df[
            vehicle_df["plate_number"].astype(str).eq(str(plate_number))
        ]
    else:
        matching_vehicle = pd.DataFrame()

    if not matching_vehicle.empty:
        vehicle = matching_vehicle.iloc[-1]
        info_values = [
            ("Plate Number", vehicle.get("plate_number", "")),
            ("Vehicle Type", vehicle.get("vehicle_type", "")),
            ("Vehicle Status", vehicle.get("status", "")),
            ("Entry Time", vehicle.get("entry_time", "")),
            ("Assigned Slot", vehicle.get("assigned_slot", "")),
            ("Exit Time", vehicle.get("exit_time", "")),
        ]
    else:
        info_values = [
            ("Plate Number", plate_number or "Not available"),
            ("Vehicle Type", detected_type),
            (
                "Vehicle Status",
                ocr.get("status", "Not available") if ocr else "Not available",
            ),
            ("Entry Time", "Not available"),
            (
                "Assigned Slot",
                st.session_state["assigned_slot"] or "Not available",
            ),
            ("Exit Time", "Not available"),
        ]

    for column, (label, value) in zip(st.columns(3), info_values[:3]):
        column.metric(label, value or "—")
    for column, (label, value) in zip(st.columns(3), info_values[3:]):
        column.metric(label, value or "—")
    if confidence is not None:
        st.caption(f"OCR confidence: {confidence:.2f}")


# ==========================================================
# VEHICLE RECORDS
# ==========================================================

elif active_page == "Vehicle Records":

    render_page_header("Current and previous vehicle records")
    st.subheader("Vehicle Records")

    if vehicle_df.empty:
        st.info("No vehicle records found.")
    else:
        filtered_records = vehicle_df.copy()
        filters = st.columns([2, 1, 1])
        search = filters[0].text_input("Search by plate number")
        vehicle_types = sorted(
            value
            for value in filtered_records.get("vehicle_type", pd.Series(dtype=str)).unique()
            if str(value).strip()
        )
        selected_type = filters[1].selectbox("Vehicle type", ["All"] + vehicle_types)
        statuses = sorted(
            value
            for value in filtered_records.get("status", pd.Series(dtype=str)).unique()
            if str(value).strip()
        )
        selected_status = filters[2].selectbox("Status", ["All"] + statuses)

        if search:
            filtered_records = filtered_records[
                filtered_records["plate_number"].astype(str).str.contains(
                    search, case=False, na=False
                )
            ]
        if selected_type != "All":
            filtered_records = filtered_records[
                filtered_records["vehicle_type"].eq(selected_type)
            ]
        if selected_status != "All":
            filtered_records = filtered_records[
                filtered_records["status"].eq(selected_status)
            ]

        if filtered_records.empty:
            st.info("No records match the selected search and filters.")
        else:
            display_vehicle_table(
                sort_by_entry_time(filtered_records),
                [
                    "plate_number",
                    "vehicle_type",
                    "entry_time",
                    "assigned_slot",
                    "status",
                    "exit_time",
                ],
            )


# ==========================================================
# PARKING LAYOUT
# ==========================================================

elif active_page == "Parking Layout":

    render_page_header("Live parking slot status")
    st.subheader("Parking Layout")
    layout_tabs = st.tabs(["Car Parking", "Bus Parking", "Motorcycle Parking"])
    layout_types = ["car", "bus", "motorcycle"]

    for tab, vehicle_type in zip(layout_tabs, layout_types):
        with tab:
            layout = load_parking_layout_for_type(vehicle_type)
            total, occupied, available = parking_counts(layout)
            summary_columns = st.columns(3)
            summary_columns[0].metric("Total Slots", total)
            summary_columns[1].metric("Occupied Slots", occupied)
            summary_columns[2].metric("Available Slots", available)

            layout_image = f"output/parking_layout/{vehicle_type}_parking_layout.jpg"
            if os.path.exists(layout_image):
                st.image(
                    layout_image,
                    caption=f"{vehicle_type.title()} parking layout",
                    width="stretch",
                )
            elif layout.empty:
                st.info("Parking layout is not available yet.")

            st.markdown("**Slot availability**")
            if layout.empty:
                st.info("No slots are available for this category.")
            else:
                ordered_layout = layout.copy()
                if "row" in ordered_layout and "column" in ordered_layout:
                    ordered_layout = ordered_layout.sort_values(["row", "column"])
                for row_name, row_slots in ordered_layout.groupby("row", sort=True):
                    st.caption(f"Row {row_name}")
                    slot_columns = st.columns(min(8, len(row_slots)))
                    for index, (_, slot) in enumerate(row_slots.iterrows()):
                        status_value = str(slot.get("status", "")).lower()
                        is_available = status_value == "empty"
                        status_label = "Available" if is_available else "Occupied"
                        slot_name = html.escape(str(slot.get("slot", "—")))
                        slot_class = "available" if is_available else "occupied"
                        slot_columns[index % len(slot_columns)].markdown(
                            f'<div class="slot-chip {slot_class}">'
                            f'<strong>{slot_name}</strong><br>{status_label}</div>',
                            unsafe_allow_html=True,
                        )


# ==========================================================
# PARKING HISTORY / REPORTS
# ==========================================================

elif active_page == "Parking History / Reports":

    render_page_header("Parking activity and completed sessions")
    st.subheader("Parking History / Reports")

    history = vehicle_df.copy() if not vehicle_df.empty else pd.DataFrame()
    status_values = history.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    completed = history[status_values.eq("exited")].copy() if not history.empty else history
    inside_count = int(status_values.eq("inside").sum()) if not history.empty else 0
    exit_count = int(status_values.eq("exited").sum()) if not history.empty else 0

    report_columns = st.columns(4)
    report_columns[0].metric("Vehicle Entries", len(history))
    report_columns[1].metric("Vehicle Exits", exit_count)
    report_columns[2].metric("Currently Inside", inside_count)
    report_columns[3].metric("Previous Parking Records", len(completed))

    st.divider()
    st.markdown("### Completed Parking Sessions")
    if completed.empty:
        st.info("No completed parking sessions are available yet.")
    else:
        entry_times = pd.to_datetime(completed["entry_time"], errors="coerce")
        exit_times = pd.to_datetime(completed["exit_time"], errors="coerce")
        durations = exit_times - entry_times

        def format_duration(duration):
            if pd.isna(duration):
                return "Not available"
            total_minutes = max(0, int(duration.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)
            days, hours = divmod(hours, 24)
            if days:
                return f"{days}d {hours}h {minutes}m"
            if hours:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"

        completed["duration"] = durations.map(format_duration)
        completed_display = sort_by_entry_time(completed).rename(
            columns={
                "plate_number": "Plate Number",
                "vehicle_type": "Vehicle Type",
                "assigned_slot": "Assigned Slot",
                "entry_time": "Entry Time",
                "exit_time": "Exit Time",
                "duration": "Duration",
            }
        )
        st.dataframe(
            completed_display[
                [
                    "Plate Number",
                    "Vehicle Type",
                    "Assigned Slot",
                    "Entry Time",
                    "Exit Time",
                    "Duration",
                ]
            ],
            width="stretch",
            hide_index=True,
        )
