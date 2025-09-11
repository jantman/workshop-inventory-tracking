#!/usr/bin/env python
"""
Google Sheets Data Analysis Script

Analyzes the structure and content of existing Google Sheets data to prepare for migration.
Examines both the Metal sheet (inventory items) and Materials sheet (taxonomy) to identify:
- Data structure and column mappings
- Multi-row JA IDs and their patterns
- Data quality issues or edge cases
- Total record counts and data distribution
"""

import sys
import os
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TestConfig
from app.google_sheets_storage import GoogleSheetsStorage
from app.materials_service import MaterialTaxonomy


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SheetsDataAnalyzer:
    """Analyzer for Google Sheets data structure and content"""
    
    def __init__(self):
        self.sheet_id = TestConfig.GOOGLE_SHEET_ID
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not configured")
        
        self.storage = GoogleSheetsStorage(self.sheet_id)
        
    def analyze_all_data(self) -> Dict[str, Any]:
        """Analyze both Metal and Materials sheets"""
        logger.info("🔍 Starting comprehensive Google Sheets data analysis...")
        
        results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'spreadsheet_id': self.sheet_id,
            'metal_sheet': None,
            'materials_sheet': None,
            'migration_summary': {}
        }
        
        # Test connection first
        connection_result = self.storage.connect()
        if not connection_result.success:
            raise RuntimeError(f"Cannot connect to Google Sheets: {connection_result.error}")
        
        logger.info(f"✅ Connected to spreadsheet: {connection_result.data.get('title', 'Unknown')}")
        
        # Analyze Metal sheet (inventory items)
        logger.info("📊 Analyzing Metal sheet (inventory items)...")
        results['metal_sheet'] = self.analyze_metal_sheet()
        
        # Analyze Materials sheet (taxonomy)
        logger.info("🌳 Analyzing Materials sheet (taxonomy)...")
        results['materials_sheet'] = self.analyze_materials_sheet()
        
        # Generate migration summary
        results['migration_summary'] = self.generate_migration_summary(results)
        
        return results
    
    def analyze_metal_sheet(self) -> Dict[str, Any]:
        """Analyze the Metal sheet (inventory items)"""
        result = self.storage.read_all("Metal")
        if not result.success:
            logger.error(f"Failed to read Metal sheet: {result.error}")
            return {"error": result.error}
        
        data = result.data
        if not data or len(data) < 2:  # Need at least headers + 1 row
            return {"error": "Metal sheet is empty or has no data rows"}
        
        headers = data[0]
        rows = data[1:]
        
        analysis = {
            'total_rows': len(rows),
            'columns': len(headers),
            'headers': headers,
            'ja_id_analysis': self._analyze_ja_ids(rows),
            'data_quality': self._analyze_data_quality(rows, headers),
            'sample_rows': rows[:5],  # First 5 rows for inspection
            'column_analysis': self._analyze_columns(rows, headers)
        }
        
        return analysis
    
    def analyze_materials_sheet(self) -> Dict[str, Any]:
        """Analyze the Materials sheet (taxonomy)"""
        result = self.storage.read_all("Materials")
        if not result.success:
            logger.error(f"Failed to read Materials sheet: {result.error}")
            return {"error": result.error}
        
        data = result.data
        if not data or len(data) < 2:
            return {"error": "Materials sheet is empty or has no data rows"}
        
        headers = data[0]
        rows = data[1:]
        
        analysis = {
            'total_rows': len(rows),
            'columns': len(headers),
            'headers': headers,
            'hierarchy_analysis': self._analyze_material_hierarchy(rows),
            'data_quality': self._analyze_materials_data_quality(rows, headers),
            'sample_rows': rows[:10],  # More samples for hierarchy inspection
            'level_distribution': self._analyze_level_distribution(rows)
        }
        
        return analysis
    
    def _analyze_ja_ids(self, rows: List[List[Any]]) -> Dict[str, Any]:
        """Analyze JA ID patterns and multi-row occurrences"""
        ja_id_counts = Counter()
        ja_id_details = defaultdict(list)
        active_status = {}
        
        for i, row in enumerate(rows):
            if not row or len(row) == 0:
                continue
                
            ja_id = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            if not ja_id:
                continue
                
            ja_id_counts[ja_id] += 1
            
            # Try to determine active status (assuming it's in a later column)
            active = self._parse_active_status(row)
            ja_id_details[ja_id].append({
                'row_index': i + 2,  # +2 because of header and 0-based index
                'active': active,
                'length': self._safe_get_float(row, 2),  # Length is column 2 (0-indexed)
                'material': self._safe_get_string(row, 9)  # Material is column 9 (0-indexed)
            })
            
            if active:
                active_status[ja_id] = True
        
        # Find multi-row JA IDs
        multi_row_ja_ids = {ja_id: count for ja_id, count in ja_id_counts.items() if count > 1}
        
        analysis = {
            'total_unique_ja_ids': len(ja_id_counts),
            'total_rows_with_ja_ids': sum(ja_id_counts.values()),
            'multi_row_ja_ids': len(multi_row_ja_ids),
            'multi_row_details': dict(list(multi_row_ja_ids.items())[:10]),  # Sample of multi-row items
            'ja_id_examples': self._get_ja_id_examples(ja_id_details, multi_row_ja_ids),
            'active_items': len(active_status)
        }
        
        return analysis
    
    def _analyze_material_hierarchy(self, rows: List[List[Any]]) -> Dict[str, Any]:
        """Analyze the materials taxonomy hierarchy"""
        hierarchy = defaultdict(lambda: {'children': [], 'level': 0})
        levels = defaultdict(list)
        
        for i, row in enumerate(rows):
            if not row or len(row) < 3:
                continue
            
            name = self._safe_get_string(row, 0)
            level = self._safe_get_int(row, 1)
            parent = self._safe_get_string(row, 2)
            
            if not name:
                continue
            
            levels[level].append(name)
            hierarchy[name]['level'] = level
            hierarchy[name]['parent'] = parent
            
            if parent and parent in hierarchy:
                hierarchy[parent]['children'].append(name)
        
        return {
            'total_materials': len(hierarchy),
            'levels': dict(levels),
            'level_counts': {level: len(names) for level, names in levels.items()},
            'hierarchy_sample': dict(list(hierarchy.items())[:10]),
            'orphaned_items': self._find_orphaned_materials(hierarchy)
        }
    
    def _analyze_data_quality(self, rows: List[List[Any]], headers: List[str]) -> Dict[str, Any]:
        """Analyze data quality issues in inventory data"""
        issues = []
        empty_cells = defaultdict(int)
        
        for i, row in enumerate(rows):
            row_num = i + 2  # Account for header row
            
            # Check for completely empty rows
            if not any(str(cell).strip() for cell in row if cell):
                issues.append(f"Row {row_num}: Completely empty row")
                continue
            
            # Check for missing JA ID
            ja_id = self._safe_get_string(row, 1)
            if not ja_id:
                issues.append(f"Row {row_num}: Missing JA ID")
            
            # Count empty cells per column
            for j, cell in enumerate(row):
                if j < len(headers) and not str(cell).strip():
                    empty_cells[headers[j]] += 1
        
        return {
            'total_issues': len(issues),
            'issues_sample': issues[:20],  # First 20 issues
            'empty_cells_by_column': dict(empty_cells),
            'data_completeness': self._calculate_completeness(rows, headers)
        }
    
    def _analyze_materials_data_quality(self, rows: List[List[Any]], headers: List[str]) -> Dict[str, Any]:
        """Analyze data quality issues in materials taxonomy"""
        issues = []
        
        for i, row in enumerate(rows):
            row_num = i + 2
            
            name = self._safe_get_string(row, 0)
            level = self._safe_get_int(row, 1)
            parent = self._safe_get_string(row, 2)
            
            if not name:
                issues.append(f"Row {row_num}: Missing material name")
                continue
            
            if level is None or level < 1 or level > 3:
                issues.append(f"Row {row_num}: Invalid level {level} for {name}")
            
            if level > 1 and not parent:
                issues.append(f"Row {row_num}: Level {level} material '{name}' missing parent")
        
        return {
            'total_issues': len(issues),
            'issues_sample': issues[:20]
        }
    
    def generate_migration_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary for migration planning"""
        summary = {}
        
        if results['metal_sheet'] and 'error' not in results['metal_sheet']:
            metal = results['metal_sheet']
            summary['inventory_items'] = {
                'total_rows': metal['total_rows'],
                'unique_ja_ids': metal['ja_id_analysis']['total_unique_ja_ids'],
                'multi_row_items': metal['ja_id_analysis']['multi_row_ja_ids'],
                'active_items': metal['ja_id_analysis']['active_items'],
                'migration_complexity': 'High' if metal['ja_id_analysis']['multi_row_ja_ids'] > 0 else 'Medium'
            }
        
        if results['materials_sheet'] and 'error' not in results['materials_sheet']:
            materials = results['materials_sheet']
            summary['materials_taxonomy'] = {
                'total_materials': materials['total_rows'],
                'hierarchy_levels': len(materials['level_distribution']),
                'categories': materials['level_distribution'].get(1, 0),
                'families': materials['level_distribution'].get(2, 0),
                'materials': materials['level_distribution'].get(3, 0),
                'migration_complexity': 'Medium'
            }
        
        return summary
    
    # Helper methods
    def _parse_active_status(self, row: List[Any]) -> bool:
        """Try to parse active status from the Active column (column 0)"""
        if len(row) > 0:
            value = str(row[0]).strip().lower()
            if value in ['1', 'true', 'yes', 'active']:
                return True
            elif value in ['0', 'false', 'no', 'inactive']:
                return False
        return True  # Default to active if unclear
    
    def _safe_get_string(self, row: List[Any], index: int) -> str:
        """Safely get string value from row"""
        if index < len(row) and row[index] is not None:
            return str(row[index]).strip()
        return ""
    
    def _safe_get_int(self, row: List[Any], index: int) -> Optional[int]:
        """Safely get integer value from row"""
        if index < len(row) and row[index] is not None:
            try:
                return int(float(str(row[index])))  # Handle "2.0" -> 2
            except (ValueError, TypeError):
                pass
        return None
    
    def _safe_get_float(self, row: List[Any], index: int) -> Optional[float]:
        """Safely get float value from row"""
        if index < len(row) and row[index] is not None:
            try:
                return float(row[index])
            except (ValueError, TypeError):
                pass
        return None
    
    def _get_ja_id_examples(self, ja_id_details: Dict, multi_row_ja_ids: Dict) -> Dict[str, Any]:
        """Get examples of single and multi-row JA IDs"""
        examples = {'single_row': [], 'multi_row': []}
        
        # Get examples of multi-row items
        for ja_id in list(multi_row_ja_ids.keys())[:3]:
            examples['multi_row'].append({
                'ja_id': ja_id,
                'occurrences': multi_row_ja_ids[ja_id],
                'details': ja_id_details[ja_id]
            })
        
        # Get examples of single-row items
        single_row_items = [ja_id for ja_id, details in ja_id_details.items() 
                           if len(details) == 1 and ja_id not in multi_row_ja_ids]
        for ja_id in single_row_items[:3]:
            examples['single_row'].append({
                'ja_id': ja_id,
                'details': ja_id_details[ja_id][0]
            })
        
        return examples
    
    def _analyze_level_distribution(self, rows: List[List[Any]]) -> Dict[int, int]:
        """Analyze distribution of materials by hierarchy level"""
        distribution = Counter()
        for row in rows:
            level = self._safe_get_int(row, 1)
            if level is not None:
                distribution[level] += 1
        return dict(distribution)
    
    def _find_orphaned_materials(self, hierarchy: Dict) -> List[str]:
        """Find materials that reference non-existent parents"""
        orphaned = []
        for name, data in hierarchy.items():
            if data['parent'] and data['parent'] not in hierarchy:
                orphaned.append(f"{name} -> {data['parent']}")
        return orphaned[:10]  # Limit to first 10
    
    def _analyze_columns(self, rows: List[List[Any]], headers: List[str]) -> Dict[str, Any]:
        """Analyze column data types and patterns"""
        analysis = {}
        for i, header in enumerate(headers):
            values = [row[i] if i < len(row) else None for row in rows]
            non_empty = [v for v in values if v is not None and str(v).strip()]
            
            analysis[header] = {
                'total_values': len(values),
                'non_empty_values': len(non_empty),
                'fill_rate': len(non_empty) / len(values) if values else 0,
                'sample_values': non_empty[:5]
            }
        return analysis
    
    def _calculate_completeness(self, rows: List[List[Any]], headers: List[str]) -> float:
        """Calculate overall data completeness percentage"""
        total_cells = len(rows) * len(headers)
        if total_cells == 0:
            return 0.0
        
        filled_cells = 0
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(headers) and cell is not None and str(cell).strip():
                    filled_cells += 1
        
        return (filled_cells / total_cells) * 100


def main():
    """Main analysis function"""
    try:
        # Initialize Flask app for application context
        from app import create_app
        from config import TestConfig
        
        app = create_app(TestConfig)
        
        with app.app_context():
            analyzer = SheetsDataAnalyzer()
            results = analyzer.analyze_all_data()
            
            # Print summary
            print("\n" + "="*80)
            print("📊 GOOGLE SHEETS DATA ANALYSIS SUMMARY")
            print("="*80)
            
            if 'migration_summary' in results:
                summary = results['migration_summary']
                
                if 'inventory_items' in summary:
                    inv = summary['inventory_items']
                    print(f"\n📦 INVENTORY ITEMS (Metal Sheet):")
                    print(f"   Total rows: {inv['total_rows']}")
                    print(f"   Unique JA IDs: {inv['unique_ja_ids']}")
                    print(f"   Multi-row items: {inv['multi_row_items']}")
                    print(f"   Active items: {inv['active_items']}")
                    print(f"   Migration complexity: {inv['migration_complexity']}")
                
                if 'materials_taxonomy' in summary:
                    mat = summary['materials_taxonomy']
                    print(f"\n🌳 MATERIALS TAXONOMY (Materials Sheet):")
                    print(f"   Total materials: {mat['total_materials']}")
                    print(f"   Categories (Level 1): {mat['categories']}")
                    print(f"   Families (Level 2): {mat['families']}")
                    print(f"   Materials (Level 3): {mat['materials']}")
                    print(f"   Migration complexity: {mat['migration_complexity']}")
            
            # Save detailed results
            import json
            output_file = 'sheets_analysis_results.json'
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            print(f"\n💾 Detailed analysis saved to: {output_file}")
            print(f"📅 Analysis completed at: {results['analysis_timestamp']}")
            
            return results
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()