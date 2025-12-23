# Feature: Photo Upload Bug

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Problem Statement

I am experiencing a significant bug when uploading photos for an existing inventory item (JA000592 in this case; this item exists only in the actual production environment, which you do not have access to).

At the start, the item has no associated photos, as confirmed in the database:

```
MariaDB [inventory]> SELECT id,filename,content_type,file_size,LENGTH(thumbnail_data),LENGTH(medium_data),LENGTH(original_data),sha256_hash,created_at,updated_at FROM photos WHERE id>33;
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| id | filename         | content_type    | file_size | LENGTH(thumbnail_data) | LENGTH(medium_data) | LENGTH(original_data) | sha256_hash | created_at          | updated_at          |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| 34 | blob             | image/jpeg      |   1587113 |                   6096 |              129481 |               1587113 | NULL        | 2025-12-06 21:32:10 | 2025-12-06 21:32:10 |
| 35 | onlineMetals.pdf | application/pdf |   8702640 |                   5113 |              111488 |               8702640 | NULL        | 2025-12-14 21:38:22 | 2025-12-14 21:38:22 |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
2 rows in set (0.009 sec)
MariaDB [inventory]> SELECT * FROM item_photo_associations WHERE photo_id>33;
+----+----------+----------+---------------+---------------------+
| id | ja_id    | photo_id | display_order | created_at          |
+----+----------+----------+---------------+---------------------+
| 34 | JA000591 |       34 |             1 | 2025-12-06 21:32:10 |
| 35 | JA000264 |       35 |             0 | 2025-12-14 21:38:22 |
| 37 | JA000263 |       35 |             0 | 2025-12-16 10:41:57 |
| 38 | JA000587 |       35 |             0 | 2025-12-16 10:41:57 |
| 39 | JA000588 |       35 |             0 | 2025-12-16 10:41:57 |
| 40 | JA000589 |       35 |             0 | 2025-12-16 10:41:57 |
| 41 | JA000590 |       35 |             0 | 2025-12-16 10:41:57 |
+----+----------+----------+---------------+---------------------+
7 rows in set (0.001 sec)
```

I upload a photo via the `/inventory/edit` page for the item in question. In the UI, I see a successful upload and the photo shows in the "Photos" section with the correct thumbnail, though if I click on the thumbnail or the "View" icon, I get a broken image icon pointing to `/api/photos/undefined?size=original`. In DevTools for my browser, in the Network tab, I see a POST to `/api/items/JA000592/photos` with the following response:

```json
{
  "message": "Photo blob uploaded successfully",
  "photo": {
    "created_at": "2025-12-23T13:39:28",
    "display_order": 0,
    "id": 46,
    "ja_id": "JA000592",
    "photo": {
      "content_type": "image/jpeg",
      "created_at": "2025-12-23T13:39:28",
      "file_size": 1648813,
      "filename": "blob",
      "id": 40,
      "sha256_hash": null,
      "updated_at": "2025-12-23T13:39:28"
    },
    "photo_id": 40
  },
  "success": true
}
```

The server logs for that POST are:

```
Dec 23 08:39:28 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:39:28,428", "level": "INFO", "message": "Connected to MariaDB database successfully", "logger": "app.mariadb_storage", "module": "mariadb_storage", "function": "connect", "line": 60, "request": {"url": "http://192.168.0.24:5603/api/items/JA000592/photos", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linuxx86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:39:28 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:39:28,428", "level": "INFO", "message": "Connected to MariaDB database successfully", "logger": "app.mariadb_storage", "module": "mariadb_storage", "function": "connect", "line": 60, "request": {"url": "http://192.168.0.24:5603/api/items/JA000592/photos", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linuxx86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:39:28 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:39:28,671", "level": "INFO", "message": "Photo uploaded for item JA000592: blob (1648813 bytes)", "logger": "app.photo_service", "module": "photo_service", "function": "upload_photo", "line": 134, "request": {"url": "http://192.168.0.24:5603/api/items/JA000592/photos", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:39:28 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:39:28,671", "level": "INFO", "message": "Photo uploaded for item JA000592: blob (1648813 bytes)", "logger": "app.photo_service", "module": "photo_service", "function": "upload_photo", "line": 134, "request": {"url": "http://192.168.0.24:5603/api/items/JA000592/photos", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
```

