"""
Label printing service for barcode labels.

Provides functionality to print barcode labels using pt-p710bt-label-maker
with support for multiple label types and test mode short-circuiting.
"""

import logging
from typing import Dict, Any, Optional
from flask import current_app
from pt_p710bt_label_maker.barcode_label import BarcodeLabelGenerator, FlagModeGenerator
from pt_p710bt_label_maker.lp_printer import LpPrinter
from typing import Union, List
from io import BytesIO

logger = logging.getLogger(__name__)

# Label types configuration - single source of truth
LABEL_TYPES: Dict[str, Dict[str, Any]] = {
    'Sato 1x2': {
        "lp_options": "-d sato2 -o PageSize=w144h72 -o Level=B -o Darkness=5",
        "maxlen_inches": 2.0,
        "lp_width_px": 305,
        "fixed_len_px": 610,
        "lp_dpi": 305
    },
    'Sato 1x2 Flag': {
        "lp_options": "-d sato2 -o PageSize=w144h72 -o Level=B -o Darkness=5",
        "maxlen_inches": 2.0,
        "lp_width_px": 305,
        "fixed_len_px": 610,
        "flag_mode": True,
        "lp_dpi": 305
    },
    'Sato 2x4': {
        "lp_options": "-d sato3 -o PageSize=w288h144 -o Level=B -o Darkness=5",
        "maxlen_inches": 4.0,
        "lp_width_px": 610,
        "fixed_len_px": 1220,
        "lp_dpi": 305
    },
    'Sato 2x4 Flag': {
        "lp_options": "-d sato3 -o PageSize=w288h144 -o Level=B -o Darkness=5",
        "maxlen_inches": 4.0,
        "lp_width_px": 610,
        "fixed_len_px": 1220,
        "flag_mode": True,
        "lp_dpi": 305
    },
    'Sato 4x6': {
        "lp_options": "-d SatoM48Pro2 -o PageSize=w400h600 -o Level=B -o Darkness=5 -o landscape",
        "maxlen_inches": 6.0,
        "lp_width_px": 1218,
        "fixed_len_px": 2436,
        "lp_dpi": 203
    },
    'Sato 4x6 Flag': {
        "lp_options": "-d SatoM48Pro2 -o PageSize=w400h600 -o Level=B -o Darkness=5 -o landscape",
        "maxlen_inches": 6.0,
        "lp_width_px": 1218,
        "fixed_len_px": 2436,
        "flag_mode": True,
        "lp_dpi": 203
    }
}


