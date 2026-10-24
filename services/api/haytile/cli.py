import argparse

from sqlalchemy import select

from .db import Audit, Session, User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["promote-admin"])
    parser.add_argument("email")
    args = parser.parse_args()
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
