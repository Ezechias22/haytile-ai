import argparse

from sqlalchemy import select

from . import accounts
from .db import Audit, Session, User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["promote-admin"])
    parser.add_argument("email")
    args = parser.parse_args()
    if accounts.enabled():
        data = accounts.by_email(args.email.strip().lower())
        if not data:
            raise SystemExit("Register the account first.")
        accounts.hydrate(
            accounts.change(data["id"], {"role": "admin"}, actor="local-operator")
        )
        print("Administrator role updated in Firestore.")
        return
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if not user:
            raise SystemExit("Register the account first.")
        user.role = "admin"
        db.add(
            Audit(
                actor_id="local-operator",
                action="admin.promote",
                details={"user_id": user.id},
            )
        )
    print("Administrator role updated.")


if __name__ == "__main__":
    main()
