"""
E2E Test Debugging Utilities

Provides comprehensive debugging information capture for failed E2E tests,
including screenshots, DOM dumps, console logs, and server logs.
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page
import logging

class E2EDebugCapture:
    """Captures comprehensive debugging information for E2E test failures"""
    
    def __init__(self, test_name: str, output_dir: str = "test-debug-output"):
        self.test_name = test_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Create test-specific directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_dir = self.output_dir / f"{test_name}_{timestamp}"
        self.test_dir.mkdir(exist_ok=True)
        
        self.console_logs: List[Dict[str, Any]] = []
        self.page_errors: List[str] = []
        self.logger = logging.getLogger(__name__)
    
    def setup_page_monitoring(self, page: Page):
        """Set up monitoring for page events, console logs, and errors"""
        # Capture console logs
        def handle_console(msg):
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "type": msg.type,
                "text": msg.text,
                "location": msg.location.get("url", "") if msg.location else ""
            }
            self.console_logs.append(log_entry)
            print(f"Console [{msg.type}]: {msg.text}")
        
        # Capture page errors  
        def handle_page_error(error):
            error_msg = str(error)
            self.page_errors.append({
                "timestamp": datetime.now().isoformat(),
                "error": error_msg
            })
            print(f"Page Error: {error_msg}")
        
        # Capture network failures
        def handle_response(response):
            if response.status >= 400:
                error_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text()
                }
                self.console_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "type": "error",
                    "text": f"HTTP {response.status}: {response.url}",
                    "location": response.url
                })
        
        page.on("console", handle_console)
        page.on("pageerror", handle_page_error) 
        page.on("response", handle_response)
    
    def capture_failure_state(self, page: Page, failure_message: str = ""):
        """Capture comprehensive failure state information"""
        print(f"\\n🔍 Capturing debug information for test failure: {self.test_name}")
        
        try:
            # 1. Screenshot
            screenshot_path = self.test_dir / "failure_screenshot.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"📸 Screenshot saved: {screenshot_path}")
            
            # 2. HTML dump
            html_path = self.test_dir / "failure_page.html"
            html_content = page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"📄 HTML dump saved: {html_path}")
            
            # 3. Console logs
            console_log_path = self.test_dir / "console_logs.json"
            with open(console_log_path, 'w', encoding='utf-8') as f:
                json.dump(self.console_logs, f, indent=2)
            print(f"📋 Console logs saved: {console_log_path}")
            
            # 4. Page errors
            if self.page_errors:
                error_log_path = self.test_dir / "page_errors.json"
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    json.dump(self.page_errors, f, indent=2)
                print(f"❌ Page errors saved: {error_log_path}")
            
            # 5. Current page state
            page_state = {
                "url": page.url,
                "title": page.title(),
                "viewport": page.viewport_size,
                "failure_message": failure_message,
                "timestamp": datetime.now().isoformat()
            }
            
            state_path = self.test_dir / "page_state.json"
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(page_state, f, indent=2)
            print(f"🔍 Page state saved: {state_path}")
            
            # 6. Network requests (if available)
            try:
                self._capture_network_state(page)
            except Exception as e:
                print(f"⚠️  Could not capture network state: {e}")
            
            # 7. Local storage and session storage
            try:
                self._capture_browser_storage(page)
            except Exception as e:
                print(f"⚠️  Could not capture browser storage: {e}")
                
            print(f"✅ Debug capture complete: {self.test_dir}")
            return str(self.test_dir)
            
        except Exception as e:
            print(f"❌ Error during debug capture: {e}")
            return None
    
    def _capture_network_state(self, page: Page):
        """Capture network-related debugging information"""
        # Get cookies
        cookies = page.context.cookies()
        if cookies:
            cookies_path = self.test_dir / "cookies.json"
            with open(cookies_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
    
    def _capture_browser_storage(self, page: Page):
        """Capture browser storage (localStorage, sessionStorage)"""
        storage_data = {}
        
        try:
            # Local storage
            local_storage = page.evaluate("() => JSON.stringify(localStorage)")
            if local_storage and local_storage != "{}":
                storage_data["localStorage"] = json.loads(local_storage)
        except:
            pass
            
        try:
            # Session storage
            session_storage = page.evaluate("() => JSON.stringify(sessionStorage)")
            if session_storage and session_storage != "{}":
                storage_data["sessionStorage"] = json.loads(session_storage)
        except:
            pass
        
        if storage_data:
            storage_path = self.test_dir / "browser_storage.json" 
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2)
    
    def capture_server_logs(self, test_server):
        """Capture server logs if available"""
        try:
            # This would need to be implemented based on how the test server
            # exposes its logs. For now, we'll create a placeholder.
            server_info = {
                "server_url": getattr(test_server, 'url', 'Unknown'),
                "note": "Server log capture not yet implemented",
                "timestamp": datetime.now().isoformat()
            }
            
            server_log_path = self.test_dir / "server_info.json"
            with open(server_log_path, 'w', encoding='utf-8') as f:
                json.dump(server_info, f, indent=2)
                
        except Exception as e:
            print(f"⚠️  Could not capture server logs: {e}")


def create_debug_summary(debug_dir: Path) -> str:
    """Create a human-readable summary of captured debug information"""
    summary_lines = [
        f"# E2E Test Debug Summary",
        f"Generated: {datetime.now().isoformat()}",
        f"Debug Directory: {debug_dir}",
        "",
        "## Captured Files:"
    ]
    
    if debug_dir.exists():
        for file_path in sorted(debug_dir.glob("*")):
            size = file_path.stat().st_size if file_path.is_file() else 0
            summary_lines.append(f"- {file_path.name} ({size} bytes)")
    
    summary_lines.extend([
        "",
        "## Analysis Tips:",
        "1. Check failure_screenshot.png for visual state",
        "2. Review console_logs.json for JavaScript errors",
        "3. Examine failure_page.html for DOM state", 
        "4. Check page_state.json for current URL and context",
        "5. Look at page_errors.json for runtime exceptions"
    ])
    
    summary_content = "\\n".join(summary_lines)
    summary_path = debug_dir / "DEBUG_SUMMARY.md"
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    return summary_content