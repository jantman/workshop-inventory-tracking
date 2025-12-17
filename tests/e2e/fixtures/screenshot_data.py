"""
Realistic Test Data Fixtures for Screenshot Generation

This module provides comprehensive, realistic test data for generating
documentation screenshots. All data represents actual workshop materials
and usage patterns.
"""

from datetime import datetime, timedelta


# Realistic inventory items representing various workshop materials
SCREENSHOT_INVENTORY_DATA = [
    {
        "ja_id": "JA000101",
        "type": "Rod",
        "shape": "Round",
        "material": "Steel - 1018 Cold Rolled",
        "length": "72",
        "width": "1.5",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 3, Shelf 2",
        "purchase_date": "2024-11-15",
        "purchase_price": "45.99",
        "purchase_location": "Online",
        "vendor": "OnlineMetals.com",
        "part_number": "CR1018-RD-1.5-72",
        "notes": "General purpose machining stock. Good for shafts and axles.",
        "active": "yes"
    },
    {
        "ja_id": "JA000102",
        "type": "Tube",
        "shape": "Round",
        "material": "Aluminum - 6061-T6",
        "length": "96",
        "width": "2",
        "wall_thickness": "0.125",
        "location": "Metal Storage Rack B",
        "sub_location": "Section 1, Horizontal Storage",
        "purchase_date": "2024-10-22",
        "purchase_price": "78.50",
        "purchase_location": "Local",
        "vendor": "McMaster-Carr",
        "part_number": "9056K141",
        "notes": "Lightweight structural tubing for robotics projects",
        "active": "yes"
    },
    {
        "ja_id": "JA000103",
        "type": "Bar",
        "shape": "Square",
        "material": "Aluminum - 6061-T651",
        "length": "48",
        "width": "0.75",
        "thickness": "0.75",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 1, Shelf 3",
        "purchase_date": "2024-09-10",
        "purchase_price": "32.15",
        "purchase_location": "Online",
        "vendor": "OnlineMetals.com",
        "notes": "Square bar stock for brackets and fixtures",
        "active": "yes"
    },
    {
        "ja_id": "JA000104",
        "type": "Sheet",
        "shape": "Rectangular",
        "material": "Aluminum - 5052-H32",
        "length": "24",
        "width": "12",
        "thickness": "0.125",
        "location": "Sheet Metal Rack",
        "sub_location": "Slot 5",
        "purchase_date": "2024-08-05",
        "purchase_price": "42.00",
        "purchase_location": "Local",
        "vendor": "Metal Supermarkets",
        "notes": "Good forming characteristics for enclosures",
        "active": "yes"
    },
    {
        "ja_id": "JA000105",
        "type": "Rod",
        "shape": "Round",
        "material": "Brass - 360 Free Machining",
        "length": "36",
        "width": "0.5",
        "location": "Small Parts Drawer",
        "sub_location": "Drawer 12",
        "purchase_date": "2024-07-18",
        "purchase_price": "28.75",
        "purchase_location": "Online",
        "vendor": "Speedy Metals",
        "notes": "Excellent for bushings and decorative parts",
        "active": "yes"
    },
    {
        "ja_id": "JA000106",
        "type": "Plate",
        "shape": "Rectangular",
        "material": "Steel - A36 Hot Rolled",
        "length": "18",
        "width": "12",
        "thickness": "0.5",
        "location": "Metal Storage Rack C",
        "sub_location": "Bottom Shelf",
        "purchase_date": "2024-06-30",
        "purchase_price": "65.00",
        "purchase_location": "Local",
        "vendor": "Local Steel Yard",
        "notes": "Heavy duty base plates for machinery",
        "active": "yes"
    },
    {
        "ja_id": "JA000107",
        "type": "Tube",
        "shape": "Square",
        "material": "Steel - DOM (Drawn Over Mandrel)",
        "length": "60",
        "width": "2",
        "wall_thickness": "0.188",
        "location": "Metal Storage Rack B",
        "sub_location": "Section 2, Vertical",
        "purchase_date": "2024-11-01",
        "purchase_price": "95.50",
        "purchase_location": "Online",
        "vendor": "McMaster-Carr",
        "part_number": "8986K511",
        "notes": "High strength square tubing for frames",
        "active": "yes"
    },
    {
        "ja_id": "JA000108",
        "type": "Rod",
        "shape": "Hex",
        "material": "Stainless Steel - 303",
        "length": "12",
        "width": "0.375",
        "location": "Small Parts Drawer",
        "sub_location": "Drawer 8",
        "purchase_date": "2024-05-12",
        "purchase_price": "18.25",
        "purchase_location": "Online",
        "vendor": "OnlineMetals.com",
        "notes": "Corrosion resistant hex stock for fasteners",
        "active": "yes"
    },
    {
        "ja_id": "JA000109",
        "type": "Angle",
        "shape": "Rectangular",
        "material": "Aluminum - 6061-T6",
        "length": "72",
        "width": "2",
        "thickness": "2",
        "wall_thickness": "0.125",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 4, Top Rack",
        "purchase_date": "2024-10-08",
        "purchase_price": "42.80",
        "purchase_location": "Local",
        "vendor": "Metal Supermarkets",
        "notes": "2x2x1/8 angle for structural framing",
        "active": "yes"
    },
    {
        "ja_id": "JA000110",
        "type": "Threaded Rod",
        "shape": "Round",
        "material": "Steel - Zinc Plated",
        "length": "36",
        "width": "0.5",
        "thread_series": "UNC",
        "thread_handedness": "Right",
        "thread_size": "1/2-13",
        "thread_form": "UN",
        "location": "Hardware Bins",
        "sub_location": "Bin 24",
        "purchase_date": "2024-09-22",
        "purchase_price": "12.50",
        "purchase_location": "Local",
        "vendor": "Fastenal",
        "part_number": "0141821",
        "notes": "Coarse thread all-thread rod for adjustable assemblies",
        "active": "yes"
    },
    {
        "ja_id": "JA000111",
        "type": "Bar",
        "shape": "Rectangular",
        "material": "Aluminum - 6061-T6",
        "length": "24",
        "width": "3",
        "thickness": "0.5",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 2, Shelf 1",
        "purchase_date": "2024-11-20",
        "purchase_price": "38.90",
        "purchase_location": "Online",
        "vendor": "OnlineMetals.com",
        "notes": "Flat bar for gussets and reinforcement plates",
        "active": "yes"
    },
    {
        "ja_id": "JA000112",
        "type": "Tube",
        "shape": "Round",
        "material": "Copper - C101",
        "length": "24",
        "width": "0.625",
        "wall_thickness": "0.049",
        "location": "Small Parts Drawer",
        "sub_location": "Drawer 15",
        "purchase_date": "2024-08-15",
        "purchase_price": "24.75",
        "purchase_location": "Local",
        "vendor": "Local Plumbing Supply",
        "notes": "Type M copper tubing for heat exchangers",
        "active": "yes"
    },
]

