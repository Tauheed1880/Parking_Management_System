import os
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
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed"
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
def load_parking_layout():

    dfs = []

    for vehicle_type in ["car", "motorcycle", "bus"]:

        path = f"output/parking_layout/{vehicle_type}_parking_layout.csv"

        if os.path.exists(path):
            dfs.append(pd.read_csv(path))

    if len(dfs) == 0:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def load_vehicle_database():

    if os.path.exists(VEHICLE_DATABASE):
        return pd.read_csv(VEHICLE_DATABASE)

    return pd.DataFrame()


def load_ocr_results():

    if os.path.exists(OCR_RESULTS):
        return pd.read_csv(OCR_RESULTS)

    return pd.DataFrame()


# -----------------------------
# LIVE DASHBOARD METRICS
# -----------------------------

parking_df = load_parking_layout()

vehicle_df = load_vehicle_database()

if parking_df.empty:

    total_slots = 0
    empty_slots = 0
    occupied_slots = 0

else:

    total_slots = len(parking_df)

    empty_slots = (
        parking_df["status"]
        .str.lower()
        .eq("empty")
        .sum()
    )

    occupied_slots = (
        parking_df["status"]
        .str.lower()
        .eq("occupied")
        .sum()
    )

total_vehicles = occupied_slots

occupancy = (
    occupied_slots / total_slots
    if total_slots > 0
    else 0
)

# -----------------------------
# HEADER
# -----------------------------

current_date = datetime.now().strftime("%d %B %Y")

current_time = datetime.now().strftime("%I:%M:%S %p")

st.markdown(
    f"""
<div class="dashboard-header">

<div>

<div class="dashboard-title">
🚗 Smart Parking Management System
</div>

<div class="dashboard-subtitle">
Real-Time Parking Monitoring Dashboard
</div>

</div>

<div class="dashboard-right">

<div class="status-online">
🟢 System Online
</div>

<div>
📅 {current_date}
</div>

<div>
🕒 {current_time}
</div>

</div>

</div>
""",
    unsafe_allow_html=True
)

# -----------------------------
# METRIC CARDS
# -----------------------------

c1, c2, c3, c4 = st.columns(4)

cards = [

    (
        c1,
        "🚘 Total Slots",
        total_slots,
        "blue"
    ),

    (
        c2,
        "🟢 Empty Slots",
        empty_slots,
        "green"
    ),

    (
        c3,
        "🔴 Occupied Slots",
        occupied_slots,
        "red"
    ),

    (
        c4,
        "📋 Vehicles",
        total_vehicles,
        "orange"
    )

]

for column, title, value, color in cards:

    with column:

        st.markdown(
            f"""
<div class="metric-card {color}">

<div class="metric-title">
{title}
</div>

<div class="metric-value">
{value}
</div>

</div>
""",
            unsafe_allow_html=True
        )

# -----------------------------
# OCCUPANCY
# -----------------------------

st.write("")

st.subheader("Parking Occupancy")

st.progress(occupancy)

st.write(f"### {occupancy*100:.1f}% Occupied")

st.divider()

# ==========================================================
# PART 2 : UPLOAD & PROCESSING PIPELINE
# ==========================================================

