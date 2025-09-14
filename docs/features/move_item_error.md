# Feature: Move Item Error

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

I’ve just tried to move an item (and also a few items), but every time it fails with an error. The server logs show:

```
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: 2025-09-14 17:55:54,736 ERROR [anonymous@192.168.0.24] Error moving item JA000424: Exception during move: AttributeError: 'str' object has no attribute 'to_dict' at /home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py:49 in _item_to_audit_dict(). Traceback: Traceback (most recent call last):
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:   File "/home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py", line 838, in batch_move_items
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:     item_before=_item_to_audit_dict(item))
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:                 ~~~~~~~~~~~~~~~~~~~^^^^^^
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:   File "/home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py", line 49, in _item_to_audit_dict
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:     'original_thread': item.original_thread.to_dict() if item.original_thread else None,
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]:                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: AttributeError: 'str' object has no attribute 'to_dict'
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: URL: http://192.168.0.24:5603/api/inventory/batch-move
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: Method: POST
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36
Sep 14 17:55:54 phoenix.jasonantman.com flask[3604337]: /home/jantman/GIT/workshop-inventory-tracking/app/main/routes.py:870
```

Please help me debug and fix this problem. Just as important as fixing this problem, please help me understand why our existing e2e tests didn’t catch this problem, and fix them so they would. Please investigate this problem and present me with a plan for fixing it and fixing the e2e tests before changing any code.