# Additional items with shortening history for history screenshots
SCREENSHOT_HISTORY_DATA = [
    {
        "original_ja_id": "JA000101",
        "action": "shorten",
        "new_ja_id": "JA000201",
        "original_length": "72",
        "new_length": "24",
        "timestamp": "2024-12-01 14:30:00",
        "notes": "Cut to length for motor shaft project"
    },
    {
        "original_ja_id": "JA000103",
        "action": "shorten",
        "new_ja_id": "JA000202",
        "original_length": "48",
        "new_length": "12",
        "timestamp": "2024-11-28 10:15:00",
        "notes": "Small bracket piece"
    },
]

# Items specifically for photo upload demonstrations
SCREENSHOT_PHOTO_ITEMS = [
    {
        "ja_id": "JA000301",
        "type": "Rod",
        "shape": "Round",
        "material": "Steel - 4140 Alloy",
        "length": "36",
        "width": "1.25",
        "location": "Metal Storage Rack A",
        "sub_location": "Section 3, Shelf 1",
        "purchase_date": "2024-11-25",
        "purchase_price": "52.00",
        "vendor": "OnlineMetals.com",
        "notes": "Heat treatable alloy steel for high-stress applications",
        "active": "yes",
        "has_photos": True,
        "photo_count": 3
    },
    {
        "ja_id": "JA000302",
        "type": "Plate",
        "shape": "Rectangular",
        "material": "Aluminum - 7075-T651",
        "length": "12",
        "width": "6",
        "thickness": "0.25",
        "location": "Metal Storage Rack C",
        "sub_location": "Top Shelf",
        "purchase_date": "2024-10-30",
        "purchase_price": "68.50",
        "vendor": "Aircraft Spruce",
        "part_number": "01-05200",
        "notes": "Aircraft-grade aluminum plate",
        "active": "yes",
        "has_photos": True,
        "photo_count": 2
    },
]

