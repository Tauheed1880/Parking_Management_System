import pandas as pd
from src.parking.draw_parking_layout import draw_parking_layout

CSV_FILE = "output/parking_layout/parking_layout.csv"


def load_parking_layout():
    return pd.read_csv(CSV_FILE)


def save_parking_layout(df):
    df.to_csv(CSV_FILE, index=False)


def get_best_parking_slot():

    df = load_parking_layout()

    best_slot = None
    longest_sequence = 0

    for row in sorted(df["row"].unique()):

        row_df = (
            df[df["row"] == row]
            .sort_values("column")
            .reset_index(drop=True)
        )

        current_sequence = []

        for _, slot in row_df.iterrows():

            if slot["status"] == "empty":
                current_sequence.append(slot)

            else:

                if len(current_sequence) > longest_sequence:
                    longest_sequence = len(current_sequence)
                    best_slot = current_sequence[0]

                current_sequence = []

        if len(current_sequence) > longest_sequence:
            longest_sequence = len(current_sequence)
            best_slot = current_sequence[0]

    if best_slot is None:
        return None

    return best_slot["slot"]


def occupy_slot(slot_id):

    df = load_parking_layout()

    index = df[df["slot"] == slot_id].index

    if len(index) == 0:
        return False

    df.loc[index, "status"] = "occupied"

    save_parking_layout(df)

    return True


def free_slot(slot_id):

    df = load_parking_layout()

    index = df[df["slot"] == slot_id].index

    if len(index) == 0:
        return False

    df.loc[index, "status"] = "empty"

    save_parking_layout(df)

    return True


def allocate_parking():

    slot = get_best_parking_slot()

    if slot is None:
        return None

    occupy_slot(slot)

    # Update parking layout image
    draw_parking_layout()

    print(f"Assigned Slot: {slot}")

    return slot


