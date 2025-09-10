"""
E2E Tests for Materials Taxonomy Admin Interface

Tests the complete admin workflow for managing hierarchical materials taxonomy.
"""

import pytest
import re
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


class AdminMaterialsPage(BasePage):
    """Page object for admin materials management"""
    
    def navigate(self):
        """Navigate to admin materials overview page"""
        self.page.goto(f"{self.base_url}/admin/materials")
        self.page.wait_for_load_state("networkidle")
    
    def navigate_add_material(self, level=3, parent=None):
        """Navigate to add material page"""
        url = f"{self.base_url}/admin/materials/add?level={level}"
        if parent:
            url += f"&parent={parent}"
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
    
    def assert_overview_visible(self):
        """Assert that overview page is displayed"""
        expect(self.page.locator("h1")).to_contain_text("Materials Taxonomy Admin")
        expect(self.page.locator(".card-header")).to_contain_text("Taxonomy Hierarchy")
    
    def assert_stats_visible(self):
        """Assert that statistics dashboard is visible"""
        expect(self.page.locator(".card-title").first).to_be_visible()
        
    def get_stat_value(self, stat_name):
        """Get value from statistics dashboard"""
        if stat_name == "total":
            return int(self.page.locator(".bg-primary .card-title").inner_text())
        elif stat_name == "active":
            return int(self.page.locator(".bg-success .card-title").inner_text())
        elif stat_name == "categories":
            return int(self.page.locator(".bg-secondary .card-title").inner_text())
    
    def click_add_category(self):
        """Click Add Category button"""
        self.page.locator('a:has-text("Add Category")').click()
        self.page.wait_for_load_state("networkidle")
    
    def click_add_family(self):
        """Click Add Family button"""
        self.page.locator('a:has-text("Add Family")').click()
        self.page.wait_for_load_state("networkidle")
    
    def click_add_material(self):
        """Click Add Material button"""
        self.page.locator('a:has-text("Add Material")').click()
        self.page.wait_for_load_state("networkidle")
    
    def fill_add_form(self, name, parent=None, aliases=None, notes=None, sort_order=None):
        """Fill the add material form"""
        self.page.locator("#name").fill(name)
        
        if parent:
            self.page.locator("#parent").select_option(parent)
            
        if aliases:
            self.page.locator("#aliases").fill(aliases)
            
        if notes:
            self.page.locator("#notes").fill(notes)
            
        if sort_order is not None:
            self.page.locator("#sort_order").fill(str(sort_order))
    
    def submit_form(self):
        """Submit the add form"""
        self.page.locator("#submit-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def assert_success_message(self, message_text=None):
        """Assert success message is shown"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        if message_text:
            expect(alert).to_contain_text(message_text)
    
    def assert_error_message(self, message_text=None):
        """Assert error message is shown"""
        alert = self.page.locator(".alert-danger").first
        expect(alert).to_be_visible()
        if message_text:
            expect(alert).to_contain_text(message_text)
    
    def assert_material_in_tree(self, material_name):
        """Assert material appears in taxonomy tree"""
        material_node = self.page.locator(f'.taxonomy-node[data-name="{material_name}"]')
        expect(material_node).to_be_visible()
    
    def assert_material_not_in_tree(self, material_name):
        """Assert material does not appear in taxonomy tree"""
        material_node = self.page.locator(f'.taxonomy-node[data-name="{material_name}"]')
        expect(material_node).not_to_be_visible()
    
    def toggle_material_status(self, material_name):
        """Toggle active/inactive status of a material"""
        # Find the material node and click its status toggle button
        material_node = self.page.locator(f'.taxonomy-node[data-name="{material_name}"]')
        status_btn = material_node.locator('button:has([class*="bi-eye"])').first
        
        # Set up dialog handler before clicking
        self.page.on("dialog", lambda dialog: dialog.accept())
        status_btn.click()
        
        # Wait for page to reload/update
        self.page.wait_for_load_state("networkidle")
    
    def click_add_child(self, parent_name):
        """Click add child button for a specific material"""
        parent_node = self.page.locator(f'.taxonomy-node[data-name="{parent_name}"]')
        add_child_btn = parent_node.locator('button:has([class*="bi-plus-circle"])').first
        add_child_btn.click()
        self.page.wait_for_load_state("networkidle")
    
    def toggle_show_inactive(self):
        """Toggle the show inactive materials checkbox"""
        self.page.locator("#includeInactive").click()
        self.page.wait_for_load_state("networkidle")


@pytest.mark.e2e
def test_admin_overview_loads(page, live_server):
    """Test that admin overview page loads with taxonomy tree"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Should show admin interface
    admin_page.assert_overview_visible()
    admin_page.assert_stats_visible()
    
    # Should show existing taxonomy from test setup
    admin_page.assert_material_in_tree("Carbon Steel")
    admin_page.assert_material_in_tree("Stainless Steel")


@pytest.mark.e2e  
def test_add_category_workflow(page, live_server):
    """Test adding a new category (Level 1) material"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Get initial stats
    initial_categories = admin_page.get_stat_value("categories")
    initial_total = admin_page.get_stat_value("total")
    
    # Click Add Category
    admin_page.click_add_category()
    
    # Should be on add form with level=1
    expect(page.locator("h1")).to_contain_text("Add Category")
    expect(page.locator('input[name="level"]')).to_have_value("1")
    
    # Fill form (no parent needed for category)
    admin_page.fill_add_form(
        name="Test Plastics",
        aliases="Polymers, Synthetic Materials",
        notes="Synthetic polymer materials for various applications",
        sort_order=10
    )
    
    # Submit form
    admin_page.submit_form()
    
    # Should redirect to overview with success message
    admin_page.assert_success_message("Successfully added 'Test Plastics'")
    
    # Should appear in taxonomy tree
    admin_page.assert_material_in_tree("Test Plastics")
    
    # Stats should be updated
    new_categories = admin_page.get_stat_value("categories")
    new_total = admin_page.get_stat_value("total")
    assert new_categories == initial_categories + 1
    assert new_total == initial_total + 1


@pytest.mark.e2e
def test_add_family_workflow(page, live_server):
    """Test adding a new family (Level 2) under existing category"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Click Add Family
    admin_page.click_add_family()
    
    # Should be on add form with level=2
    expect(page.locator("h1")).to_contain_text("Add Family")
    expect(page.locator('input[name="level"]')).to_have_value("2")
    
    # Should show parent dropdown with categories
    parent_select = page.locator("#parent")
    expect(parent_select).to_be_visible()
    
    # Fill form with parent selection
    admin_page.fill_add_form(
        name="Test High Strength Steel",
        parent="Carbon Steel",
        aliases="High Strength Alloys",
        notes="High strength carbon steel alloys",
        sort_order=5
    )
    
    # Submit form
    admin_page.submit_form()
    
    # Should redirect to overview with success message
    admin_page.assert_success_message("Successfully added 'Test High Strength Steel'")
    
    # Should appear in taxonomy tree under Carbon Steel
    admin_page.assert_material_in_tree("Test High Strength Steel")


@pytest.mark.e2e
def test_add_material_workflow(page, live_server):
    """Test adding a new specific material (Level 3) under existing family"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Click Add Material
    admin_page.click_add_material()
    
    # Should be on add form with level=3
    expect(page.locator("h1")).to_contain_text("Add Material")
    expect(page.locator('input[name="level"]')).to_have_value("3")
    
    # Fill form with parent selection
    admin_page.fill_add_form(
        name="Test 4145 Steel",
        parent="Medium Carbon Steel",
        aliases="4145, Test Alloy Steel",
        notes="Test chromium-molybdenum alloy steel",
        sort_order=3
    )
    
    # Submit form  
    admin_page.submit_form()
    
    # Should redirect to overview with success message
    admin_page.assert_success_message("Successfully added 'Test 4145 Steel'")
    
    # Should appear in taxonomy tree
    admin_page.assert_material_in_tree("Test 4145 Steel")


@pytest.mark.e2e
def test_duplicate_material_prevention(page, live_server):
    """Test that duplicate material names are prevented"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Try to add duplicate category
    admin_page.click_add_category()
    
    # Try to use existing name
    admin_page.fill_add_form(name="Carbon Steel")
    admin_page.submit_form()
    
    # Should show error message
    admin_page.assert_error_message("already exists")


@pytest.mark.e2e
def test_alias_conflict_prevention(page, live_server):
    """Test that alias conflicts with existing materials are prevented"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Try to add material with conflicting alias
    admin_page.click_add_category()
    
    admin_page.fill_add_form(
        name="Test New Category",
        aliases="Carbon Steel, Steel"  # These should conflict
    )
    admin_page.submit_form()
    
    # Should show error about alias conflict
    admin_page.assert_error_message("conflicts")


@pytest.mark.e2e
def test_parent_validation(page, live_server):
    """Test that parent validation works correctly"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Try to add family without parent
    admin_page.click_add_family()
    
    admin_page.fill_add_form(name="Test Family No Parent")
    admin_page.submit_form()
    
    # Should show parent validation error specifically
    parent_feedback = page.locator("#parent").locator("..").locator(".invalid-feedback")
    expect(parent_feedback).to_be_visible()
    expect(parent_feedback).to_contain_text("select a parent")


@pytest.mark.e2e
def test_material_status_toggle(page, live_server):
    """Test toggling material active/inactive status"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    
    # First add a test material to toggle
    admin_page.navigate_add_material(level=1)
    admin_page.fill_add_form(name="Test Toggle Category")
    admin_page.submit_form()
    
    # Should be back on overview
    admin_page.assert_material_in_tree("Test Toggle Category")
    
    # Toggle material to inactive
    admin_page.toggle_material_status("Test Toggle Category")
    
    # Enable "Show inactive materials" to see the inactive material
    admin_page.toggle_show_inactive()
    
    # Should now be visible with inactive badge
    material_node = page.locator('.taxonomy-node[data-name="Test Toggle Category"]')
    expect(material_node.locator(".badge:has-text('INACTIVE')")).to_be_visible()


@pytest.mark.e2e
def test_add_child_workflow(page, live_server):
    """Test adding child material via 'Add child' button"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate()
    
    # Click add child button on existing category
    admin_page.click_add_child("Carbon Steel")
    
    # Should be on add form with parent pre-selected
    expect(page.locator("h1")).to_contain_text("Add Family")  # Level 2
    expect(page.locator("#parent")).to_have_value("Carbon Steel")
    
    # Fill and submit
    admin_page.fill_add_form(name="Test Child Family")
    admin_page.submit_form()
    
    # Should be added successfully
    admin_page.assert_success_message("Successfully added 'Test Child Family'")


@pytest.mark.e2e
def test_show_inactive_toggle(page, live_server):
    """Test show/hide inactive materials functionality"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    
    # First add and deactivate a material
    admin_page.navigate_add_material(level=1)
    admin_page.fill_add_form(name="Test Inactive Category")
    admin_page.submit_form()
    
    # Deactivate it
    admin_page.toggle_material_status("Test Inactive Category")
    
    # Material should now be hidden (default view shows only active materials)
    admin_page.assert_material_not_in_tree("Test Inactive Category")
    
    # Enable "Show inactive materials" to see the inactive material
    admin_page.toggle_show_inactive()
    
    # Should now be visible with inactive badge
    expect(page.locator('.taxonomy-node:has-text("Test Inactive Category")')).to_be_visible()
    
    # Toggle show inactive off again
    admin_page.toggle_show_inactive()
    
    # Should reload page and inactive material should be hidden again
    admin_page.assert_material_not_in_tree("Test Inactive Category")


@pytest.mark.e2e
def test_admin_integration_with_autocomplete(page, live_server):
    """Test that materials added via admin appear in material autocomplete"""
    # First, add a new material via admin
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate_add_material(level=3)
    
    admin_page.fill_add_form(
        name="Test Integration Material",
        parent="Medium Carbon Steel",
        aliases="TIM, Test Material"
    )
    admin_page.submit_form()
    
    # Now go to add inventory item page and test autocomplete
    from tests.e2e.pages.add_item_page import AddItemPage
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Type in material field to trigger autocomplete
    material_input = page.locator('#material')
    material_input.fill('Test Integration')
    page.wait_for_timeout(500)  # Wait for autocomplete
    
    # Should show the new material in suggestions
    suggestions = page.locator('#material-suggestions .dropdown-item')
    expect(suggestions.first).to_be_visible()
    
    # Should find our new material
    suggestion_texts = [item.inner_text() for item in suggestions.all()]
    assert any('Test Integration Material' in text for text in suggestion_texts), f"Expected new material in suggestions: {suggestion_texts}"


@pytest.mark.e2e
def test_real_time_validation(page, live_server):
    """Test that real-time validation works in add form"""
    admin_page = AdminMaterialsPage(page, live_server.url)
    admin_page.navigate_add_material(level=1)
    
    name_input = page.locator("#name")
    
    # Enter duplicate name
    name_input.fill("Carbon Steel")
    page.wait_for_timeout(1000)  # Wait for validation
    
    # Should show as invalid
    expect(name_input).to_have_class(re.compile(r'.*is-invalid.*'))
    
    # Submit button should be disabled
    submit_btn = page.locator("#submit-btn")
    expect(submit_btn).to_be_disabled()
    
    # Clear and enter valid name
    name_input.fill("Valid New Category")
    page.wait_for_timeout(1000)  # Wait for validation
    
    # Should show as valid
    expect(name_input).to_have_class(re.compile(r'.*is-valid.*'))
    expect(submit_btn).to_be_enabled()