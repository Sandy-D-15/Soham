from datetime import date, datetime
from decimal import Decimal
from database.db import db
from models.maintenance_bill import MaintenanceBill
from models.maintenance_payment import MaintenancePayment
from models.flat import Flat
from models.floor import Floor
from models.wing import Wing
from models.building import Building
from models.flat_member import FlatMember
from models.user import User


def outstanding_for_flat(flat_id):
    """
    Computes outstanding balance and overdue metrics for a flat:
    Returns dict:
      total_outstanding: Decimal
      unpaid_count: int
      current_bill: MaintenanceBill or None
      overdue_days: int
    """
    bills = (
        MaintenanceBill.query
        .filter_by(flat_id=flat_id)
        .order_by(MaintenanceBill.bill_year.desc(), MaintenanceBill.bill_month.desc())
        .all()
    )

    total_outstanding = Decimal("0.00")
    unpaid_count = 0
    current_bill = bills[0] if bills else None
    overdue_days = 0
    today = date.today()

    for bill in bills:
        # Balance = total_amount - paid_amount + penalty_amount
        bill_total = Decimal(str(bill.total_amount or 0)) + Decimal(str(bill.penalty_amount or 0))
        paid = Decimal(str(bill.paid_amount or 0))
        remaining = bill_total - paid

        if remaining > Decimal("0.01") or bill.status in ("Unpaid", "Pending", "Partially Paid", "Overdue"):
            total_outstanding += max(Decimal("0.00"), remaining)
            unpaid_count += 1

            if bill.due_date and bill.due_date < today:
                days_diff = (today - bill.due_date).days
                if days_diff > overdue_days:
                    overdue_days = days_diff

    return {
        "total_outstanding": total_outstanding,
        "unpaid_count": unpaid_count,
        "current_bill": current_bill,
        "overdue_days": overdue_days
    }


def current_bill_for_flat(flat_id):
    """Retrieves the latest generated maintenance bill for a flat."""
    return (
        MaintenanceBill.query
        .filter_by(flat_id=flat_id)
        .order_by(MaintenanceBill.bill_year.desc(), MaintenanceBill.bill_month.desc())
        .first()
    )


def defaulters(society_id=None, limit=10):
    """
    Finds flats with unpaid dues, ordered by highest outstanding amount.
    Returns list of dicts:
      flat: Flat
      primary_member: FlatMember or None
      outstanding_amount: Decimal
      unpaid_months: int
      overdue_days: int
    """
    flat_query = Flat.query.filter_by(status=True)
    if society_id:
        flat_query = (
            flat_query
            .join(Floor, Flat.floor_id == Floor.id)
            .join(Wing, Floor.wing_id == Wing.id)
            .join(Building, Wing.building_id == Building.id)
            .filter(Building.society_id == society_id)
        )

    all_flats = flat_query.all()
    results = []

    for flat in all_flats:
        info = outstanding_for_flat(flat.id)
        if info["total_outstanding"] > Decimal("0.01"):
            primary = (
                FlatMember.query
                .filter_by(flat_id=flat.id, is_active=True, is_primary=True)
                .first()
            )
            if not primary:
                primary = (
                    FlatMember.query
                    .filter_by(flat_id=flat.id, is_active=True)
                    .first()
                )
            results.append({
                "flat": flat,
                "primary_member": primary,
                "outstanding_amount": info["total_outstanding"],
                "unpaid_months": info["unpaid_count"],
                "overdue_days": info["overdue_days"]
            })

    results.sort(key=lambda x: x["outstanding_amount"], reverse=True)
    return results[:limit]


def get_billing_summary(society_id=None):
    """
    Calculates high-level financial metrics for the admin dashboard:
    - this_month_billed
    - this_month_collected
    - collection_percentage
    - total_outstanding_dues
    """
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Current month bills
    bill_query = MaintenanceBill.query.filter_by(bill_year=current_year, bill_month=current_month)
    if society_id:
        bill_query = bill_query.filter_by(society_id=society_id)
    current_bills = bill_query.all()

    this_month_billed = sum((Decimal(str(b.total_amount or 0)) for b in current_bills), Decimal("0.00"))

    # Current month collections
    payment_query = MaintenancePayment.query
    if society_id:
        payment_query = payment_query.join(MaintenanceBill, MaintenancePayment.bill_id == MaintenanceBill.id).filter(MaintenanceBill.society_id == society_id)
    
    # Filter payments this calendar month
    month_start = date(current_year, current_month, 1)
    if current_month == 12:
        next_month_start = date(current_year + 1, 1, 1)
    else:
        next_month_start = date(current_year, current_month + 1, 1)

    payments = (
        payment_query
        .filter(MaintenancePayment.payment_date >= month_start, MaintenancePayment.payment_date < next_month_start)
        .all()
    )
    this_month_collected = sum((Decimal(str(p.amount or 0)) for p in payments), Decimal("0.00"))

    if this_month_billed > Decimal("0.00"):
        collection_pct = min(100.0, round(float(this_month_collected / this_month_billed * 100), 1))
    else:
        collection_pct = 0.0

    # Total outstanding dues across all active bills
    all_unpaid_query = MaintenanceBill.query.filter(MaintenanceBill.status != "Paid")
    if society_id:
        all_unpaid_query = all_unpaid_query.filter_by(society_id=society_id)
    unpaid_bills = all_unpaid_query.all()

    total_outstanding_dues = sum(
        (max(Decimal("0.00"), Decimal(str(b.total_amount or 0)) + Decimal(str(b.penalty_amount or 0)) - Decimal(str(b.paid_amount or 0)))
         for b in unpaid_bills),
        Decimal("0.00")
    )

    return {
        "this_month_billed": this_month_billed,
        "this_month_collected": this_month_collected,
        "collection_pct": collection_pct,
        "total_outstanding_dues": total_outstanding_dues
    }


def get_structure_stats(society_id=None):
    """Returns total flats, occupied flats, and registered members."""
    flat_query = Flat.query.filter_by(status=True)
    if society_id:
        flat_query = (
            flat_query
            .join(Floor, Flat.floor_id == Floor.id)
            .join(Wing, Floor.wing_id == Wing.id)
            .join(Building, Wing.building_id == Building.id)
            .filter(Building.society_id == society_id)
        )
    total_flats = flat_query.count()

    # Occupied flats: either occupancy_status != 'Vacant' or having an active FlatMember
    occupied_flats = (
        flat_query
        .join(FlatMember, Flat.id == FlatMember.flat_id)
        .filter(FlatMember.is_active == True)
        .distinct()
        .count()
    )

    user_query = User.query.filter_by(role="member", is_active=True, approval_status="approved")
    total_members = user_query.count()

    return {
        "total_flats": total_flats,
        "occupied_flats": occupied_flats,
        "total_members": total_members
    }