The database confirms that photo 40 has been added and is associated with item JA000592:

```
MariaDB [inventory]> SELECT id,filename,content_type,file_size,LENGTH(thumbnail_data),LENGTH(medium_data),LENGTH(original_data),sha256_hash,created_at,updated_at FROM photos WHERE id>33;
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| id | filename         | content_type    | file_size | LENGTH(thumbnail_data) | LENGTH(medium_data) | LENGTH(original_data) | sha256_hash | created_at          | updated_at          |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| 34 | blob             | image/jpeg      |   1587113 |                   6096 |              129481 |               1587113 | NULL        | 2025-12-06 21:32:10 | 2025-12-06 21:32:10 |
| 35 | onlineMetals.pdf | application/pdf |   8702640 |                   5113 |              111488 |               8702640 | NULL        | 2025-12-14 21:38:22 | 2025-12-14 21:38:22 |
| 40 | blob             | image/jpeg      |   1648813 |                   4903 |              114107 |               1648813 | NULL        | 2025-12-23 13:39:28 | 2025-12-23 13:39:28 |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
3 rows in set (0.009 sec)

MariaDB [inventory]> SELECT * FROM item_photo_associations WHERE photo_id>33;
+----+----------+----------+---------------+---------------------+
| id | ja_id    | photo_id | display_order | created_at          |
+----+----------+----------+---------------+---------------------+
| 34 | JA000591 |       34 |             1 | 2025-12-06 21:32:10 |
| 35 | JA000264 |       35 |             0 | 2025-12-14 21:38:22 |
| 37 | JA000263 |       35 |             0 | 2025-12-16 10:41:57 |
| 38 | JA000587 |       35 |             0 | 2025-12-16 10:41:57 |
| 39 | JA000588 |       35 |             0 | 2025-12-16 10:41:57 |
| 40 | JA000589 |       35 |             0 | 2025-12-16 10:41:57 |
| 41 | JA000590 |       35 |             0 | 2025-12-16 10:41:57 |
| 46 | JA000592 |       40 |             0 | 2025-12-23 13:39:28 |
+----+----------+----------+---------------+---------------------+
8 rows in set (0.001 sec)
```

If I now click the "Update Item" button at the bottom left corner of the `/inventory/edit/JA000592` page, I'm redirected back to the Inventory List page as expected and the server logs are as follows:

