import calendar

from app import app
from database.db import db

from models.maintenance_payment import MaintenancePayment
from models.financial_account import FinancialAccount
from models.financial_transaction import FinancialTransaction


def backfill_financial_transactions():

    created_count = 0
    skipped_count = 0
    failed_count = 0

    with app.app_context():

        payments = (
            MaintenancePayment.query
            .order_by(
                MaintenancePayment.id.asc()
            )
            .all()
        )

        print(
            f"Found {len(payments)} maintenance payment(s)."
        )

        for payment in payments:

            bill = payment.bill

            if not bill:

                print(
                    f"SKIPPED Payment #{payment.id}: "
                    "Bill not found."
                )

                failed_count += 1
                continue

            # ---------------------------------
            # CHECK EXISTING TRANSACTION
            # ---------------------------------

            existing_transaction = (
                FinancialTransaction.query
                .filter_by(
                    source_type="MaintenancePayment",
                    source_id=payment.id,
                    direction="Credit"
                )
                .first()
            )

            if existing_transaction:

                print(
                    f"SKIPPED Payment #{payment.id}: "
                    "Financial transaction already exists."
                )

                skipped_count += 1
                continue

            # ---------------------------------
            # CHOOSE ACCOUNT TYPE
            # ---------------------------------

            if payment.payment_mode == "Cash":

                required_account_type = "Cash"

            else:

                required_account_type = "Bank"

            financial_account = (
                FinancialAccount.query
                .filter_by(
                    society_id=bill.society_id,
                    account_type=required_account_type,
                    status=True
                )
                .order_by(
                    FinancialAccount.id.asc()
                )
                .first()
            )

            if not financial_account:

                print(
                    f"FAILED Payment #{payment.id}: "
                    f"No active {required_account_type} "
                    "account found."
                )

                failed_count += 1
                continue

            # ---------------------------------
            # CREATE FINANCIAL TRANSACTION
            # ---------------------------------

            transaction = FinancialTransaction(
                society_id=bill.society_id,
                account_id=financial_account.id,
                transaction_date=payment.payment_date,
                transaction_type="Income",
                direction="Credit",
                amount=payment.amount,
                reference_number=payment.reference_number,
                description=(
                    f"Maintenance payment for "
                    f"Bill #{bill.id} - "
                    f"{calendar.month_name[bill.bill_month]} "
                    f"{bill.bill_year}"
                ),
                source_type="MaintenancePayment",
                source_id=payment.id,
                created_by=payment.recorded_by
            )

            db.session.add(
                transaction
            )

            created_count += 1

            print(
                f"CREATED Payment #{payment.id} "
                f"→ {financial_account.name} "
                f"₹{payment.amount}"
            )

        try:

            db.session.commit()

        except Exception as error:

            db.session.rollback()

            print(
                "Backfill failed."
            )

            print(
                error
            )

            return

        print("")
        print("------------------------------")
        print("BACKFILL COMPLETE")
        print("------------------------------")
        print(
            f"Created : {created_count}"
        )
        print(
            f"Skipped : {skipped_count}"
        )
        print(
            f"Failed  : {failed_count}"
        )


if __name__ == "__main__":

    backfill_financial_transactions()