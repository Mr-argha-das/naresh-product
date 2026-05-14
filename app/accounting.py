from decimal import Decimal
from typing import Iterable

from mongoengine import NotUniqueError

from app.models import Account, JournalEntry, LedgerEntry, STANDARD_ACCOUNTS, Transaction, Workspace


DEBIT_NORMAL_TYPES = {"Asset", "Expense"}


def ensure_standard_accounts(workspace: Workspace) -> None:
    for name, account_type in STANDARD_ACCOUNTS:
        try:
            Account(workspace=workspace, name=name, account_type=account_type, is_system=True).save()
        except NotUniqueError:
            continue


def workspace_accounts(workspace: Workspace) -> Iterable[Account]:
    return Account.objects(workspace=workspace).order_by("account_type", "name")


def create_pending_transaction(
    *,
    workspace: Workspace,
    date,
    transaction_type: str,
    amount: Decimal,
    description: str,
    reference_no: str,
    account_from: Account,
    account_to: Account,
    payment_method: str,
) -> Transaction:
    return Transaction(
        workspace=workspace,
        date=date,
        transaction_type=transaction_type,
        amount=amount,
        description=description,
        reference_no=reference_no,
        account_from=account_from,
        account_to=account_to,
        payment_method=payment_method,
    ).save()


def confirm_transaction_entries(transaction: Transaction) -> JournalEntry:
    existing = JournalEntry.objects(transaction=transaction).first()
    if existing:
        return existing

    amount = transaction.amount
    account_from = transaction.account_from
    account_to = transaction.account_to
    lines = [
        {
            "account_id": str(account_to.id),
            "account_name": account_to.name,
            "debit": str(amount),
            "credit": "0.00",
        },
        {
            "account_id": str(account_from.id),
            "account_name": account_from.name,
            "debit": "0.00",
            "credit": str(amount),
        },
    ]
    journal = JournalEntry(
        workspace=transaction.workspace,
        transaction=transaction,
        date=transaction.date,
        description=f"{transaction.transaction_type}: {transaction.description}",
        reference_no=transaction.reference_no,
        lines=lines,
    ).save()

    LedgerEntry(
        workspace=transaction.workspace,
        transaction=transaction,
        journal_entry=journal,
        account=account_to,
        date=transaction.date,
        description=journal.description,
        reference_no=transaction.reference_no,
        debit=amount,
        credit=Decimal("0.00"),
    ).save()
    LedgerEntry(
        workspace=transaction.workspace,
        transaction=transaction,
        journal_entry=journal,
        account=account_from,
        date=transaction.date,
        description=journal.description,
        reference_no=transaction.reference_no,
        debit=Decimal("0.00"),
        credit=amount,
    ).save()
    return journal


def running_ledger(account: Account):
    balance = Decimal("0.00")
    rows = []
    for entry in LedgerEntry.objects(account=account).order_by("date", "created_at"):
        if account.account_type in DEBIT_NORMAL_TYPES:
            balance += entry.debit - entry.credit
        else:
            balance += entry.credit - entry.debit
        rows.append({"entry": entry, "balance": balance})
    return rows
