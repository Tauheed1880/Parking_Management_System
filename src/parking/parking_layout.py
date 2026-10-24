"""Manual parking-slot generation backed by the SQLite layout store."""

VEHICLE_TYPES = ("car", "bus", "motorcycle")


def generate_parking_layout(vehicle_type, folder_name=None):
    """Manually regenerate one category's slots from its canonical base image."""
    from src.parking.parking_reconciliation import regenerate_layout

    return regenerate_layout(vehicle_type)


def generate_all_layouts():
    return [generate_parking_layout(vehicle_type) for vehicle_type in VEHICLE_TYPES]


if __name__ == "__main__":
    for report in generate_all_layouts():
        print(report)
