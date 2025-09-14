"""
MariaDB Materials Taxonomy Admin Service

Handles administrative operations for the hierarchical materials taxonomy using MariaDB.
Provides similar functionality to MaterialsAdminService but works with MariaDB backend.
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from .database import MaterialTaxonomy
from .mariadb_storage import MariaDBStorage
from .exceptions import ValidationError
from config import Config


@dataclass
class TaxonomyAddRequest:
    """Request to add a new taxonomy entry"""
    name: str
    level: int  # 1=Category, 2=Family, 3=Material
    parent: str = ''  # Empty for categories
    aliases: List[str] = None
    notes: str = ''
    sort_order: int = 0


class MariaDBMaterialsAdminService:
    """Service for managing materials taxonomy through admin interface using MariaDB"""
    
    def __init__(self, storage: MariaDBStorage = None):
        """Initialize with MariaDB storage"""
        if storage is None:
            storage = MariaDBStorage()
        
        self.storage = storage
        
        # Direct database access for complex queries
        self.engine = getattr(storage, 'engine', None) or self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
    
    def _create_engine(self):
        """Create database engine if not provided by storage"""
        return create_engine(
            Config.SQLALCHEMY_DATABASE_URI,
            **Config.SQLALCHEMY_ENGINE_OPTIONS
        )
    
    def get_taxonomy_overview(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get complete taxonomy overview for admin interface
        Returns hierarchical structure with usage statistics
        """
        try:
            session = self.Session()
            
            # Get all materials from database
            query = session.query(MaterialTaxonomy)
            if not include_inactive:
                query = query.filter(MaterialTaxonomy.active == True)
            
            all_materials = query.order_by(
                MaterialTaxonomy.level,
                MaterialTaxonomy.sort_order,
                MaterialTaxonomy.name
            ).all()
            
            # Group by level for easier processing
            categories = [m for m in all_materials if m.level == 1]
            families = [m for m in all_materials if m.level == 2]
            materials = [m for m in all_materials if m.level == 3]
            
            # Build hierarchical structure
            overview = []
            
            for category in sorted(categories, key=lambda x: (x.sort_order or 0, x.name)):
                category_data = {
                    'id': category.id,
                    'name': category.name,
                    'level': category.level,
                    'active': category.active,
                    'notes': category.notes or '',
                    'sort_order': category.sort_order or 0,
                    'children': []
                }
                
                # Find families under this category
                category_families = [f for f in families if f.parent == category.name]
                
                for family in sorted(category_families, key=lambda x: (x.sort_order or 0, x.name)):
                    family_data = {
                        'id': family.id,
                        'name': family.name,
                        'level': family.level,
                        'parent': family.parent,
                        'active': family.active,
                        'notes': family.notes or '',
                        'sort_order': family.sort_order or 0,
                        'children': []
                    }
                    
                    # Find materials under this family
                    family_materials = [m for m in materials if m.parent == family.name]
                    
                    for material in sorted(family_materials, key=lambda x: (x.sort_order or 0, x.name)):
                        material_data = {
                            'id': material.id,
                            'name': material.name,
                            'level': material.level,
                            'parent': material.parent,
                            'active': material.active,
                            'aliases': material.aliases or [],
                            'notes': material.notes or '',
                            'sort_order': material.sort_order or 0
                        }
                        family_data['children'].append(material_data)
                    
                    category_data['children'].append(family_data)
                
                overview.append(category_data)
            
            return overview
            
        except Exception as e:
            raise ValidationError(f'Failed to get taxonomy overview: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def get_usage_statistics(self) -> Dict[str, int]:
        """Get usage statistics for materials"""
        try:
            session = self.Session()
            
            # Get statistics from MaterialTaxonomy table
            total_count = session.query(MaterialTaxonomy).count()
            active_count = session.query(MaterialTaxonomy).filter(MaterialTaxonomy.active == True).count()
            categories_count = session.query(MaterialTaxonomy).filter(MaterialTaxonomy.level == 1).count()
            families_count = session.query(MaterialTaxonomy).filter(MaterialTaxonomy.level == 2).count()
            materials_count = session.query(MaterialTaxonomy).filter(MaterialTaxonomy.level == 3).count()
            
            return {
                'total_entries': total_count,
                'active_entries': active_count,
                'inactive_entries': total_count - active_count,
                'categories': categories_count,
                'families': families_count,
                'materials': materials_count
            }
            
        except Exception as e:
            raise ValidationError(f'Failed to get usage statistics: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def add_taxonomy_entry(self, request: TaxonomyAddRequest) -> Tuple[bool, str]:
        """Add a new taxonomy entry"""
        try:
            session = self.Session()
            
            # Validate the request
            self._validate_add_request(request, session)
            
            # Create new material taxonomy entry
            new_material = MaterialTaxonomy(
                name=request.name,
                level=request.level,
                parent=request.parent if request.parent else None,
                aliases=request.aliases or [],
                notes=request.notes,
                sort_order=request.sort_order,
                active=True,
                date_added=datetime.now(),
                last_modified=datetime.now()
            )
            
            session.add(new_material)
            session.commit()
            
            return True, f"Successfully added '{new_material.name}' to taxonomy"
            
        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            return False, f'Failed to add taxonomy entry: {e}'
        finally:
            if 'session' in locals():
                session.close()
    
    def _validate_add_request(self, request: TaxonomyAddRequest, session):
        """Validate a taxonomy add request"""
        # Check if name already exists
        existing = session.query(MaterialTaxonomy).filter(
            MaterialTaxonomy.name == request.name
        ).first()
        
        if existing:
            raise ValidationError(f'Material "{request.name}" already exists')
        
        # Check aliases for conflicts
        if request.aliases:
            for alias in request.aliases:
                existing_alias = session.query(MaterialTaxonomy).filter(
                    MaterialTaxonomy.aliases.contains([alias])
                ).first()
                
                existing_name = session.query(MaterialTaxonomy).filter(
                    MaterialTaxonomy.name == alias
                ).first()
                
                if existing_alias or existing_name:
                    raise ValidationError(f'Alias "{alias}" conflicts with existing material or alias')
        
        # Validate parent exists (for levels 2 and 3)
        if request.level > 1 and request.parent:
            parent_level = request.level - 1
            parent = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.name == request.parent,
                MaterialTaxonomy.level == parent_level
            ).first()
            
            if not parent:
                raise ValidationError(f'Parent "{request.parent}" not found at level {parent_level}')
    
    def toggle_material_status(self, material_id: int) -> Dict[str, Any]:
        """Toggle active/inactive status of a material"""
        try:
            session = self.Session()
            
            material = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.id == material_id
            ).first()
            
            if not material:
                raise ValidationError(f'Material with ID {material_id} not found')
            
            # Toggle status
            material.active = not material.active
            material.last_modified = datetime.now()
            
            session.commit()
            
            return {
                'success': True,
                'id': material.id,
                'name': material.name,
                'active': material.active
            }
            
        except ValidationError:
            raise
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            raise ValidationError(f'Failed to toggle material status: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def get_parent_options(self, level: int) -> List[Dict[str, str]]:
        """Get available parent options for a given level"""
        try:
            session = self.Session()
            
            if level <= 1:
                return []  # Categories don't have parents
            
            parent_level = level - 1
            parents = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.level == parent_level,
                MaterialTaxonomy.active == True
            ).order_by(MaterialTaxonomy.name).all()
            
            return [{'name': p.name, 'level': p.level} for p in parents]
            
        except Exception as e:
            raise ValidationError(f'Failed to get parent options: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def validate_material_name(self, name: str) -> Dict[str, Any]:
        """Validate if a material name is available"""
        try:
            session = self.Session()
            
            existing = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.name == name
            ).first()
            
            return {
                'available': existing is None,
                'conflict': existing.name if existing else None
            }
            
        except Exception as e:
            raise ValidationError(f'Failed to validate material name: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def get_available_parents(self, level: int) -> List[Dict[str, Any]]:
        """Get available parent options for a given level"""
        try:
            session = self.Session()
            
            if level <= 1:
                return []  # Categories don't have parents
            
            parent_level = level - 1
            parents = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.level == parent_level,
                MaterialTaxonomy.active == True
            ).order_by(MaterialTaxonomy.sort_order, MaterialTaxonomy.name).all()
            
            return [{
                'name': p.name,
                'level': p.level,
                'notes': p.notes or ''
            } for p in parents]
            
        except Exception as e:
            raise ValidationError(f'Failed to get available parents: {e}')
        finally:
            if 'session' in locals():
                session.close()
    
    def set_material_status(self, name: str, active: bool) -> Tuple[bool, str]:
        """Set the active status of a taxonomy entry (enable/disable)"""
        try:
            session = self.Session()
            
            # Find the material
            material = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.name == name
            ).first()
            
            if not material:
                return False, f"Material '{name}' not found"
            
            # Update status
            material.active = active
            material.last_modified = datetime.now()
            
            session.commit()
            
            status_word = "activated" if active else "deactivated"
            return True, f"Successfully {status_word} '{name}'"
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
            return False, f"Error updating material status: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()
    
    def validate_add_request(self, request: TaxonomyAddRequest) -> Tuple[bool, List[str]]:
        """Validate a request to add a new taxonomy entry"""
        errors = []
        
        # Basic validation
        if not request.name or not request.name.strip():
            errors.append("Name is required")
            
        if request.level not in [1, 2, 3]:
            errors.append("Level must be 1 (Category), 2 (Family), or 3 (Material)")
            
        # Level-specific validation
        if request.level > 1 and not request.parent:
            errors.append(f"Level {request.level} entries must have a parent")
            
        if request.level == 1 and request.parent:
            errors.append("Categories (Level 1) cannot have a parent")
        
        try:
            session = self.Session()
            
            # Check for duplicates (case-insensitive)
            existing = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.name.ilike(request.name.strip())
            ).first()
            
            if existing:
                errors.append(f"Material '{request.name}' already exists")
            
            # Check aliases for conflicts
            if request.aliases:
                for alias in request.aliases:
                    if alias.strip():
                        # Check if alias conflicts with existing names
                        existing_name = session.query(MaterialTaxonomy).filter(
                            MaterialTaxonomy.name.ilike(alias.strip())
                        ).first()
                        
                        if existing_name:
                            errors.append(f"Alias '{alias}' conflicts with existing material '{existing_name.name}'")
                        
                        # Check if alias conflicts with existing aliases
                        # Note: This is a simplified check; for JSON array searching, we'd need more complex SQL
                        materials_with_aliases = session.query(MaterialTaxonomy).filter(
                            MaterialTaxonomy.aliases.isnot(None)
                        ).all()
                        
                        for material in materials_with_aliases:
                            if material.aliases and alias.strip().lower() in [a.lower() for a in material.aliases]:
                                errors.append(f"Alias '{alias}' conflicts with existing alias for '{material.name}'")
                                break
            
            # Validate parent exists and is correct level
            if request.parent:
                parent_material = session.query(MaterialTaxonomy).filter(
                    MaterialTaxonomy.name == request.parent,
                    MaterialTaxonomy.level == request.level - 1
                ).first()
                
                if not parent_material:
                    expected_parent_level = request.level - 1
                    errors.append(f"Parent '{request.parent}' not found at level {expected_parent_level}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors
        finally:
            if 'session' in locals():
                session.close()