import pandas as pd

OUTPUT_FOLDER = "output/parking_layout"


def get_csv_path(vehicle_type):
    return f"{OUTPUT_FOLDER}/{vehicle_type}_parking_layout.csv"


def load_parking_layout(vehicle_type):
    return pd.read_csv(get_csv_path(vehicle_type))


def save_parking_layout(df, vehicle_type):
    df.to_csv(get_csv_path(vehicle_type), index=False)


def get_best_parking_slot(vehicle_type):

    df = load_parking_layout(vehicle_type)

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


def occupy_slot(slot_id,vehicle_type):

    df = load_parking_layout(vehicle_type)

    index = df[df["slot"] == slot_id].index

    if len(index) == 0:
        return False

    df.loc[index, "status"] = "occupied"

    save_parking_layout(df,vehicle_type)

    return True


def free_slot(slot_id,vehicle_type):

    df = load_parking_layout(vehicle_type)

    index = df[df["slot"] == slot_id].index

    if len(index) == 0:
        return False

    df.loc[index, "status"] = "empty"

    save_parking_layout(df,vehicle_type)

    return True


def allocate_parking(vehicle_type):

    slot = get_best_parking_slot(vehicle_type)

    if slot is None:
        return None

    occupy_slot(slot,vehicle_type)

    # # Update parking layout image
    # draw_parking_layout()

    print(f"Assigned Slot: {slot}")

    return slot