def generate_and_print_label(
    barcode_value: str,
    lp_options: str,
    maxlen_inches: float,
    lp_width_px: int,
    fixed_len_px: int,
    flag_mode: bool = False,
    lp_dpi: int = 305,
    num_copies: int = 1
) -> None:
    """
    Generate and print a barcode label equivalent to pt-barcode-label commands.
    
    Args:
        barcode_value: The text/value for the barcode
        lp_options: LP printer options string (e.g., "-d printer_name -o option=value")
        maxlen_inches: Maximum label length in inches
        lp_width_px: Width in pixels for LP printing (height of the label)
        fixed_len_px: Fixed length in pixels for the final image
        flag_mode: Whether to use flag mode (rotated barcodes at ends)
        lp_dpi: DPI for LP printing (default: 305)
        num_copies: Number of copies to print (default: 1)
    """
    # Test mode short-circuit - prevents actual printing during tests or if disabled
    if current_app and (current_app.config.get('TESTING', False) or current_app.config.get('DISABLE_LABEL_PRINTING', False)):
        logger.info(
            f"Test mode detected - short-circuiting label print. "
            f"Would have printed: barcode_value='{barcode_value}', "
            f"lp_options='{lp_options}', maxlen_inches={maxlen_inches}, "
            f"lp_width_px={lp_width_px}, fixed_len_px={fixed_len_px}, "
            f"flag_mode={flag_mode}, lp_dpi={lp_dpi}, num_copies={num_copies}"
        )
        return

    logger.info(f"Printing label for barcode: {barcode_value}")
    
    try:
        # Calculate maxlen_px from inches
        maxlen_px: int = int(maxlen_inches * lp_dpi)
        
        # Generate the appropriate label type
        generator: Union[BarcodeLabelGenerator, FlagModeGenerator]
        if flag_mode:
            generator = FlagModeGenerator(
                value=barcode_value,
                height_px=lp_width_px,
                maxlen_px=maxlen_px,
                fixed_len_px=fixed_len_px,
                show_text=True
            )
        else:
            generator = BarcodeLabelGenerator(
                value=barcode_value,
                height_px=lp_width_px,
                maxlen_px=maxlen_px,
                fixed_len_px=fixed_len_px,
                show_text=True
            )
        
        # Print using lp
        try:
            printer: LpPrinter = LpPrinter(lp_options)
            images: List[BytesIO] = [generator.file_obj] * num_copies if num_copies > 1 else [generator.file_obj]
            printer.print_images(images)
        except Exception as print_error:
            import traceback
            import shutil
            import os
            
            logger.error(f"Error in LpPrinter.print_images(): {print_error}")
            
            # Check if this is the common PATH issue
            lp_path = shutil.which('lp')
            current_path = os.environ.get('PATH', 'PATH not set')
            
            if lp_path is None and '$PATH' in current_path:
                logger.error("ROOT CAUSE: PATH variable contains unexpanded $PATH")
                logger.info("Attempting to fix malformed PATH by expanding $PATH...")
                
                # Get a reasonable default PATH
                default_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
                fixed_path = current_path.replace('$PATH', default_path)
                os.environ['PATH'] = fixed_path
                logger.info(f"Fixed PATH set to: {fixed_path}")
                
                # Try to find lp again with fixed PATH
                lp_path = shutil.which('lp')
                
                if lp_path:
                    logger.info("SUCCESS: Found lp command after fixing PATH. Retrying print...")
                    # Retry the print operation
                    printer = LpPrinter(lp_options)
                    printer.print_images(images)
                    logger.info(f"Successfully printed {num_copies} label(s) for {barcode_value}")
                    return  # Success, exit the function
            
            # If we can't fix it, provide helpful error info
            logger.error(f"Full traceback: {traceback.format_exc()}")
            if lp_path is None:
                logger.error(f"'lp' command not found in PATH: {current_path}")
                raise Exception("'lp' command not found. Please install CUPS (sudo apt install cups) or check your system PATH.")
            else:
                logger.error(f"'lp' command found at {lp_path}, but printing failed.")
                raise print_error
        
        logger.info(f"Successfully printed {num_copies} label(s) for {barcode_value}")
        
    except Exception as e:
        logger.error(f"Error printing label for {barcode_value}: {str(e)}")
        raise


def print_label_for_ja_id(ja_id: str, label_type: str) -> None:
    """
    Print a label for a specific JA ID using the specified label type.
    
    Args:
        ja_id: The JA ID to print (e.g., "JA123456")
        label_type: The type of label to print (must be a key in LABEL_TYPES)
        
    Raises:
        ValueError: If label_type is not valid
        Exception: If printing fails
    """
    if label_type not in LABEL_TYPES:
        valid_types = list(LABEL_TYPES.keys())
        raise ValueError(f"Invalid label type '{label_type}'. Valid types: {valid_types}")
    
    logger.info(f"Printing {label_type} label for JA ID: {ja_id}")
    
    # Get the label configuration
    label_config = LABEL_TYPES[label_type].copy()
    label_config['barcode_value'] = ja_id
    
    # Call the core printing function
    generate_and_print_label(**label_config)


def get_available_label_types() -> List[str]:
    """
    Get a list of all available label types.
    
    Returns:
        List of label type names
    """
    return list(LABEL_TYPES.keys())


def get_label_type_config(label_type: str) -> Optional[Dict[str, Any]]:
    """
    Get the configuration for a specific label type.
    
    Args:
        label_type: The label type name
        
    Returns:
        Label configuration dictionary, or None if label type is invalid
    """
    return LABEL_TYPES.get(label_type)