```
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,606", "level": "INFO", "message": "AUDIT: edit_item item=JA000592 phase=input capturing user input for reconstruction", "logger": "inventory", "module": "logging_config", "function": "log_audit_operation", "line": 317, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}, "item_id": "JA000592", "audit_operation": "edit_item", "audit_phase": "input", "audit_timestamp": "2025-12-23T08:44:08.606526", "audit_data": {"form_data": {"csrf_token": "ImU0OWY3MTc4M2E1YjI5YzJmNmNkZjdhZjNhYmE0YjU0MmZlM2ZlNWQi.aUqbfg.glNWI6TGtsg63kx2SkeqGuQZFQU", "ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "active": "on", "length": "96.5", "width": "0.5", "thickness": "", "wall_thickness": "", "weight": "", "thread_size": "", "thread_series": "", "thread_handedness": "", "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22", "purchase_price": "14.07", "purchase_location": "Steel Mart", "vendor": "Steel Mart", "vendor_part_number": "CR ROUND 1/2\" x 20'", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "submit_type": "save"}, "item_before": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material":"CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:20:05"}}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,606", "level": "INFO", "message": "AUDIT: edit_item item=JA000592 phase=input capturing user input for reconstruction", "logger": "inventory", "module": "logging_config", "function": "log_audit_operation", "line": 317, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}, "item_id": "JA000592", "audit_operation": "edit_item", "audit_phase": "input", "audit_timestamp": "2025-12-23T08:44:08.606526", "audit_data": {"form_data": {"csrf_token": "ImU0OWY3MTc4M2E1YjI5YzJmNmNkZjdhZjNhYmE0YjU0MmZlM2ZlNWQi.aUqbfg.glNWI6TGtsg63kx2SkeqGuQZFQU", "ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "active": "on", "length": "96.5", "width": "0.5", "thickness": "", "wall_thickness": "", "weight": "", "thread_size": "", "thread_series": "", "thread_handedness": "", "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22", "purchase_price": "14.07", "purchase_location": "Steel Mart", "vendor": "Steel Mart", "vendor_part_number": "CR ROUND 1/2\" x 20'", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "submit_type": "save"}, "item_before": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material":"CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:20:05"}}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,609", "level": "INFO", "message": "Retrieved 81 valid materials from taxonomy", "logger": "app.mariadb_inventory_service", "module": "mariadb_inventory_service", "function": "get_valid_materials", "line": 639, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,609", "level": "INFO", "message": "Retrieved 81 valid materials from taxonomy", "logger": "app.mariadb_inventory_service", "module": "mariadb_inventory_service", "function": "get_valid_materials", "line": 639, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,629", "level": "INFO", "message": "AUDIT: update_item_service item=JA000592 phase=success operation completed successfully","logger": "mariadb_inventory_service", "module": "logging_config", "function": "log_audit_operation", "line": 317, "item_id": "JA000592", "audit_operation": "update_item_service", "audit_phase": "success", "audit_timestamp": "2025-12-23T08:44:08.629263", "audit_data": {"item_before": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "length": 96.5, "width": 0.5, "thickness": null, "wall_thickness": null, "weight": null, "location": "M2", "sub_location": "Steel", "thread_series": "", "thread_handedness": "", "thread_size": "", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut(got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'"}, "item_after": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "length": 96.5, "width": 0.5, "thickness":null, "wall_thickness": null, "weight": null, "location": "M2", "sub_location": "Steel", "thread_series": "", "thread_handedness": "", "thread_size": "", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'"}}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,629", "level": "INFO", "message": "Successfully updated item JA000592", "logger": "app.mariadb_inventory_service", "module":"mariadb_inventory_service", "function": "update_item", "line": 768, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,629", "level": "INFO", "message": "Successfully updated item JA000592", "logger": "app.mariadb_inventory_service", "module":"mariadb_inventory_service", "function": "update_item", "line": 768, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,629", "level": "INFO", "message": "AUDIT: edit_item item=JA000592 phase=success operation completed successfully", "logger":"inventory", "module": "logging_config", "function": "log_audit_operation", "line": 317, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}, "item_id": "JA000592", "audit_operation": "edit_item", "audit_phase": "success", "audit_timestamp": "2025-12-23T08:44:08.629493", "audit_data": {"item_before": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:20:05"}, "item_after": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:44:08.609934"}, "changes": {"last_modified": {"before": "2025-12-23T08:20:05", "after": "2025-12-23T08:44:08.609934"}}}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,629", "level": "INFO", "message": "AUDIT: edit_item item=JA000592 phase=success operation completed successfully", "logger":"inventory", "module": "logging_config", "function": "log_audit_operation", "line": 317, "request": {"url": "http://192.168.0.24:5603/inventory/edit/JA000592", "method": "POST", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}, "item_id": "JA000592", "audit_operation": "edit_item", "audit_phase": "success", "audit_timestamp": "2025-12-23T08:44:08.629493", "audit_data": {"item_before": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:20:05"}, "item_after": {"ja_id": "JA000592", "item_type": "Bar", "shape": "Round", "material": "CRS", "dimensions": {"length": "96.5", "width": "0.5", "thickness": null, "wall_thickness": null, "weight": null}, "thread": null, "location": "M2", "sub_location": "Steel", "purchase_date": "2025-12-22T00:00:00", "purchase_price": "14.07", "purchase_location": "Steel Mart", "notes": "Purchased 20' stick at Steel Mart, Tucker for $35 including one cut (got two).", "vendor": "Steel Mart", "vendor_part": "CR ROUND 1/2\" x 20'", "original_material": null, "original_thread": null, "precision": false, "active": true, "date_added": "2025-12-22T17:25:32", "last_modified": "2025-12-23T08:44:08.609934"}, "changes": {"last_modified": {"before": "2025-12-23T08:20:05", "after": "2025-12-23T08:44:08.609934"}}}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,816", "level": "INFO", "message": "Connected to MariaDB database successfully", "logger": "app.mariadb_storage", "module": "mariadb_storage", "function": "connect", "line": 60, "request": {"url": "http://192.168.0.24:5603/api/inventory/list", "method": "GET", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64)AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
Dec 23 08:44:08 phoenix.jasonantman.com flask[2469]: {"timestamp": "2025-12-23 08:44:08,816", "level": "INFO", "message": "Connected to MariaDB database successfully", "logger": "app.mariadb_storage", "module": "mariadb_storage", "function": "connect", "line": 60, "request": {"url": "http://192.168.0.24:5603/api/inventory/list", "method": "GET", "remote_addr": "192.168.0.24", "user_agent": "Mozilla/5.0 (X11; Linux x86_64)AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36", "user_id": "anonymous"}}
```

