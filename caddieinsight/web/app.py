"""The CaddieInsight v2 web app.

    python -m uvicorn --factory caddieinsight.web.app:create_app

Every page renders complete without JavaScript; the only script the app
ships is the service-worker registration. Session auth is a signed cookie
(``auth.py``); persistence is one SQLite file (``store.py``).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import __version__, bag as catalogue
from ..caddie import recommend
from ..gapping import OVERLAP, WIDE_GAP, analyze
from ..store import Store
from .auth import SESSION_COOKIE, SESSION_DAYS, sign_session, verify_session

PACKAGE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"

MIN_CARRY, MAX_CARRY = 5.0, 400.0

# Notices survive a redirect as a ?msg= key so no-JS flows still get
# feedback. Only keys named here ever render — the query string cannot
# inject copy.
NOTICES = {
    "welcome": "Welcome to the clubhouse. Pick the clubs you carry.",
    "bag-saved": "Bag saved.",
    "shots-logged": "Shots logged. Your numbers just got more honest.",
    "bad-carries": (
        "Could not read those carries — numbers between 5 and 400, "
        "separated by spaces."
    ),
    "pick-club": "Pick a club before logging carries.",
    "posted": "Posted to the clubhouse.",
    "empty-post": "A post needs words in it.",
    "comment-added": "Comment added.",
    "settings-saved": "Settings saved.",
    "signed-out": "Signed out. Play well.",
    "bad-login": "That email and password do not match.",
    "email-taken": "That email already has an account — sign in instead.",
    "signup-invalid": (
        "Name, a real email and a password of 8+ characters, please."
    ),
    "bad-target": "Give the caddie a yardage between 5 and 400.",
    "private-bag": "That member keeps their bag private.",
}


def create_app() -> FastAPI:
    app = FastAPI(title="CaddieInsight v2", version=__version__)
    store = Store(os.environ.get("CADDIE_DB", "caddieinsight.db"))
    secret = os.environ.get("CADDIE_SECRET", "").encode() or secrets.token_bytes(32)

    jinja = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["j2", "html"]),
    )

    def fmt_num(value) -> str:
        if value is None:
            return "—"
        return f"{value:g}"

    def ago(moment: datetime) -> str:
        delta = datetime.utcnow() - moment
        seconds = int(delta.total_seconds())
        if seconds < 90:
            return "just now"
        minutes = seconds // 60
        if minutes < 90:
            return f"{minutes} min ago"
        hours = minutes // 60
        if hours < 36:
            return f"{hours} h ago"
        days = hours // 24
        if days < 45:
            return f"{days} d ago"
        return moment.strftime("%b %Y")

    jinja.filters["num"] = fmt_num
    jinja.filters["ago"] = ago
    jinja.globals["catalogue"] = catalogue
    jinja.globals["version"] = __version__

    def current_user(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return None
        user_id = verify_session(secret, token)
        if user_id is None:
            return None
        return store.user_by_id(user_id)

    def render(
        request: Request, template: str, status_code: int = 200, **context
    ) -> HTMLResponse:
        context.setdefault("user", current_user(request))
        context["path"] = request.url.path
        msg_key = request.query_params.get("msg", "")
        context["notice"] = NOTICES.get(msg_key)
        html = jinja.get_template(template).render(**context)
        return HTMLResponse(html, status_code=status_code)

    def login_redirect(request: Request) -> RedirectResponse:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)

    def set_session(response: RedirectResponse, request: Request, user_id: int):
        response.set_cookie(
            SESSION_COOKIE,
            sign_session(secret, user_id),
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )

    # ---- shell -----------------------------------------------------------

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"ok": True, "version": __version__})

    @app.get("/manifest.webmanifest")
    def manifest():
        return JSONResponse(
            {
                "name": "CaddieInsight",
                "short_name": "CaddieInsight",
                "description": "The yardage book for your bag.",
                "start_url": "/bag",
                "display": "standalone",
                "background_color": "#f2f2f3",
                "theme_color": "#f2f2f3",
                "icons": [
                    {
                        "src": "/static/brand/pwa-icon-192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                    },
                    {
                        "src": "/static/brand/pwa-icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                    },
                    {
                        "src": "/static/brand/pwa-icon-maskable-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
            },
            media_type="application/manifest+json",
        )

    @app.get("/service-worker.js")
    def service_worker():
        return FileResponse(
            STATIC_DIR / "service-worker.js", media_type="text/javascript"
        )

    # ---- landing and auth ------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        if current_user(request):
            return RedirectResponse("/bag", status_code=303)
        return render(request, "landing.html.j2")

    @app.get("/signup", response_class=HTMLResponse)
    def signup_form(request: Request):
        if current_user(request):
            return RedirectResponse("/bag", status_code=303)
        return render(request, "signup.html.j2")

    @app.post("/signup")
    async def signup(request: Request):
        form = await request.form()
        name = str(form.get("display_name", "")).strip()
        email = str(form.get("email", "")).strip().lower()
        password = str(form.get("password", ""))
        if not name or "@" not in email or len(password) < 8:
            return RedirectResponse("/signup?msg=signup-invalid", status_code=303)
        if store.user_by_email(email):
            return RedirectResponse("/login?msg=email-taken", status_code=303)
        user = store.create_user(email, name, password)
        response = RedirectResponse("/bag/setup?msg=welcome", status_code=303)
        set_session(response, request, user.id)
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if current_user(request):
            return RedirectResponse("/bag", status_code=303)
        return render(
            request,
            "login.html.j2",
            request_next=request.query_params.get("next", ""),
        )

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        user = store.authenticate(
            str(form.get("email", "")), str(form.get("password", ""))
        )
        if not user:
            return RedirectResponse("/login?msg=bad-login", status_code=303)
        next_path = str(form.get("next", "")) or "/bag"
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/bag"
        response = RedirectResponse(next_path, status_code=303)
        set_session(response, request, user.id)
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/?msg=signed-out", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    # ---- the bag ---------------------------------------------------------

    @app.get("/bag", response_class=HTMLResponse)
    def bag(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        rungs = store.rungs(user.id)
        if not rungs:
            return RedirectResponse("/bag/setup?msg=welcome", status_code=303)
        measured = [r for r in rungs if r.number.carry is not None]
        return render(
            request,
            "bag.html.j2",
            user=user,
            rungs=rungs,
            measured_count=len(measured),
            shot_total=store.shot_count(user.id),
        )

    @app.get("/bag/setup", response_class=HTMLResponse)
    def bag_setup(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        current = set(store.bag_keys(user.id)) or set(catalogue.DEFAULT_BAG)
        return render(request, "bag_setup.html.j2", user=user, current=current)

    @app.post("/bag/setup")
    async def bag_setup_save(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        form = await request.form()
        store.set_bag(user.id, [str(k) for k in form.getlist("clubs")])
        return RedirectResponse("/bag?msg=bag-saved", status_code=303)

    # ---- the range log ---------------------------------------------------

    def parse_carries(raw: str) -> list[float] | None:
        parts = raw.replace(",", " ").split()
        if not parts:
            return None
        carries = []
        for part in parts:
            try:
                value = float(part)
            except ValueError:
                return None
            if not (MIN_CARRY <= value <= MAX_CARRY):
                return None
            carries.append(value)
        return carries

    @app.get("/range", response_class=HTMLResponse)
    def range_log(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        return render(
            request,
            "range.html.j2",
            user=user,
            bag_keys=store.bag_keys(user.id),
            recent=store.recent_shots(user.id),
        )

    @app.post("/range")
    async def range_log_save(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        form = await request.form()
        club_key = str(form.get("club", "")).upper()
        if club_key not in store.bag_keys(user.id):
            return RedirectResponse("/range?msg=pick-club", status_code=303)
        carries = parse_carries(str(form.get("carries", "")))
        if not carries:
            return RedirectResponse("/range?msg=bad-carries", status_code=303)
        store.log_shots(
            user.id, club_key, carries, note=str(form.get("note", "")).strip()
        )
        return RedirectResponse("/range?msg=shots-logged", status_code=303)

    # ---- gapping ---------------------------------------------------------

    @app.get("/gapping", response_class=HTMLResponse)
    def gapping(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        report = analyze(store.rungs(user.id))
        max_carry = (
            report.ladder[0].number.carry if report.ladder else None
        )
        return render(
            request,
            "gapping.html.j2",
            user=user,
            report=report,
            max_carry=max_carry,
            wide_gap=WIDE_GAP,
            overlap=OVERLAP,
        )

    # ---- the caddie ------------------------------------------------------

    def parse_float(raw: str | None, default: float) -> float | None:
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except ValueError:
            return None

    @app.get("/caddie", response_class=HTMLResponse)
    def caddie(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        params = request.query_params
        result = None
        form = {"target": "", "elevation": "0", "wind": "0", "temp": "70"}
        if "target" in params:
            target = parse_float(params.get("target"), 0.0)
            elevation = parse_float(params.get("elevation"), 0.0)
            wind = parse_float(params.get("wind"), 0.0)
            temp = parse_float(params.get("temp"), 70.0)
            valid = (
                target is not None
                and elevation is not None
                and wind is not None
                and temp is not None
                and MIN_CARRY <= target <= MAX_CARRY
            )
            if not valid:
                return RedirectResponse("/caddie?msg=bad-target", status_code=303)
            form = {
                "target": f"{target:g}",
                "elevation": f"{elevation:g}",
                "wind": f"{wind:g}",
                "temp": f"{temp:g}",
            }
            result = recommend(
                store.rungs(user.id),
                target,
                elevation_ft=elevation,
                wind_mph=wind,
                temp_f=temp,
            )
        return render(
            request, "caddie.html.j2", user=user, result=result, form=form
        )

    # ---- the clubhouse ---------------------------------------------------

    @app.get("/clubhouse", response_class=HTMLResponse)
    def clubhouse(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        return render(
            request,
            "clubhouse.html.j2",
            user=user,
            posts=store.feed(user.id),
            shared=store.shared_bags(),
        )

    @app.post("/clubhouse/post")
    async def clubhouse_post(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        form = await request.form()
        body = str(form.get("body", "")).strip()[:500]
        if not body:
            return RedirectResponse("/clubhouse?msg=empty-post", status_code=303)
        post_id = store.create_post(user.id, body)
        return RedirectResponse(f"/clubhouse/p/{post_id}?msg=posted", status_code=303)

    @app.get("/clubhouse/p/{post_id}", response_class=HTMLResponse)
    def clubhouse_thread(request: Request, post_id: int):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        post = store.post(post_id, user.id)
        if not post:
            return render(request, "missing.html.j2", status_code=404, user=user)
        return render(
            request,
            "post.html.j2",
            user=user,
            post=post,
            comments=store.comments_for(post_id),
        )

    @app.post("/clubhouse/p/{post_id}/comment")
    async def clubhouse_comment(request: Request, post_id: int):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        if not store.post(post_id, user.id):
            return render(request, "missing.html.j2", status_code=404, user=user)
        form = await request.form()
        body = str(form.get("body", "")).strip()[:500]
        if body:
            store.add_comment(post_id, user.id, body)
        return RedirectResponse(
            f"/clubhouse/p/{post_id}?msg=comment-added", status_code=303
        )

    @app.post("/clubhouse/p/{post_id}/tap")
    def clubhouse_tap(request: Request, post_id: int):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        if not store.post(post_id, user.id):
            return render(request, "missing.html.j2", status_code=404, user=user)
        store.toggle_tap(post_id, user.id)
        back = request.headers.get("referer", f"/clubhouse/p/{post_id}")
        if not back.startswith(str(request.base_url).rstrip("/")):
            back = f"/clubhouse/p/{post_id}"
        return RedirectResponse(back, status_code=303)

    @app.get("/clubhouse/bags", response_class=HTMLResponse)
    def bag_rack(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        shared = store.shared_bags()
        racks = [
            (member, analyze(store.rungs(member.id)).ladder)
            for member in shared
        ]
        return render(request, "bags.html.j2", user=user, racks=racks)

    @app.get("/clubhouse/bags/{member_id}", response_class=HTMLResponse)
    def bag_card(request: Request, member_id: int):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        member = store.user_by_id(member_id)
        if not member:
            return render(request, "missing.html.j2", status_code=404, user=user)
        if not member.share_bag and member.id != user.id:
            return RedirectResponse(
                "/clubhouse/bags?msg=private-bag", status_code=303
            )
        report = analyze(store.rungs(member.id))
        max_carry = report.ladder[0].number.carry if report.ladder else None
        return render(
            request,
            "bag_card.html.j2",
            user=user,
            member=member,
            report=report,
            max_carry=max_carry,
        )

    # ---- settings --------------------------------------------------------

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        return render(request, "settings.html.j2", user=user)

    @app.post("/settings")
    async def settings_save(request: Request):
        user = current_user(request)
        if not user:
            return login_redirect(request)
        form = await request.form()
        name = str(form.get("display_name", "")).strip()
        store.update_profile(
            user.id,
            display_name=name or user.display_name,
            home_course=str(form.get("home_course", "")).strip(),
            share_bag=form.get("share_bag") == "on",
        )
        return RedirectResponse("/settings?msg=settings-saved", status_code=303)

    return app
