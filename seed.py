"""
Fills the database with sample data so you (or a professor/reviewer) can open
the app and immediately see it in a populated, realistic state, instead of
an empty one.

Usage:
    python seed.py            # adds sample data (skips if data already exists)
    python seed.py --reset    # wipes the database first, then seeds fresh
"""
import os
import sys
from datetime import datetime, timedelta

from app import (
    app, db, User, Project, Milestone, MilestoneFile, MilestoneComment, Notification,
    MILESTONE_TYPES, SECURITY_QUESTIONS, UPLOAD_FOLDER
)
from werkzeug.security import generate_password_hash

SAMPLE_PASSWORD = "password123"


def ensure_placeholder_image():
    """Create a small real PNG so demo milestone files actually open instead of 404ing."""
    path = os.path.join(UPLOAD_FOLDER, "demo-placeholder.png")
    if os.path.exists(path):
        return
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (300, 200), color=(226, 232, 240))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 290, 190], outline=(37, 99, 235), width=3)
        draw.text((60, 90), "Demo Sample File", fill=(31, 41, 48))
        img.save(path)
    except Exception:
        # Pillow not available for some reason — write a tiny valid PNG instead.
        import base64
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8"
            "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with open(path, "wb") as f:
            f.write(tiny_png)


def make_user(name, email, role, **kwargs):
    return User(
        name=name, email=email, role=role,
        password_hash=generate_password_hash(SAMPLE_PASSWORD),
        security_question=SECURITY_QUESTIONS[0],
        security_answer_hash=generate_password_hash("demo"),
        **kwargs
    )


def run():
    with app.app_context():
        if "--reset" in sys.argv:
            db.drop_all()
            db.create_all()
            print("Database reset.")

        if User.query.first():
            print("Data already exists — skipping seed. Use --reset to start fresh.")
            return

        ensure_placeholder_image()

        inspector = make_user("Maria Santos", "inspector@demo.local", "inspector", business_key="MUNI-DEMO01")
        db.session.add(inspector)
        db.session.commit()

        installer1 = make_user("Juan Dela Cruz", "installer1@demo.local", "installer", inspector_id=inspector.id)
        installer2 = make_user("Ana Reyes", "installer2@demo.local", "installer", inspector_id=inspector.id)
        db.session.add_all([installer1, installer2])
        db.session.commit()

        sites = [
            (installer1, "Barangay San Isidro Site", "123 Rizal St, San Isidro", ["approved", "approved", "pending", "pending"]),
            (installer1, "Purok 3 Community Hall", "Purok 3, Mabini", ["approved", "rejected", "pending", "pending"]),
            (installer2, "Riverside Elementary School", "45 Riverside Ave", ["approved", "approved", "approved", "approved"]),
            (installer2, "Sunrise Subdivision Site", "Blk 4 Lot 2, Sunrise Subd.", ["pending", "pending", "pending", "pending"]),
        ]

        for installer, name, address, statuses in sites:
            project = Project(site_name=name, address=address,
                               installer_id=installer.id, inspector_id=inspector.id,
                               created_at=datetime.utcnow() - timedelta(days=10))
            db.session.add(project)
            db.session.commit()

            for mtype, status in zip(MILESTONE_TYPES, statuses):
                m = Milestone(project_id=project.id, milestone_type=mtype, status=status,
                              uploaded_at=datetime.utcnow() - timedelta(days=8))
                if status in ("approved", "rejected"):
                    m.reviewed_at = datetime.utcnow() - timedelta(days=5)
                if status == "rejected":
                    m.note = "Please resubmit with clearer photos."
                db.session.add(m)
                db.session.flush()

                db.session.add(MilestoneFile(milestone_id=m.id, file_path="demo-placeholder.png",
                                              original_name=f"{mtype}.png"))
                if status == "rejected":
                    db.session.add(MilestoneComment(
                        milestone_id=m.id, author_id=inspector.id, author_name=inspector.name,
                        author_role="inspector", body="Please resubmit with clearer photos."
                    ))
                    db.session.add(MilestoneComment(
                        milestone_id=m.id, author_id=installer.id, author_name=installer.name,
                        author_role="installer", body="Got it, re-uploading tomorrow."
                    ))

            db.session.commit()

        db.session.add_all([
            Notification(user_id=inspector.id, message="Juan Dela Cruz signed up as a new installer using your key."),
            Notification(user_id=inspector.id, message="New Grid Connection Sign-off uploaded for Riverside Elementary School."),
            Notification(user_id=installer1.id, message="Site Blueprint for Barangay San Isidro Site was approved."),
        ])
        db.session.commit()

        print("Seed complete. Sample logins (all use password: {}):".format(SAMPLE_PASSWORD))
        print("  Inspector : inspector@demo.local")
        print("  Installer : installer1@demo.local")
        print("  Installer : installer2@demo.local")


if __name__ == "__main__":
    run()