However, if I now browse back to `/inventory/edit/JA000592`, the thumbnail that I see is of photo 35 not photo 40. Attempting to view that photo gives me a broken photo icon and the word "blob". The link for that photo (`/api/photos/40?size=original`) returns the PDF file of photo 35, not photo 40.

The database has not changed since the photo upload:

```
MariaDB [inventory]> SELECT id,filename,content_type,file_size,LENGTH(thumbnail_data),LENGTH(medium_data),LENGTH(original_data),sha256_hash,created_at,updated_at FROM photos WHERE id>33;
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| id | filename         | content_type    | file_size | LENGTH(thumbnail_data) | LENGTH(medium_data) | LENGTH(original_data) | sha256_hash | created_at          | updated_at          |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
| 34 | blob             | image/jpeg      |   1587113 |                   6096 |              129481 |               1587113 | NULL        | 2025-12-06 21:32:10 | 2025-12-06 21:32:10 |
| 35 | onlineMetals.pdf | application/pdf |   8702640 |                   5113 |              111488 |               8702640 | NULL        | 2025-12-14 21:38:22 | 2025-12-14 21:38:22 |
| 40 | blob             | image/jpeg      |   1648813 |                   4903 |              114107 |               1648813 | NULL        | 2025-12-23 13:39:28 | 2025-12-23 13:39:28 |
+----+------------------+-----------------+-----------+------------------------+---------------------+-----------------------+-------------+---------------------+---------------------+
3 rows in set (0.008 sec)

MariaDB [inventory]> SELECT * FROM item_photo_associations WHERE photo_id>33;
+----+----------+----------+---------------+---------------------+
| id | ja_id    | photo_id | display_order | created_at          |
+----+----------+----------+---------------+---------------------+
| 34 | JA000591 |       34 |             1 | 2025-12-06 21:32:10 |
| 35 | JA000264 |       35 |             0 | 2025-12-14 21:38:22 |
| 37 | JA000263 |       35 |             0 | 2025-12-16 10:41:57 |
| 38 | JA000587 |       35 |             0 | 2025-12-16 10:41:57 |
| 39 | JA000588 |       35 |             0 | 2025-12-16 10:41:57 |
| 40 | JA000589 |       35 |             0 | 2025-12-16 10:41:57 |
| 41 | JA000590 |       35 |             0 | 2025-12-16 10:41:57 |
| 46 | JA000592 |       40 |             0 | 2025-12-23 13:39:28 |
+----+----------+----------+---------------+---------------------+
8 rows in set (0.001 sec)
```

## Your Task

You will create an e2e test that reproduces the user flow that I've described, using a database that already includes multiple items with photos (some one-to-many item to photos, and some one-to-many photo to items). This database can be pre-seeded directly in the database rather than creating and uploading via the UI. We will assume that your e2e test will reproduce the bug I'm seeing; assuming so, you will then examine the codebase and attempt to identify and fix the bug. If your e2e test does not reproduce the bug, stop and discuss with me.
