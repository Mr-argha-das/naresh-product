from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mongoengine import NotUniqueError

from app.accounting import confirm_transaction_entries, create_pending_transaction, ensure_standard_accounts, running_ledger, workspace_accounts
from app.config import get_settings
from app.database import init_db
from app.dependencies import RedirectToLogin, get_current_user, get_owned_workspace, require_user
from app.models import Account, JournalEntry, PAYMENT_METHODS, TRANSACTION_TYPES, Transaction, User, Workspace
from app.security import create_access_token, hash_password, verify_password


settings = get_settings()
app = FastAPI(title=settings.app_name)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def money(value) -> str:
    return f"{Decimal(value):,.2f}"


templates.env.filters["money"] = money


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(RedirectToLogin)
def redirect_to_login(_, exc: RedirectToLogin):
    return exc.response


@app.middleware("http")
async def add_template_user(request: Request, call_next):
    request.state.user = get_current_user(request)
    return await call_next(request)


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200) -> HTMLResponse:
    base = {"request": request, "user": request.state.user, "app_name": settings.app_name}
    if context:
        base.update(context)
    return templates.TemplateResponse(template, base, status_code=status_code)


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def set_auth_cookie(response: RedirectResponse, user: User) -> None:
    token = create_access_token(str(user.id))
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.access_token_expire_minutes * 60,
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if request.state.user:
        return redirect("/dashboard")
    return redirect("/login")


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "auth/register.html")


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    email = email.strip().lower()
    if password != confirm_password:
        return render(request, "auth/register.html", {"error": "Passwords do not match."}, 400)
    if len(password) < 8:
        return render(request, "auth/register.html", {"error": "Password must be at least 8 characters."}, 400)
    try:
        user = User(full_name=full_name.strip(), email=email, password_hash=hash_password(password)).save()
    except NotUniqueError:
        return render(request, "auth/register.html", {"error": "An account with this email already exists."}, 400)

    response = redirect("/workspaces/new?first=1")
    set_auth_cookie(response, user)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "auth/login.html")


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = User.objects(email=email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "auth/login.html", {"error": "Invalid email or password."}, 400)
    response = redirect("/dashboard")
    set_auth_cookie(response, user)
    return response


