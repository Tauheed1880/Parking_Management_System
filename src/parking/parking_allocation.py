def get_best_parking_slot(vehicle_type, parking_df):
    """Select the first slot in the longest consecutive empty row run."""
    df = parking_df.copy()

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
