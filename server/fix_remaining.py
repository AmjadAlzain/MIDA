"""
One-time script to fix NULL remaining quantities for all certificate items.
"""

from decimal import Decimal
from app.db.session import get_session_factory
from app.repositories import mida_certificate_repo, mida_import_repo


def main():
    session_factory = get_session_factory()
    if not session_factory:
        print("Error: Could not create database session")
        return
    
    db = session_factory()
    
    try:
        # Get all certificates
        certs, total = mida_certificate_repo.list_certificates(db, limit=1000)
        print(f"Found {total} certificates")
        
        total_fixed = 0
        
        for cert in certs:
            fixed = 0
            for item in cert.items:
                if item.remaining_quantity is None:
                    # Check if there are any imports for this item
                    imports = mida_import_repo.get_import_history_for_item(db, item.id)
                    
                    if imports:
                        # Recalculate from existing imports
                        mida_import_repo.recalculate_item_remaining_quantities(db, item.id)
                    else:
                        # No imports - initialize to approved quantity
                        approved_qty = item.approved_quantity or Decimal("0")
                        
                        # Check if port allocations are set
                        has_port_allocations = (
                            (item.port_klang_qty is not None and item.port_klang_qty > 0) or
                            (item.klia_qty is not None and item.klia_qty > 0) or
                            (item.bukit_kayu_hitam_qty is not None and item.bukit_kayu_hitam_qty > 0)
                        )
                        
                        if has_port_allocations:
                            item.remaining_port_klang = item.port_klang_qty or Decimal("0")
                            item.remaining_klia = item.klia_qty or Decimal("0")
                            item.remaining_bukit_kayu_hitam = item.bukit_kayu_hitam_qty or Decimal("0")
                            item.remaining_quantity = item.remaining_port_klang + item.remaining_klia + item.remaining_bukit_kayu_hitam
                        else:
                            item.remaining_quantity = approved_qty
                            item.remaining_port_klang = approved_qty
                            item.remaining_klia = approved_qty
                            item.remaining_bukit_kayu_hitam = approved_qty
                        
                        item.quantity_status = "normal"
                    
                    fixed += 1
            
            if fixed > 0:
                print(f"  {cert.certificate_number}: fixed {fixed} items")
                total_fixed += fixed
        
        db.commit()
        print(f"\nDone! Fixed {total_fixed} items across all certificates.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