# Search filter examples for search screenshots
SCREENSHOT_SEARCH_FILTERS = {
    "material_search": {
        "material": "Aluminum",
        "expected_count": 6
    },
    "dimension_search": {
        "length_min": "24",
        "length_max": "72",
        "expected_count": 8
    },
    "location_search": {
        "location": "Metal Storage Rack A",
        "expected_count": 5
    },
    "combined_search": {
        "type": "Rod",
        "shape": "Round",
        "material_contains": "Steel",
        "expected_count": 3
    }
}

# Batch operation examples
SCREENSHOT_BATCH_OPERATIONS = {
    "move_items": {
        "items": ["JA000101", "JA000102", "JA000103"],
        "new_location": "Workshop Floor",
        "new_sub_location": "Active Project Area"
    },
    "shorten_items": {
        "item": "JA000102",
        "original_length": "96",
        "new_length": "48",
        "notes": "Cut in half for two separate projects"
    }
}

# Location data for autocomplete
SCREENSHOT_LOCATIONS = [
    "Metal Storage Rack A",
    "Metal Storage Rack B",
    "Metal Storage Rack C",
    "Sheet Metal Rack",
    "Small Parts Drawer",
    "Hardware Bins",
    "Workshop Floor",
    "Active Project Area",
]

# Vendor data
SCREENSHOT_VENDORS = [
    "OnlineMetals.com",
    "McMaster-Carr",
    "Metal Supermarkets",
    "Speedy Metals",
    "Fastenal",
    "Aircraft Spruce",
    "Local Steel Yard",
    "Local Plumbing Supply",
]

# Material categories for autocomplete demonstrations
SCREENSHOT_MATERIALS = [
    "Steel - 1018 Cold Rolled",
    "Steel - A36 Hot Rolled",
    "Steel - 4140 Alloy",
    "Steel - DOM (Drawn Over Mandrel)",
    "Steel - Zinc Plated",
    "Aluminum - 6061-T6",
    "Aluminum - 6061-T651",
    "Aluminum - 5052-H32",
    "Aluminum - 7075-T651",
    "Brass - 360 Free Machining",
    "Copper - C101",
    "Stainless Steel - 303",
]


def get_inventory_items(count=None):
    """
    Get realistic inventory items for screenshots.

    Args:
        count: Number of items to return (None for all)

    Returns:
        List of inventory item dictionaries
    """
    if count is None:
        return SCREENSHOT_INVENTORY_DATA.copy()
    return SCREENSHOT_INVENTORY_DATA[:count].copy()


def get_items_with_photos():
    """Get items that should have photos attached."""
    return SCREENSHOT_PHOTO_ITEMS.copy()


def get_history_items():
    """Get items with history for history screenshots."""
    return SCREENSHOT_HISTORY_DATA.copy()


def get_search_examples():
    """Get search filter examples."""
    return SCREENSHOT_SEARCH_FILTERS.copy()


def get_batch_operation_examples():
    """Get batch operation examples."""
    return SCREENSHOT_BATCH_OPERATIONS.copy()


def get_locations():
    """Get list of locations for autocomplete."""
    return SCREENSHOT_LOCATIONS.copy()


def get_vendors():
    """Get list of vendors."""
    return SCREENSHOT_VENDORS.copy()


def get_materials():
    """Get list of materials."""
    return SCREENSHOT_MATERIALS.copy()
