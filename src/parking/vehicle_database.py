import os
import pandas as pd
from datetime import datetime

CSV_FILE = "data/vehicles.csv"


# ---------------------------------------
# LOAD DATABASE
# ---------------------------------------

def load_database():

    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE, dtype=str).fillna("")

    columns = [
        "plate_number",
        "entry_time",
        "exit_time",
        "assigned_slot",
        "status"
    ]

    df = pd.DataFrame(columns=columns)

    df.to_csv(CSV_FILE, index=False)

    return df


# ---------------------------------------
# SAVE DATABASE
# ---------------------------------------

def save_database(df):

    df.to_csv(CSV_FILE, index=False)


# ---------------------------------------
# CHECK VEHICLE EXISTS
# ---------------------------------------

def plate_exists(plate_number):

    df = load_database()

    return plate_number in df["plate_number"].values


# ---------------------------------------
# CHECK VEHICLE INSIDE
# ---------------------------------------

def is_vehicle_inside(plate_number):

    df = load_database()

    vehicle = df[
        (df["plate_number"] == plate_number)
        &
        (df["status"] == "Inside")
    ]

    return not vehicle.empty


# ---------------------------------------
# GET VEHICLE
# ---------------------------------------

def get_vehicle(plate_number):

    df = load_database()

    vehicle = df[
        df["plate_number"] == plate_number
    ]

    if vehicle.empty:
        return None

    return vehicle.iloc[-1]


# ---------------------------------------
# ADD NEW VEHICLE
# ---------------------------------------

def add_vehicle(plate_number):

    df = load_database()

    new_vehicle = pd.DataFrame([{

        "plate_number": plate_number,

        "entry_time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "exit_time": "",

        "assigned_slot": "",

        "status": "Inside"

    }])

    df = pd.concat(
        [df, new_vehicle],
        ignore_index=True
    )

    save_database(df)

    print("Vehicle added.")


# ---------------------------------------
# UPDATE EXIT
# ---------------------------------------

def update_exit_time(plate_number):

    df = load_database()

    index = df[
        (df["plate_number"] == plate_number)
        &
        (df["status"] == "Inside")
    ].index

    if len(index) == 0:
        return

    latest = index[-1]

    df.loc[latest, "exit_time"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    df.loc[latest, "status"] = "Exited"

    save_database(df)

    print("Exit updated.")



# ---------------------------------------
# ASSIGN SLOT
# ---------------------------------------

def assign_slot(plate_number, slot):

    df = load_database()

    index = df[
        (df["plate_number"] == plate_number)
        &
        (df["status"] == "Inside")
    ].index

    if len(index) == 0:
        return

    df.loc[index[-1], "assigned_slot"] = slot

    save_database(df)

    print(f"Assigned Slot {slot}")


# ---------------------------------------
# REMOVE SLOT
# ---------------------------------------

def remove_slot(plate_number):

    df = load_database()

    index = df[
        (df["plate_number"] == plate_number)
        &
        (df["status"] == "Exited")
    ].index

    if len(index) == 0:
        return

    latest = index[-1]

    df.loc[latest, "assigned_slot"] = ""

    save_database(df)

    print("Slot removed.")


# ---------------------------------------
# GET ASSIGNED SLOT
# ---------------------------------------

def get_assigned_slot(plate_number):

    df = load_database()

    vehicle = df[
        (df["plate_number"] == plate_number)
        &
        (df["status"] == "Inside")
    ]

    if vehicle.empty:
        return None

    return vehicle.iloc[-1]["assigned_slot"]