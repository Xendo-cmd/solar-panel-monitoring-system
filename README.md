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

## Deploying it online (real link + real database)

This gives you a real public link (e.g. `your-app.onrender.com`) and a real
database that everyone's uploads and approvals are saved to permanently —
not just on your own laptop.

**Part 1 — Create the free database (Neon)**

1. Go to [neon.com](https://neon.com) and sign up (free, no credit card).
2. Create a new project. Neon gives you a **connection string** that looks like:
   `postgresql://user:password@host/dbname?sslmode=require`
3. Copy that connection string — you'll paste it into Render in Part 2.

**Part 2 — Deploy the app (Render)**

1. Put this project's code in a GitHub repository (create one on
   [github.com](https://github.com), then upload these files to it).
2. Go to [render.com](https://render.com) and sign up (free, no credit card).
3. Click **New +** → **Web Service**, and connect your GitHub repo.
4. Render should auto-detect Python. If asked:
   - **Build Command:** `pip install -r requirements.txt -r requirements-postgres.txt`
     (the second file adds the Postgres driver, which is only needed once deployed — your laptop keeps using plain `pip install -r requirements.txt` with SQLite)
   - **Start Command:** `gunicorn app:app` (already set via the included `Procfile`)
5. Under **Environment Variables**, add:
   - `DATABASE_URL` = the Neon connection string from Part 1
   - `SECRET_KEY` = any random text (e.g. `mySuperSecretKey123`)
6. Click **Create Web Service**. After a minute or two, Render gives you a
   live link like `https://solar-inspect-system.onrender.com`.

That's it — that link is real, shareable, and saves to a real database.
Anyone who opens it can sign up and use it, and all the data is shared and
kept, the same way a normal website works.

**Permanent file storage:** When `CLOUDINARY_URL` is configured, uploaded
blueprints, photos, and diagrams are stored in Cloudinary and their secure
URLs are saved in the database. The app still uses the local `uploads/`
folder automatically when running on your laptop without Cloudinary.

## Notes

- This is a simple starting version: one file for all backend logic (`app.py`), plain HTML templates, and a small CSS file — no build tools or frameworks needed.
- Uploaded files are stored in the `uploads/` folder and can be viewed through a link on each milestone.
- PDF reports are generated with ReportLab, plain formatting, no decorative design.
- For a real deployment, change `SECRET_KEY` in `app.py`, use a production server (e.g. gunicorn), and consider a real "forgot password" email flow instead of security questions.
