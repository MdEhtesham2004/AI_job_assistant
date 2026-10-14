"""Command-line tasks.

    uv run python -m app.cli create-admin --email you@example.com --full-name "Your Name"

The password is read from the ADMIN_PASSWORD environment variable, or asked for interactively
(never passed as a command-line argument, so it does not end up in shell history).
"""

import argparse
import asyncio
import getpass
import os
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.services.admin_seed import AdminSeedService


def _read_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD")
    if password:
        return password
    password = getpass.getpass("Admin password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return password


def _check_email(email: str) -> str | None:
    """The same rule as sign-in (EmailStr): an address sign-in rejects (e.g. *.test, found in
    Phase 14) must not be created here, or the admin could never log in."""
    try:
        return str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError:
        return None


async def _create_admin(email: str, full_name: str, password: str) -> int:
    checked = _check_email(email)
    if checked is None:
        print(f"Error: {email!r} is not an address you can sign in with.", file=sys.stderr)
        return 1
    email = checked
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            result = await AdminSeedService(session).ensure_admin(
                email=email, full_name=full_name, password=password
            )
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    action = "Created" if result.created else "Promoted existing account to"
    print(f"{action} admin: {result.user.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create_admin = commands.add_parser("create-admin", help="Create or promote the admin account")
    create_admin.add_argument("--email", required=True)
    create_admin.add_argument("--full-name", default="Administrator")

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return asyncio.run(_create_admin(args.email, args.full_name, _read_password()))
    return 2


if __name__ == "__main__":
    sys.exit(main())
