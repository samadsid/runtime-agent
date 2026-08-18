from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from uuid import UUID

from dotenv import load_dotenv

from commerce.models import StaffRole
from infrastructure.database import DatabasePool
from infrastructure.database.config import DatabaseConfig
from infrastructure.database.repositories import (
    PostgresStaffRepository,
    StaffIdentityConflictError,
)
from infrastructure.security import Argon2PasswordHasher
from services.staff_auth import normalize_staff_email


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Bootstrap a staff account and membership."
    )
    result.add_argument("--email", required=True)
    result.add_argument("--display-name", required=True)
    result.add_argument("--tenant-id", required=True, type=UUID)
    result.add_argument(
        "--role", required=True, choices=[role.value for role in StaffRole]
    )
    result.add_argument("--password-stdin", action="store_true")
    return result


async def run(args: argparse.Namespace) -> int:
    load_dotenv()
    password = (
        sys.stdin.readline().rstrip("\n")
        if args.password_stdin
        else getpass.getpass("Password: ")
    )
    minimum = int(os.environ.get("STAFF_PASSWORD_MIN_LENGTH", "12"))
    if len(password) < minimum:
        print(f"Password must contain at least {minimum} characters.", file=sys.stderr)
        return 2
    required = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("Missing database configuration: " + ", ".join(missing), file=sys.stderr)
        return 2
    pool = DatabasePool(
        DatabaseConfig(
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ["POSTGRES_PORT"]),
            database=os.environ["POSTGRES_DB"],
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
    )
    await pool.connect()
    try:
        repository = PostgresStaffRepository(pool)
        account, membership, created = await repository.bootstrap(
            email_normalized=normalize_staff_email(args.email),
            display_name=args.display_name.strip(),
            password_hash=Argon2PasswordHasher().hash(password),
            tenant_id=args.tenant_id,
            role=StaffRole(args.role),
        )
    except StaffIdentityConflictError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        await pool.close()
    action = "created" if created else "already matches"
    print(
        f"Staff account {account.id} and {membership.role.value} membership {action}."
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run(parser().parse_args())))


if __name__ == "__main__":
    main()
