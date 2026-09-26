# Solar Panel Installation & Inspection System

A simple Flask web app with two login types:

- **Municipal Inspector** — reviews and signs off on milestones (blueprints, photos, wiring diagrams, grid connection).
- **Installer** — uploads site blueprints, photos, and wiring info, and signs up using a business key from their municipal inspector.

## How to run it

1. Make sure Python 3.9+ is installed.
2. Open a terminal in this folder and install the dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Run the app:

   ```
   python app.py
   ```

4. Open your browser to `http://127.0.0.1:5000`

The database (`solar_system.db`) is created automatically the first time you run it.

**Want to see it already populated with sample data instead of starting empty?**
Run `python seed.py` once before opening the browser (see "Demo seed data" below).

## How to use it

1. Go to Sign Up, choose **Municipal Inspector**, and create an account. A business key (e.g. `MUNI-4F2A1C`) is generated for you — this is shown after sign up.
2. Give that key to your installers.
3. Installers go to Sign Up, choose **Installer**, and enter the business key to link their account to you.
4. Installers create a "Site" and upload milestones: Site Blueprint, Site Photos, Wiring System Diagram, Grid Connection Sign-off.
5. Log in as the inspector to review each milestone and Approve or Reject it (with an optional note).

## New features

- **Progress bars** — every site shows a visual progress bar (% of the 4 milestone types currently approved). Shown on the installer dashboard, inspector dashboard, per-installer progress page, and the site detail page.
- **Per-installer progress page** — from the inspector dashboard, click "View Progress" next to an installer to see their site count, average progress, and pending/rejected counts.
- **Site deletion + PDF report** — on a site's detail page (inspector view), click "Download Summary Report (PDF)" to save a report before deleting, then "Delete Site" to remove it. Deleting a site removes it (and its milestones) from the installer's account too, since it's the same shared database.
- **Forgot password** — at sign up, each user picks a security question and answer. On the login page, "Forgot password?" leads to a two-step flow: enter your email, answer your security question, then set a new password.
- **Multi-file milestones** — each milestone upload can include several files at once (e.g. multiple site photos), not just one.
- **Persistent file storage when deployed** — once `CLOUDINARY_URL` is set (see deployment steps below), uploaded files are stored on Cloudinary instead of the local disk, so they survive Render restarts. No setup needed for local testing — it falls back to the local `uploads/` folder automatically.
- **Comment threads** — every milestone has its own discussion thread, so the installer and inspector can go back and forth (a rejection reason is automatically posted as the first comment).
- **In-app notifications** — a 🔔 bell in the top bar shows unread updates: new installer sign-ups, new uploads, approvals/rejections, and new comments. Click it to see the list (marks everything as read).
- **Profile & settings page** — click your name in the top bar to update your display name or change your password.
- **Dashboard charts** — both dashboards show a simple bar chart of Approved/Pending/Rejected milestone counts.
- **Search & sort** — both dashboards have a search box and a sort dropdown (by name, progress, or newest/oldest) that filter and reorder the site table instantly, no page reload.
- **Demo seed data** — run `python seed.py` to fill the database with sample inspectors, installers, sites, and milestones in different states, so the app looks populated right away instead of empty. Run `python seed.py --reset` to wipe and reseed. Sample login: `inspector@demo.local` / `installer1@demo.local` / `installer2@demo.local`, all with password `password123`.

## How the data fits together (ER diagram)

```mermaid
erDiagram
    USER ||--o{ PROJECT : "installer owns"
    USER ||--o{ PROJECT : "inspector oversees"
    USER ||--o{ USER : "inspector links installers"
    PROJECT ||--o{ MILESTONE : "has"
    MILESTONE ||--o{ MILESTONE_FILE : "has"
    MILESTONE ||--o{ MILESTONE_COMMENT : "has"
    USER ||--o{ NOTIFICATION : "receives"

    USER {
        int id
        string name
        string email
        string role "inspector or installer"
        string business_key "inspector only"
        int inspector_id "installer only, FK to USER"
    }
    PROJECT {
        int id
        string site_name
        string address
        int installer_id
        int inspector_id
    }
    MILESTONE {
        int id
        string milestone_type
        string status "pending, approved, rejected"
        string note
    }
    MILESTONE_FILE {
        int id
        string file_path
        string original_name
    }
    MILESTONE_COMMENT {
        int id
        string author_name
        string author_role
        string body
    }
    NOTIFICATION {
        int id
        string message
        string link
        bool is_read
    }
```

(GitHub and most Markdown viewers render this automatically. If yours doesn't, any online "Mermaid live editor" will render it by pasting the code above.)

## Deploying it online (real link + real database + persistent files)

This gives you a real public link (e.g. `your-app.onrender.com`), a real
database, and file storage that all survive restarts — not just something
that works on your own laptop.

**Part 1 — Create the free database (Neon)**

1. Go to [neon.com](https://neon.com) and sign up (free, no credit card).
2. Create a new project. Neon gives you a **connection string** that looks like:
   `postgresql://user:password@host/dbname?sslmode=require`
3. Copy that connection string — you'll paste it into Render in Part 3.

**Part 2 — Create free file storage (Cloudinary)**

Render's free plan doesn't keep uploaded files (blueprints/photos/diagrams)
across restarts — only the database does. Cloudinary solves this by storing
those files somewhere permanent instead.

1. Go to [cloudinary.com](https://cloudinary.com) and sign up (free tier is plenty for this).
2. On your Cloudinary dashboard, copy the **API Environment variable** — it looks like:
   `CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>`
3. Keep that for Part 3.

(If you skip this part, the app still works — it just falls back to
storing files locally, which Render may clear on restart. Fine for local
testing, not ideal for a real deployed link.)

**Part 3 — Deploy the app (Render)**

1. Put this project's code in a GitHub repository (create one on
   [github.com](https://github.com), then upload these files to it).
2. Go to [render.com](https://render.com) and sign up (free, no credit card).
3. Click **New +** → **Web Service**, and connect your GitHub repo.
4. Render should auto-detect Python. If asked:
   - **Build Command:** `pip install -r requirements.txt -r requirements-postgres.txt`
     (the second file adds the Postgres driver and Cloudinary client, which are only needed once deployed — your laptop keeps using plain `pip install -r requirements.txt` with SQLite and local file storage)
   - **Start Command:** `gunicorn app:app` (already set via the included `Procfile`)
5. Under **Environment Variables**, add:
   - `DATABASE_URL` = the Neon connection string from Part 1
   - `CLOUDINARY_URL` = the value from Part 2
   - `SECRET_KEY` = any random text (e.g. `mySuperSecretKey123`)
6. Click **Create Web Service**. After a minute or two, Render gives you a
   live link like `https://solar-inspect-system.onrender.com`.

That's it — that link is real, shareable, saves to a real database, and
keeps uploaded files permanently through Cloudinary. Anyone who opens it can
sign up and use it, the same way a normal website works.

## Notes

- This is a simple starting version: one file for all backend logic (`app.py`), plain HTML templates, and a small CSS file — no build tools or frameworks needed.
- Uploaded files are stored in the local `uploads/` folder during development, or on Cloudinary once `CLOUDINARY_URL` is set (see deployment steps above) — either way, they're viewed through a link on each milestone.
- PDF reports are generated with ReportLab, plain formatting, no decorative design.
- For a real deployment, change `SECRET_KEY` in `app.py` and consider a real "forgot password" email flow instead of security questions.
