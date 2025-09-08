#!/usr/bin/env python3
"""
Debug script for E2E form submission issues
"""

from playwright.sync_api import sync_playwright
import sys
import time

def debug_form_submission():
    """Debug the form submission process"""
    with sync_playwright() as p:
        # Launch browser in headed mode
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: print(f"Console: {msg.text}"))
        page.on("pageerror", lambda msg: print(f"Page Error: {msg}"))
        
        try:
            # Navigate to add form
            print("Navigating to form...")
            page.goto("http://127.0.0.1:5000/inventory/add")
            page.wait_for_timeout(2000)
            
            # Take screenshot
            page.screenshot(path="debug_form_initial.png")
            print("Initial screenshot saved as debug_form_initial.png")
            
            # Fill form
            print("Filling form...")
            page.fill("#ja_id", "TEST001")
            page.select_option("#item_type", "Rod")
            page.select_option("#shape", "Round") 
            page.fill("#material", "Steel")
            
            # Take screenshot of filled form
            page.screenshot(path="debug_form_filled.png")
            print("Filled form screenshot saved as debug_form_filled.png")
            
            # Submit form
            print("Submitting form...")
            page.click("#submit-btn")
            
            # Wait for navigation or response
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except:
                print("No network idle - continuing...")
            
            # Take screenshot of result
            page.screenshot(path="debug_form_result.png")
            print("Result screenshot saved as debug_form_result.png")
            print(f"Current URL: {page.url}")
            
            # Check for flash messages
            try:
                success_msg = page.locator(".alert.alert-success").text_content(timeout=1000)
                print(f"Success message: {success_msg}")
            except:
                print("No success message found")
            
            try:
                error_msg = page.locator(".alert.alert-danger, .alert.alert-error").text_content(timeout=1000)
                print(f"Error message: {error_msg}")
            except:
                print("No error message found")
                
        except Exception as e:
            print(f"Error during debugging: {e}")
            page.screenshot(path="debug_error.png")
        finally:
            print("Waiting 5 seconds before closing...")
            page.wait_for_timeout(5000)
            browser.close()

if __name__ == "__main__":
    debug_form_submission()