from datetime import datetime, timezone

from mongoengine import (
    CASCADE,
    BooleanField,
    DateTimeField,
    DecimalField,
    Document,
    EmailField,
    ListField,
    ReferenceField,
    StringField,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ACCOUNT_TYPES = (
    "Asset",
    "Liability",
    "Equity",
    "Revenue",
    "Expense",
)

TRANSACTION_TYPES = (
    "Sale",
    "Purchase",
    "Expense",
    "Income",
    "Payment Received",
    "Payment Sent",
    "Journal Entry",
)

PAYMENT_METHODS = ("cash", "bank", "cheque")

STANDARD_ACCOUNTS = [
    ("Cash", "Asset"),
    ("Bank", "Asset"),
    ("Accounts Receivable", "Asset"),
    ("Accounts Payable", "Liability"),
    ("Sales Revenue", "Revenue"),
    ("Purchase", "Expense"),
    ("Expenses", "Expense"),
    ("Capital", "Equity"),
]


class User(Document):
    full_name = StringField(required=True, max_length=120)
    email = EmailField(required=True, unique=True)
    password_hash = StringField(required=True)
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "users",
        "indexes": ["email"],
    }


class Workspace(Document):
    owner = ReferenceField(User, required=True, reverse_delete_rule=CASCADE)
    name = StringField(required=True, max_length=120)
    description = StringField(default="", max_length=500)
    currency = StringField(required=True, default="PKR", max_length=12)
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "workspaces",
        "indexes": ["owner", ("owner", "name")],
    }


class Account(Document):
    workspace = ReferenceField(Workspace, required=True, reverse_delete_rule=CASCADE)
    name = StringField(required=True, max_length=120)
    account_type = StringField(required=True, choices=ACCOUNT_TYPES)
    is_system = BooleanField(default=True)
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "accounts",
        "indexes": [
            "workspace",
            {"fields": ["workspace", "name"], "unique": True},
        ],
    }


class Transaction(Document):
    workspace = ReferenceField(Workspace, required=True, reverse_delete_rule=CASCADE)
    date = DateTimeField(required=True)
    transaction_type = StringField(required=True, choices=TRANSACTION_TYPES)
    amount = DecimalField(required=True, precision=2, min_value=0)
    description = StringField(required=True, max_length=500)
    reference_no = StringField(default="", max_length=80)
    account_from = ReferenceField(Account, required=True)
    account_to = ReferenceField(Account, required=True)
    payment_method = StringField(required=True, choices=PAYMENT_METHODS)
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "transactions",
        "indexes": ["workspace", "date", "transaction_type", "account_from", "account_to"],
    }


class JournalEntry(Document):
    workspace = ReferenceField(Workspace, required=True, reverse_delete_rule=CASCADE)
    transaction = ReferenceField(Transaction, required=True, reverse_delete_rule=CASCADE)
    date = DateTimeField(required=True)
    description = StringField(required=True)
    reference_no = StringField(default="", max_length=80)
    lines = ListField()
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "journal_entries",
        "indexes": ["workspace", "date", "transaction"],
    }


class LedgerEntry(Document):
    workspace = ReferenceField(Workspace, required=True, reverse_delete_rule=CASCADE)
    transaction = ReferenceField(Transaction, required=True, reverse_delete_rule=CASCADE)
    journal_entry = ReferenceField(JournalEntry, required=True, reverse_delete_rule=CASCADE)
    account = ReferenceField(Account, required=True)
    date = DateTimeField(required=True)
    description = StringField(required=True)
    reference_no = StringField(default="", max_length=80)
    debit = DecimalField(default=0, precision=2, min_value=0)
    credit = DecimalField(default=0, precision=2, min_value=0)
    created_at = DateTimeField(default=utc_now)

    meta = {
        "collection": "ledger_entries",
        "indexes": ["workspace", "account", "date", "transaction"],
    }