st.markdown(
    """
<div class="section-card">

<div class="info-title">
📤 Upload Vehicle Image
</div>

</div>
""",
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader(
    "",
    type=["jpg", "jpeg", "png"],
    label_visibility="collapsed"
)

uploaded_image = None

if uploaded_file is not None:

    uploaded_image = cv2.imdecode(
        np.frombuffer(uploaded_file.getbuffer(), dtype=np.uint8),
        cv2.IMREAD_COLOR
    )


# ----------------------------------------------------------
# PROCESS BUTTON
# ----------------------------------------------------------

process_button = st.button(
    "🚀 Process Vehicle",
    use_container_width=True
)


# ----------------------------------------------------------
# INITIALIZE SESSION STATE
# ----------------------------------------------------------

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


# ----------------------------------------------------------
# PROCESS COMPLETE PIPELINE
# ----------------------------------------------------------

if process_button:

    if uploaded_image is None:

        st.warning("Please upload an image.")

    else:

        with st.spinner("Processing Vehicle..."):

            # Keep the uploaded original in memory.
            st.session_state["uploaded_image"] = uploaded_image.copy()

            # ----------------------------------------
            # STEP 1
            # Vehicle Detection
            # ----------------------------------------

            vehicle_detection_image, vehicle_images, vehicle_type = detect_vehicle(
                uploaded_image,
                uploaded_file.name
            )

            if len(vehicle_type) > 0:
                st.session_state["vehicle_type"] = vehicle_type[0]

            st.session_state["vehicle_detection"] = (
                vehicle_detection_image
            )

            if len(vehicle_images) > 0:
            
                st.session_state["vehicle_crop"] = (
                    vehicle_images
                )

            # ----------------------------------------
            # STEP 2
            # Plate Detection
            # ----------------------------------------

            plate_detection_images, plate_images = detect_plate(
                vehicle_images
            )

            if len(plate_detection_images) > 0:

                st.session_state["plate_detection"] = (
                    plate_detection_images
                )

                    

            if len(plate_images) > 0:

                st.session_state["plate_crop"] = (
                    plate_images[0]
                )

            # ----------------------------------------
            # STEP 3
            # OCR
            # ----------------------------------------

            _, ocr_records = read_plate(
                plate_images
            )

            if len(ocr_records) > 0:

                st.session_state["ocr_record"] = (
                    ocr_records[0]
                )

            # ----------------------------------------
            # STEP 4
            # ENTRY / EXIT LOGIC
            # ----------------------------------------

            plate_number = ""

            if len(ocr_records) > 0:

                plate_number = ocr_records[0]["plate_number"]

            layout_vehicle_type = "car"
            if plate_number != "":

                # -------------------------
                # EXIT
                # -------------------------

                if is_vehicle_inside(plate_number):

                    vehicle_record = get_vehicle(plate_number)
                    layout_vehicle_type = VEHICLE_LAYOUT_MAP.get(
                        vehicle_record["vehicle_type"], "car"
                    )

                    assigned_slot = get_assigned_slot(plate_number)

                    if assigned_slot:
                        free_slot(assigned_slot, layout_vehicle_type)

                    update_exit_time(plate_number)
                    remove_slot(plate_number)

                    st.session_state["assigned_slot"] = assigned_slot

                # -------------------------
                # ENTRY
                # -------------------------

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

                # ----------------------------------------
                # STEP 5
                # UPDATE PARKING IMAGE
                # ----------------------------------------

                updated_layout = draw_parking_layout(layout_vehicle_type)

                st.session_state["parking_layout"] = updated_layout

    st.success("Vehicle processed successfully.")

    st.rerun()

    st.divider()

# ==========================================================
# MAIN DASHBOARD
# ==========================================================

left, right = st.columns([1, 1])

# ==========================================================
# LEFT PANEL
# ==========================================================

with left:

    st.subheader("📷 Uploaded Vehicle")

    if st.session_state["uploaded_image"] is not None:

        st.image(
            st.session_state["uploaded_image"],
            channels="BGR",
            use_container_width=True
        )

    else:

        st.info("Upload a vehicle image.")

    st.write("")

    st.subheader("🚗 Vehicle Detection")

    if st.session_state["vehicle_detection"]:

        st.image(
            st.session_state["vehicle_detection"],
            use_container_width=True
        )

    else:

        st.info("Vehicle detection result will appear here.")

    st.write("")

    st.subheader("🔖 License Plate")

    if st.session_state["plate_crop"]:

        st.image(
            st.session_state["plate_crop"],
            use_container_width=True
        )

    else:

        st.info("Detected license plate will appear here.")

# ==========================================================
# RIGHT PANEL
# ==========================================================

with right:

    st.subheader("🅿 Live Parking Layout")

    if st.session_state["parking_layout"]:

        st.image(
            st.session_state["parking_layout"],
            use_container_width=True
        )

    elif os.path.exists(PARKING_LAYOUT_IMAGE):

        st.image(
            PARKING_LAYOUT_IMAGE,
            use_container_width=True
        )

    else:

        st.info("Parking layout unavailable.")

st.divider()

# ==========================================================
# VEHICLE INFORMATION
# ==========================================================

st.subheader("🚙 Vehicle Information")

info1, info2, info3 = st.columns(3)

plate_number = "--"
vehicle_type = "--"
confidence = "--"
status = "--"
entry_time = "--"
exit_time = "--"
slot = "--"

# ---------------------------------------
# OCR DATA
# ---------------------------------------

ocr = st.session_state["ocr_record"]

if ocr is not None:

    plate_number = ocr["plate_number"]

    confidence = f'{ocr["confidence"]:.2f}'

    status = ocr["status"]

# ---------------------------------------
# VEHICLE DATABASE
# ---------------------------------------

vehicle_df = load_vehicle_database()

if (
    not vehicle_df.empty
    and plate_number != "--"
):

    vehicle = vehicle_df[
        vehicle_df["plate_number"] == plate_number
    ]

    if not vehicle.empty:

        vehicle = vehicle.iloc[-1]

        vehicle_type = vehicle["vehicle_type"]

        entry_time = vehicle["entry_time"]

        exit_time = vehicle["exit_time"]

        status = vehicle["status"]

        slot = vehicle["assigned_slot"]

# ---------------------------------------
# SESSION SLOT
# ---------------------------------------

if st.session_state["assigned_slot"]:

    slot = st.session_state["assigned_slot"]

if st.session_state["vehicle_type"]:
    vehicle_type = st.session_state["vehicle_type"]

# ---------------------------------------
# DISPLAY
# ---------------------------------------

with info1:

    st.metric(
        "Plate Number",
        plate_number
    )

    st.metric(
    "Vehicle Type",
    vehicle_type
)

    st.metric(
        "Vehicle Status",
        status
    )

with info2:

    st.metric(
        "OCR Confidence",
        confidence
    )

    st.metric(
        "Entry Time",
        entry_time
    )

with info3:

    st.metric(
        "Assigned Slot",
        slot
    )

    st.metric(
        "Exit Time",
        exit_time
    )

st.divider()

# ==========================================================
# VEHICLE RECORDS
# ==========================================================

st.subheader("📋 Vehicle Records")

vehicle_df = load_vehicle_database()

if not vehicle_df.empty:

    search = st.text_input(
        "🔍 Search Plate Number"
    )

    if search:

        vehicle_df = vehicle_df[
            vehicle_df["plate_number"]
            .str.contains(
                search,
                case=False,
                na=False
            )
        ]

    vehicle_df = vehicle_df.rename(
        columns={
            "plate_number": "Plate Number",
            "vehicle_type": "Vehicle Type",
            "assigned_slot": "Assigned Slot",
            "entry_time": "Entry Time",
            "exit_time": "Exit Time",
            "status": "Status"
        }
    )

    st.dataframe(
        vehicle_df,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info("No vehicles found.")