@app.post("/logout")
def logout():
    response = redirect("/login")
    response.delete_cookie("access_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_user(request)
    workspaces = Workspace.objects(owner=user).order_by("-created_at")
    return render(request, "workspaces/dashboard.html", {"workspaces": workspaces})


@app.get("/workspaces/new", response_class=HTMLResponse)
def new_workspace_page(request: Request, first: int = 0):
    require_user(request)
    return render(request, "workspaces/new.html", {"first": first})


@app.post("/workspaces", response_class=HTMLResponse)
def create_workspace(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    currency: str = Form("PKR"),
):
    user = require_user(request)
    workspace = Workspace(owner=user, name=name.strip(), description=description.strip(), currency=currency.strip().upper()).save()
    ensure_standard_accounts(workspace)
    return redirect(f"/workspaces/{workspace.id}/transactions/new")


def workspace_context(request: Request, workspace_id: str):
    user = require_user(request)
    workspace = get_owned_workspace(workspace_id, user)
    if not workspace:
        return None, redirect("/dashboard")
    ensure_standard_accounts(workspace)
    return workspace, None


def workspace_shell_context(workspace: Workspace, active_page: str) -> dict:
    workspaces = Workspace.objects(owner=workspace.owner).order_by("-created_at")
    return {"workspace": workspace, "workspaces": workspaces, "active_page": active_page}


@app.get("/workspaces/{workspace_id}/transactions", response_class=HTMLResponse)
def transactions_page(
    request: Request,
    workspace_id: str,
    type: str = "",
    date_from: str = "",
    date_to: str = "",
    account: str = "",
):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response

    confirmed_ids = [
        entry.transaction.id
        for entry in JournalEntry.objects(workspace=workspace).only("transaction")
        if entry.transaction
    ]
    query = Transaction.objects(workspace=workspace)
    if confirmed_ids:
        query = query.filter(id__nin=confirmed_ids)
    if type:
        query = query.filter(transaction_type=type)
    if date_from:
        query = query.filter(date__gte=datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(date__lte=datetime.fromisoformat(date_to + "T23:59:59"))
    if account:
        account_obj = Account.objects(id=account, workspace=workspace).first()
        if account_obj:
            query = query.filter(__raw__={"$or": [{"account_from": account_obj.id}, {"account_to": account_obj.id}]})

    return render(
        request,
        "accounting/transactions.html",
        {
            **workspace_shell_context(workspace, "transactions"),
            "accounts": list(workspace_accounts(workspace)),
            "transactions": query.order_by("-date", "-created_at"),
            "transaction_types": TRANSACTION_TYPES,
            "payment_methods": PAYMENT_METHODS,
            "filters": {"type": type, "date_from": date_from, "date_to": date_to, "account": account},
        },
    )


@app.get("/workspaces/{workspace_id}/transactions/new", response_class=HTMLResponse)
def new_transaction_page(request: Request, workspace_id: str, error: str = ""):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response
    return render(
        request,
        "accounting/add_transaction.html",
        {
            **workspace_shell_context(workspace, "add"),
            "accounts": list(workspace_accounts(workspace)),
            "transaction_types": TRANSACTION_TYPES,
            "payment_methods": PAYMENT_METHODS,
            "error": error,
        },
    )


@app.post("/workspaces/{workspace_id}/transactions", response_class=HTMLResponse)
def create_transaction(
    request: Request,
    workspace_id: str,
    date: str = Form(...),
    transaction_type: str = Form(...),
    amount: str = Form(...),
    description: str = Form(...),
    reference_no: str = Form(""),
    account_from: str = Form(...),
    account_to: str = Form(...),
    payment_method: str = Form(...),
):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response
    from_account = Account.objects(id=account_from, workspace=workspace).first()
    to_account = Account.objects(id=account_to, workspace=workspace).first()
    if not from_account or not to_account or from_account.id == to_account.id:
        return redirect(f"/workspaces/{workspace.id}/transactions/new?error=accounts")
    try:
        parsed_amount = Decimal(amount)
        parsed_date = datetime.fromisoformat(date)
    except (InvalidOperation, ValueError):
        return redirect(f"/workspaces/{workspace.id}/transactions/new?error=invalid")
    create_pending_transaction(
        workspace=workspace,
        date=parsed_date,
        transaction_type=transaction_type,
        amount=parsed_amount,
        description=description.strip(),
        reference_no=reference_no.strip(),
        account_from=from_account,
        account_to=to_account,
        payment_method=payment_method,
    )
    return redirect(f"/workspaces/{workspace.id}/transactions")


@app.post("/workspaces/{workspace_id}/transactions/{transaction_id}/confirm", response_class=HTMLResponse)
def confirm_transaction(request: Request, workspace_id: str, transaction_id: str):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response
    transaction = Transaction.objects(id=transaction_id, workspace=workspace).first()
    if transaction:
        confirm_transaction_entries(transaction)
    return redirect(f"/workspaces/{workspace.id}/transactions")


@app.get("/workspaces/{workspace_id}/journal", response_class=HTMLResponse)
def journal_page(request: Request, workspace_id: str):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response
    entries = JournalEntry.objects(workspace=workspace).order_by("-date", "-created_at")
    return render(request, "accounting/journal.html", {**workspace_shell_context(workspace, "journal"), "entries": entries})


@app.get("/workspaces/{workspace_id}/ledger", response_class=HTMLResponse)
def ledger_page(request: Request, workspace_id: str, account: str = ""):
    workspace, response = workspace_context(request, workspace_id)
    if response:
        return response
    accounts = list(workspace_accounts(workspace))
    selected_account = Account.objects(id=account, workspace=workspace).first() if account else (accounts[0] if accounts else None)
    rows = running_ledger(selected_account) if selected_account else []
    return render(
        request,
        "accounting/ledger.html",
        {**workspace_shell_context(workspace, "ledger"), "accounts": accounts, "selected_account": selected_account, "rows": rows},
    )
