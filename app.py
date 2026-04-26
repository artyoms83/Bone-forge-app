import os
import json
import base64
import io
import re
import hashlib
import secrets
import time
import uuid
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, flash, Response,
    stream_with_context, send_file
)
from dotenv import load_dotenv
import anthropic
import requests
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

load_dotenv()

import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

import resend
resend.api_key = os.getenv("RESEND_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@boneforge.dev")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PRICES = {
    "creator": "price_1TJO2PRvRmxEBkoDE6KnLFaI",
    "pro": "price_1TJO2QRvRmxEBkoDNBCMAhKG",
    "founding_member": "price_1TJO2MRvRmxEBkoDhqw6M7Hh",
}

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")


def is_owner():
    return session.get("email", "") == OWNER_EMAIL

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "boneforge_secret_2026")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "forge2026")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if create_client and SUPABASE_URL and SUPABASE_KEY else None

# ---------------------------------------------------------------------------
# Supabase database helpers
# ---------------------------------------------------------------------------

def db_get_user(email):
    if not supabase:
        print("Supabase client is None - check SUPABASE_URL and SUPABASE_KEY")
        return None
    try:
        result = supabase.table("users").select("*").eq("email", email).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"db_get_user error: {e}")
        return None

def db_create_user(email, password_hash, tier="free"):
    if not supabase:
        print("Supabase client is None - check SUPABASE_URL and SUPABASE_KEY")
        return False
    try:
        supabase.table("users").insert({
            "email": email,
            "password_hash": password_hash,
            "tier": tier
        }).execute()
        return True
    except Exception as e:
        print(f"db_create_user error: {e}")
        return False

def db_get_usage(email):
    if not supabase: return None
    try:
        result = supabase.table("usage").select("*").eq("email", email).execute()
        return result.data[0] if result.data else None
    except: return None

def db_update_usage(email, videos_generated, month):
    if not supabase: return
    try:
        supabase.table("usage").upsert({
            "email": email,
            "videos_generated": videos_generated,
            "month": month
        }).execute()
    except: pass

def db_get_reference(character_key):
    if not supabase: return None
    try:
        result = supabase.table("reference_images").select("*").eq("character_key", character_key).execute()
        return result.data[0]["image_data"] if result.data else None
    except: return None

def db_save_reference(character_key, image_data):
    if not supabase: return
    try:
        supabase.table("reference_images").upsert({
            "character_key": character_key,
            "image_data": image_data
        }).execute()
    except: pass

def db_get_characters(email):
    if not supabase: return []
    try:
        result = supabase.table("characters").select("*").eq("email", email).execute()
        return result.data or []
    except Exception as e:
        print(f"db_get_characters error: {e}")
        return []

def db_create_character(email, name, reference_image, prompt_prefix):
    if not supabase: return False
    try:
        supabase.table("characters").insert({
            "email": email,
            "name": name,
            "reference_image": reference_image,
            "prompt_prefix": prompt_prefix
        }).execute()
        return True
    except Exception as e:
        print(f"db_create_character error: {e}")
        return False

def db_delete_character(character_id, email):
    if not supabase: return False
    try:
        supabase.table("characters").delete().eq("id", character_id).eq("email", email).execute()
        return True
    except Exception as e:
        print(f"db_delete_character error: {e}")
        return False

def db_save_history(email, concept, script, image_prompts, animation_directives, character_id, formula, word_count):
    if not supabase: return None
    try:
        result = supabase.table("history").insert({
            "email": email,
            "concept": concept,
            "script": script,
            "image_prompts": image_prompts,
            "animation_directives": animation_directives,
            "character_id": character_id,
            "formula": formula,
            "word_count": word_count
        }).execute()
        rows = result.data or []
        return rows[0].get("id") if rows else None
    except Exception as e:
        print(f"db_save_history error: {e}")
        return None

def db_save_score(history_id, email, score):
    if not supabase or not history_id: return False
    try:
        supabase.table("history").update({"score": score}).eq("id", history_id).eq("email", email).execute()
        return True
    except Exception as e:
        print(f"db_save_score error: {e}")
        return False

def db_get_history(email, limit=20):
    if not supabase: return []
    try:
        result = supabase.table("history").select("*").eq("email", email).order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        print(f"db_get_history error: {e}")
        return []

def db_delete_history(history_id, email):
    if not supabase: return False
    try:
        supabase.table("history").delete().eq("id", history_id).eq("email", email).execute()
        return True
    except Exception as e:
        print(f"db_delete_history error: {e}")
        return False

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def compress_image_if_needed(image_data, max_bytes=4_000_000):
    """Only compress if image is over 4MB. Preserves resolution unless it
    exceeds 2048x2048. Re-encodes as JPEG at quality 85 for high fidelity.
    Logs before/after size and dimensions.
    """
    try:
        from PIL import Image

        if "," in image_data:
            _, b64 = image_data.split(",", 1)
        else:
            b64 = image_data

        img_bytes = base64.b64decode(b64)
        original_size = len(img_bytes)

        if original_size <= max_bytes:
            print(f"[compress] {original_size} bytes <= {max_bytes} — leaving uncompressed")
            return image_data

        img = Image.open(io.BytesIO(img_bytes))
        original_dims = img.size
        img = img.convert("RGB")

        max_dim = 2048
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim))
            print(f"[compress] downscaling {original_dims[0]}x{original_dims[1]} -> {img.size[0]}x{img.size[1]} (>2048 limit)")
        else:
            print(f"[compress] preserving dimensions {original_dims[0]}x{original_dims[1]} (<=2048)")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        new_size = buffer.tell()
        compressed_b64 = base64.b64encode(buffer.getvalue()).decode()

        print(f"[compress] {original_size} bytes ({original_dims[0]}x{original_dims[1]}) -> {new_size} bytes ({img.size[0]}x{img.size[1]}) at q=85")
        return f"data:image/jpeg;base64,{compressed_b64}"

    except Exception as e:
        print(f"Compression error: {e}")
        return image_data

# ---------------------------------------------------------------------------
# Character presets — injected into image prompts for consistency
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PREMADE_CHARACTERS = [
    {
        "id": "basic",
        "name": "Basic Skeleton",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, photorealistic environment, natural lighting, realistic textures",
        "thumbnail": "/static/characters/thumbnails/basic.png"
    },
    {
        "id": "napoleon",
        "name": "Napoleon Skeleton",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, Napoleonic French infantry uniform, navy blue coat, red facings, white crossbelt, shako hat",
        "thumbnail": "/static/characters/thumbnails/napoleon.png"
    },
    {
        "id": "knight",
        "name": "Knight Skeleton",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, full medieval plate armor, skull face fully exposed",
        "thumbnail": "/static/characters/thumbnails/knight.png"
    },
    {
        "id": "viking",
        "name": "Viking Skeleton",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, Viking warrior outfit, brown fur cloak over chainmail, horned iron helmet, leather arm wraps",
        "thumbnail": "/static/characters/thumbnails/viking.png"
    },
    {
        "id": "roman",
        "name": "Roman Centurion",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, Roman centurion armor, burgundy cape, ornate bronze chest plate, studded red skirt, metal greaves, crested helmet with red mohawk",
        "thumbnail": "/static/characters/thumbnails/roman.png"
    },
    {
        "id": "samurai",
        "name": "Samurai Skeleton",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, traditional Japanese samurai armor, red and black lacquered plates, horned kabuto helmet, katana",
        "thumbnail": "/static/characters/thumbnails/samurai.png"
    },
    {
        "id": "pharaoh",
        "name": "Egyptian Pharaoh",
        "prompt_prefix": "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, ancient Egyptian pharaoh outfit, white linen kilt, golden nemes headdress with uraeus cobra, crook and flail",
        "thumbnail": "/static/characters/thumbnails/pharaoh.png"
    },
]

# Build lookup dict from premade list
CHARACTER_PRESETS = {c["id"]: {"name": c["name"], "prompt_prefix": c["prompt_prefix"]} for c in PREMADE_CHARACTERS}

def load_premade_reference(character_id):
    path = os.path.join(BASE_DIR, "static", "characters", "references", f"{character_id}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{b64}"
    return None

PROFESSION_BASE_PREFIX = "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, photorealistic environment, natural lighting, realistic textures"

IMAGE_MODELS = {
    "nano_banana": "google/gemini-3-pro-image-preview",
    "nano_banana_2": "google/gemini-3.1-flash-image-preview",
    "nano_banana_regular": "google/gemini-2.5-flash-image"
}

# ---------------------------------------------------------------------------
# Video caps
# ---------------------------------------------------------------------------

VIDEO_CAPS = {
    "free": 0,
    "starter": 15,
    "creator": 20,
    "pro": 50,
    "founding_member": 50,
}

TIER_FEATURES = {
    "free": {"formula_a": False, "characters": 0, "history": False},
    "creator": {"formula_a": True, "characters": 3, "history": True},
    "pro": {"formula_a": True, "characters": 6, "history": True},
    "founding_member": {"formula_a": True, "characters": 6, "history": True},
}

CHARACTER_LIMITS = {
    "starter": 1,
    "creator": 5,
    "pro": 999,
    "founding_member": 999,
}


# ---------------------------------------------------------------------------
# What's New — static changelog shown in the sidebar modal.
# Most recent first. Add new entries at the top.
# ---------------------------------------------------------------------------

UPDATES = [
    {
        "date": "2026-04-23",
        "title": "Regenerate button fixed",
        "description": "Regenerating now correctly uses your original concept and formula. You can also compare the previous and new script side by side.",
    },
    {
        "date": "2026-04-23",
        "title": "Better skeleton character eyes",
        "description": "Image prompts now generate more consistent 3D-looking eyes across every shot.",
    },
    {
        "date": "2026-04-22",
        "title": "Tone control + clean language mode",
        "description": "New tone toggle lets you pick between deadpan, comedic, serious, or clean language to match your channel voice.",
    },
    {
        "date": "2026-04-22",
        "title": "Reference image shortcut",
        "description": "When a character is selected, prompts now use (use reference) tag to keep outputs shorter and faster.",
    },
]

WHATS_NEW_LIMIT = 3


@app.context_processor
def inject_sidebar_context():
    if not session.get("authenticated"):
        return {}
    email = session.get("email", "")
    tier = session.get("tier", "free")
    video_cap = VIDEO_CAPS.get(tier, 0)
    videos_used = 0
    try:
        usage = db_get_usage(email)
        current_month = datetime.utcnow().strftime("%Y-%m")
        if usage and usage.get("month") == current_month:
            videos_used = usage.get("videos_generated", 0)
    except Exception:
        pass
    whats_new = UPDATES[:WHATS_NEW_LIMIT]
    latest_id = ""
    if whats_new:
        latest_id = f"{whats_new[0]['date']}|{whats_new[0]['title']}"
    return {
        "tier": tier,
        "videos_used": videos_used,
        "video_cap": video_cap,
        "owner_mode": is_owner(),
        "whats_new": whats_new,
        "whats_new_latest_id": latest_id,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def require_paid_tier():
    if is_owner():
        return None
    tier = session.get("tier", "free")
    if tier not in ["creator", "pro", "founding_member"]:
        return redirect(url_for("pricing_page"))
    return None


@app.route("/", methods=["GET"])
def index():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if email:
            # Email + password auth
            user = db_get_user(email)
            if user and user.get("password_hash") == hash_password(password):
                session["authenticated"] = True
                session["email"] = email
                tier = user.get("tier", "free")
                session["tier"] = tier
                if tier not in ["creator", "pro", "founding_member"]:
                    return redirect(url_for("pricing_page"))
                else:
                    return redirect(url_for("dashboard"))
            else:
                error = "Invalid email or password."
        else:
            # Legacy single-password fallback
            if password == APP_PASSWORD:
                session["authenticated"] = True
                return redirect(url_for("dashboard"))
            else:
                error = "Wrong password. Try again."

    return render_template("login.html", error=error, mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        try:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")

            print(f"Register attempt: email={email}, password_len={len(password)}")

            if not email or not password:
                error = "Email and password are required."
            elif "@" not in email or "." not in email:
                error = "Enter a valid email address."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            elif password != confirm:
                error = "Passwords don't match."
            else:
                existing = db_get_user(email)
                print(f"Existing user check: {existing}")
                if existing:
                    error = "An account with that email already exists."
                else:
                    success = db_create_user(email, hash_password(password))
                    print(f"Create user result: {success}")
                    if success:
                        session["authenticated"] = True
                        session["email"] = email
                        session["tier"] = "free"
                        return redirect(url_for("pricing_page"))
                    else:
                        error = "Registration failed. Please try again."
        except Exception as e:
            print(f"Register route error: {e}")
            error = f"Unexpected error: {str(e)}"

    return render_template("login.html", error=error, mode="register")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    data = request.form
    email = data.get("email", "").strip().lower()

    if not email:
        return render_template("forgot_password.html",
            error="Email is required")

    user = db_get_user(email)

    # Always show success even if email not found (prevents enumeration)
    if user:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)

        try:
            if supabase:
                supabase.table("password_resets").insert({
                    "email": email,
                    "token": token,
                    "expires_at": expires_at.isoformat(),
                    "used": False
                }).execute()

            reset_url = f"https://boneforge.dev/reset-password?token={token}"

            resend.Emails.send({
                "from": f"BoneForge <{SENDER_EMAIL}>",
                "to": email,
                "subject": "Reset your BoneForge password",
                "html": f"""
                <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;background:#0a0806;color:#b8b3ab;padding:40px;border-radius:16px;">
                    <img src="https://boneforge.studio/boneforge-logo-removebg.png" width="48" style="margin-bottom:24px">
                    <h2 style="color:#f0ece6;font-size:1.4rem;margin:0 0 12px">Reset your password</h2>
                    <p style="margin:0 0 28px;line-height:1.6">
                        Click the button below to reset your BoneForge password.
                        This link expires in 1 hour.
                    </p>
                    <a href="{reset_url}"
                       style="display:inline-block;background:#d4580a;color:#fff;font-weight:700;padding:14px 32px;border-radius:50px;text-decoration:none;font-size:0.9rem;">
                        Reset Password
                    </a>
                    <p style="margin:28px 0 0;font-size:0.8rem;color:#6e6960;">
                        If you didn't request this, ignore this email.
                        Your password won't change.
                    </p>
                </div>
                """
            })
        except Exception as e:
            print(f"Password reset error: {e}")

    return render_template("forgot_password.html",
        success="If that email exists, a reset link is on its way.")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token", "") or request.form.get("token", "")

    if not token:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("reset_password.html", token=token)

    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not password or len(password) < 6:
        return render_template("reset_password.html",
            token=token, error="Password must be at least 6 characters.")

    if password != confirm:
        return render_template("reset_password.html",
            token=token, error="Passwords don't match.")

    try:
        if supabase:
            result = supabase.table("password_resets")\
                .select("*")\
                .eq("token", token)\
                .eq("used", False)\
                .execute()

            if not result.data:
                return render_template("reset_password.html",
                    token=token, error="Invalid or expired reset link.")

            reset = result.data[0]
            expires_at = datetime.fromisoformat(reset["expires_at"])

            if datetime.utcnow() > expires_at:
                return render_template("reset_password.html",
                    token=token, error="Reset link has expired. Request a new one.")

            email = reset["email"]

            supabase.table("users").update({
                "password_hash": hash_password(password)
            }).eq("email", email).execute()

            supabase.table("password_resets").update({
                "used": True
            }).eq("token", token).execute()

            return redirect(url_for("login"))

    except Exception as e:
        print(f"Reset password error: {e}")
        return render_template("reset_password.html",
            token=token, error="Something went wrong. Try again.")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    gate = require_paid_tier()
    if gate: return gate
    tier = session.get("tier", "free")
    is_paid = True
    user = db_get_user(session.get("email", ""))
    onboarded = user.get("onboarded", False) if user else True
    session["onboarded"] = onboarded
    return render_template("dashboard.html", owner_mode=is_owner(), is_paid=is_paid, tier=tier, onboarded=onboarded, tone=session.get("tone", "deadpan"))


@app.route("/usage", methods=["GET"])
@login_required
def get_usage():
    email = session.get("email", "legacy")
    tier = session.get("tier", "founding_member")
    cap = VIDEO_CAPS.get(tier, 30)
    current_month = datetime.now().strftime("%Y-%m")
    usage = db_get_usage(email)
    videos = 0
    if usage and usage.get("month") == current_month:
        videos = usage.get("videos_generated", 0)
    return jsonify({
        "videos_generated": videos,
        "video_cap": cap,
        "tier": tier,
        "owner_mode": is_owner(),
    })


# ---------------------------------------------------------------------------
# System prompt — Formula A: Historical / What If
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are BoneForge — an AI content engine that writes viral short-form video scripts for faceless AI character channels on TikTok and YouTube Shorts.

THE FORMULA:
Open with "What if you [did X] in [historical/extreme setting]?" then follow a time progression: Day 1 → Day 2 → Day 3 → Week 1 → Month 1/6 → Year 1. Each step escalates stakes. You start with nothing and end dominant.

RULES — FOLLOW EXACTLY:
1. SECOND PERSON ONLY. "You" throughout. Never mention the character, skeleton, or any visual element. The viewer is the protagonist.
2. TARGET 280-380 WORDS. Longer narrative format.
3. TIME PROGRESSION STRUCTURE. Use Day 1, Day 2, Day 3, Week 1, Month 1/6, Year 1 as natural checkpoints. Stakes must escalate every step.
4. RECURRING FIGURE. Include the recurring figure specified by the user. They appear once or twice. They ask a weird question or cause a problem. They get dismissed with foul language or physical humor. If recurring figure is "None", skip this entirely.
5. FOUL LANGUAGE ALLOWED. 1-3 times max. Surgical use only — shock, humor, or emphasis. Never gratuitous.
6. ESCALATING STAKES. Day 1 you are nobody. Year 1 you control something.
7. QUIET CLOSER. End with 1-2 lines that recontextualize everything. Understated. No hype. Example: "You didn't just make a business. You filled hungry stomachs."
8. NO CHARACTER MENTION. Never mention skeleton, bones, or any visual character. Pure second person narrative.
9. SENSORY DETAIL. Match smells, sounds, and textures to the historical setting. Make it visceral.
10. PUNCHY SENTENCES AT KEY MOMENTS. Most prose flows naturally but punch key moments with 3-5 word sentences.

RECURRING FIGURE BEHAVIOR:
- Appears once or twice maximum
- Asks a philosophical question OR causes a problem OR tries to steal credit
- Gets dismissed: "You tell him to f*** off", "You tie him up and send him back", "You shove it down his throat", "You hand him over to the guards"
- Story continues without them after dismissal

CHARACTER OUTFIT:
Return a detailed character_outfit field describing exactly what the character wears for this concept. Be specific — include clothing color, logo placement, accessories. Example: "Raising Canes employee uniform, red polo shirt with Canes logo on chest, white visor, black apron"

OUTPUT FORMAT — Return ONLY valid JSON:
{
  "script": "Complete script 280-380 words",
  "word_count": 310,
  "character_outfit": "Detailed outfit description for this concept",
  "image_prompts": ["Prompt 1...", "...exactly 28 prompts"]
}

IMAGE PROMPT RULES — STRICT:

1. VEHICLE/OBJECT SPECIFICITY
Never use generic terms. Always use exact make, model, and color in every single prompt the vehicle appears.
- WRONG: "the car", "the vehicle", "the Hellcat"
- RIGHT: "black Dodge Charger SRT Hellcat"
Always include color + brand + model + variant.

2. SETTING SPECIFICITY
Never say just "desert" or "forest" or "city". Always include time period, location, and atmospheric details.
- WRONG: "desert background"
- RIGHT: "Crusade-era desert battlefield 1191, sandy terrain, distant Jerusalem walls visible, period-accurate Crusader tents and banners, harsh midday sun"
Derive the setting from the script and be specific.

3. CHARACTER-FIRST DEFAULT — CRITICAL
The skeleton character MUST appear in EVERY image prompt by default. This is the protagonist — the viewer is watching them do things. Do NOT omit the skeleton from a prompt unless the scene is clearly one of these b-roll categories:
  a) Environment establishing shot (wide landscape, cityscape, period-setting shot)
  b) Object close-up (the object named in the script shown alone for emphasis)
  c) Reaction shot of ANOTHER named character (Napoleon, Caesar, etc) witnessing the event
  d) Text explicitly labeled "b-roll" or "cutaway" in the script
If in doubt, INCLUDE the skeleton. Default to character shots always.

4. CHARACTER SHOTS (default, ~70% of prompts)
Every character prompt MUST start with the full character prefix provided. Never shorten it. Never summarize it. Environment description comes AFTER the prefix, never before. End with: "9:16 vertical"

5. B-ROLL SHOTS (rare, ~30% of prompts, NEVER more than 2 in a row)
Only use for the four categories listed in rule 3. Never include character descriptions. End with: "no skeleton visible, 9:16 vertical"

6. CHARACTER IN ACTION SHOTS
If the script shows the character interacting with an object (touching, driving, climbing):
- Include full character prefix
- Describe the exact action precisely
- Describe the object with full specificity
- WRONG: "skeleton touching the car"
- RIGHT: "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, [full outfit], pressing both gauntleted hands flat against the hood of the black Dodge Charger SRT Hellcat, expression of cautious wonder"

7. INTERIOR SHOTS WITH CHARACTER
If the character is inside the vehicle:
- Include full character prefix
- Specify exact interior details
- WRONG: "skeleton in the car"
- RIGHT: "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, [full outfit], gripping the leather steering wheel of the black Dodge Charger SRT Hellcat with both gauntleted hands, red stitched seats visible, START button glowing on dashboard"

8. EVERY PROMPT ENDS WITH:
Character shots: "9:16 vertical"
B-roll shots: "no skeleton visible, 9:16 vertical"

9. COUNT & RATIO
Generate exactly 28 prompts. Never generate fewer.
Target ratio: ~70% character shots (19-20 prompts), ~30% b-roll (8-9 prompts max).
NEVER place more than 2 b-roll shots in a row — always break up b-roll with character shots.

ADDITIONAL RULES:
- CRITICAL: Each image prompt must work as a completely standalone photograph. The AI image generator has NO memory of previous images generated.
- When the script involves a named historical figure (Napoleon, Caesar, Alexander, Genghis Khan, pharaohs etc), generate a photorealistic environment shot of that figure in their period-appropriate setting as a reaction/witness shot. Describe their appearance fully in that single prompt. This counts as a b-roll shot.
- When a character outfit changes mid-script (promotion, disguise, transformation), update the character prefix description in all subsequent prompts to reflect the new outfit.
- Art style: dark, cinematic, slightly absurd, photorealistic, high detail.
"""

# ---------------------------------------------------------------------------
# System prompt — Formula B: Named Object (original Gerald/Karen format)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_B = """You are BoneForge — an AI content engine that writes viral short-form video scripts for faceless AI character channels on TikTok and YouTube Shorts.

FORMULA B — NAMED OBJECT — FOLLOW EXACTLY:

1. TARGET 130-180 WORDS. Count every word.
2. CRITICAL — SECOND PERSON ONLY: Use "you/your" throughout. NEVER use third-person references. The viewer IS the character.
3. NAME THE OBJECT BY SENTENCE 2. The object must receive a human name (Gerald, Karen, Ramses, Bjorn, Doris, Franklin, Maverick, etc.) no later than the second sentence.
4. INCLUDE "you do not know what it is" OR equivalent in the first 3 sentences.
5. HEAD FAKE at exactly 60-70% through the script. A sudden tonal shift that subverts what the viewer expects.
6. DEADPAN DRY TONE ONLY. No exclamation marks. No hype language. Ultra short sentences — aim for 3-7 words each.
7. PHILOSOPHICAL OR DEADPAN CLOSER before the CTA. One sentence that recontextualizes everything.
8. THREE OPTION CTA — EXACT FORMAT: "If you want [specific thing], like. If you want [specific thing], follow. If you want [specific thing], share this with someone who [funny specific reason]."

WINNER SCRIPT REFERENCES:

WINNER 1 — Napoleon's Dirt Bike (391k views, 130 words):
"You are Napoleon. You find a dirt bike in 1803. You do not know what it is. You name it Pierre..."

WINNER 2 — Gerald the Nuke (157k views, 138 words):
"You are a retired crossing guard. You find a nuclear warhead in your garden. You do not know what it is. You name it Gerald..."

OUTPUT FORMAT — Return ONLY valid JSON:
{
  "script": "Complete script, 130-180 words, second person throughout",
  "word_count": 137,
  "image_prompts": ["Prompt 1...", "...exactly 18 prompts"]
}

IMAGE PROMPT RULES — STRICT:

1. VEHICLE/OBJECT SPECIFICITY
Never use generic terms. Always use exact make, model, and color in every single prompt the vehicle appears.
- WRONG: "the car", "the vehicle", "the Hellcat"
- RIGHT: "black Dodge Charger SRT Hellcat"
Always include color + brand + model + variant.

2. SETTING SPECIFICITY
Never say just "desert" or "forest" or "city". Always include time period, location, and atmospheric details.
- WRONG: "desert background"
- RIGHT: "Crusade-era desert battlefield 1191, sandy terrain, distant Jerusalem walls visible, period-accurate Crusader tents and banners, harsh midday sun"
Derive the setting from the script and be specific.

3. CHARACTER-FIRST DEFAULT — CRITICAL
The skeleton character MUST appear in EVERY image prompt by default. This is the protagonist — the viewer is watching them do things. Do NOT omit the skeleton from a prompt unless the scene is clearly one of these b-roll categories:
  a) Environment establishing shot (wide landscape, cityscape, period-setting shot)
  b) Object close-up (the object named in the script shown alone for emphasis)
  c) Reaction shot of ANOTHER named character (Napoleon, Caesar, etc) witnessing the event
  d) Text explicitly labeled "b-roll" or "cutaway" in the script
If in doubt, INCLUDE the skeleton. Default to character shots always.

4. CHARACTER SHOTS (default, ~70% of prompts)
Every character prompt MUST start with the full character prefix provided. Never shorten it. Never summarize it. Environment description comes AFTER the prefix, never before. End with: "9:16 vertical"

5. B-ROLL SHOTS (rare, ~30% of prompts, NEVER more than 2 in a row)
Only use for the four categories listed in rule 3. Never include character descriptions. End with: "no skeleton visible, 9:16 vertical"

6. CHARACTER IN ACTION SHOTS
If the script shows the character interacting with an object (touching, driving, climbing):
- Include full character prefix
- Describe the exact action precisely
- Describe the object with full specificity
- WRONG: "skeleton touching the car"
- RIGHT: "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, [full outfit], pressing both gauntleted hands flat against the hood of the black Dodge Charger SRT Hellcat, expression of cautious wonder"

7. INTERIOR SHOTS WITH CHARACTER
If the character is inside the vehicle:
- Include full character prefix
- Specify exact interior details
- WRONG: "skeleton in the car"
- RIGHT: "Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic, [full outfit], gripping the leather steering wheel of the black Dodge Charger SRT Hellcat with both gauntleted hands, red stitched seats visible, START button glowing on dashboard"

8. EVERY PROMPT ENDS WITH:
Character shots: "9:16 vertical"
B-roll shots: "no skeleton visible, 9:16 vertical"

9. COUNT & RATIO
Generate exactly 18 prompts. Never generate fewer.
Target ratio: ~70% character shots (12-13 prompts), ~30% b-roll (5-6 prompts max).
NEVER place more than 2 b-roll shots in a row — always break up b-roll with character shots.

ADDITIONAL RULES:
- CRITICAL: Each image prompt must work as a completely standalone photograph. The AI image generator has NO memory of previous images generated.
- When the script involves a named historical figure (Napoleon, Caesar, Alexander, Genghis Khan, pharaohs etc), generate a photorealistic environment shot of that figure in their period-appropriate setting as a reaction/witness shot. Describe their appearance fully in that single prompt. This counts as a b-roll shot.
- When a character outfit changes mid-script (promotion, disguise, transformation), update the character prefix description in all subsequent prompts to reflect the new outfit.
- Art style: dark, cinematic, slightly absurd, photorealistic, high detail.
"""


# ---------------------------------------------------------------------------
# Generation endpoint
# ---------------------------------------------------------------------------

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    gate = require_paid_tier()
    if gate: return gate

    data = request.get_json()
    concept = data.get("concept", "").strip()
    formula = data.get("formula", "a")
    recurring_figure = data.get("recurring_figure", "socrates")
    character_mode = data.get("character_mode", "library")
    character_preset = data.get("character_preset", "napoleon")
    word_count = data.get("word_count", 180)
    prompt_mode = data.get("prompt_mode", "full")
    tone = data.get("tone", session.get("tone", "deadpan"))
    if tone not in ("deadpan", "comedic", "serious", "clean"):
        tone = "deadpan"
    session["tone"] = tone  # Persist across generations

    if not concept:
        return jsonify({"error": "Concept is required"}), 400

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_key_here":
        return jsonify({"error": "Anthropic API key not configured. Add it to .env"}), 500

    # Tier check
    email = session.get("email", "legacy")
    tier = session.get("tier", "founding_member")
    features = TIER_FEATURES.get(tier, TIER_FEATURES["free"])

    # Video cap check (owner bypasses)
    videos_used = 0
    video_cap = VIDEO_CAPS.get(tier, 0)
    usage_row = db_get_usage(email)
    current_month = datetime.utcnow().strftime("%Y-%m")
    if usage_row and usage_row.get("month") == current_month:
        videos_used = usage_row.get("videos_generated", 0)

    if not is_owner():
        if videos_used >= video_cap:
            return jsonify({"error": f"You've reached your {video_cap} video limit this month. Upgrade to generate more."}), 403

    # Resolve character prefix based on mode
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    if character_mode == "library" and uuid_pattern.match(character_preset):
        # Custom character from My Characters
        email = session.get("email", "")
        chars = db_get_characters(email)
        char = next((c for c in chars if c["id"] == character_preset), None)
        if char:
            character_prompt_prefix = char.get("prompt_prefix", PROFESSION_BASE_PREFIX)
            mode_instruction = ""
        else:
            character_prompt_prefix = PROFESSION_BASE_PREFIX
            mode_instruction = ""
    elif character_mode == "library":
        preset = CHARACTER_PRESETS.get(character_preset, list(CHARACTER_PRESETS.values())[0])
        character_prompt_prefix = preset["prompt_prefix"]
        mode_instruction = ""
    else:  # profession or custom
        character_prompt_prefix = PROFESSION_BASE_PREFIX
        mode_instruction = "\nCharacter mode is PROFESSION AUTO. Append character_outfit to all character image prompts after the base prefix.\n"

    # Select system prompt based on formula
    system_prompt = SYSTEM_PROMPT if formula == "a" else SYSTEM_PROMPT_B

    # Tone instruction — overrides/refines the default voice
    TONE_INSTRUCTIONS = {
        "deadpan": (
            "TONE: DEADPAN (default).\n"
            "Dry, understated, matter-of-fact delivery. No exclamation marks. No hype. "
            "Absurd events described in a flat, unremarkable voice. Trust the concept to carry the humor. "
            "Foul language may appear ONCE at most for impact."
        ),
        "comedic": (
            "TONE: COMEDIC.\n"
            "Punchy, overt jokes with clear setup/punchline rhythm. Looser sentence structure allowed. "
            "Exclamation marks permitted sparingly for emphasis. Absurd details leaned into rather than understated. "
            "The viewer should laugh out loud, not just smirk. One strong profanity for impact is OK."
        ),
        "serious": (
            "TONE: SERIOUS.\n"
            "Formal documentary narration voice over an absurd concept. Measured, weighty sentences. "
            "Treat the ridiculous premise with complete gravity — the humor comes from the contrast between "
            "the dignified voice and the ludicrous events. No exclamation marks. No profanity. "
            "Think David Attenborough narrating nonsense."
        ),
        "clean": (
            "TONE: CLEAN (platform-safe).\n"
            "ZERO profanity. Absolutely no f-words, s-words, or strong language of any kind. "
            "Replace any urge to swear with softer alternatives: 'damn' -> 'darn', 'hell' -> 'heck', "
            "'shit' -> 'crap', 'fuck off' -> 'get lost' or 'buzz off'. Dismissals should be firm but PG. "
            "Keep the dry, deadpan delivery but make the script safe for YouTube Shorts monetization "
            "and TikTok's strictest auto-moderation. No sexual references, no graphic violence descriptions."
        ),
    }
    tone_instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["deadpan"])

    # Prompt mode: full descriptions vs reference shortcut
    if prompt_mode == "reference":
        prefix_instruction = (
            "REFERENCE MODE — OVERRIDE:\n"
            "Do NOT start character image prompts with the full character prefix below. "
            "Instead, begin every CHARACTER shot with the literal string '(use reference) ' "
            "followed by scene-specific details only (action, environment, objects, setting, "
            "lighting, camera angle). The reference image supplies the character's appearance — "
            "do not repeat clothing, eye design, skull, or outfit descriptions. "
            "B-roll shots still follow the standard rules (no skeleton, end with 'no skeleton visible, 9:16 vertical').\n"
            "Example: \"(use reference) sitting on a dirt bike in a muddy Napoleonic battlefield, "
            "smoke drifting across the field, low angle shot, 9:16 vertical\"\n"
            "The reference character for context is:\n"
            f'"{character_prompt_prefix}"\n'
        )
    else:
        prefix_instruction = (
            f"For every character image prompt, begin with this exact prefix:\n"
            f'"{character_prompt_prefix}"\n'
        )

    if formula == "a":
        figure_line = ""
        if recurring_figure and recurring_figure != "none":
            figure_line = (
                f"\nRecurring figure: {recurring_figure}. Work them in per the formula "
                f"— one or two appearances, philosophical question or disruption, "
                f"dismissed with foul language or physical humor.\n"
            )
        else:
            figure_line = "\nDo not include a recurring figure.\n"
        user_message = (
            f"Write a viral short-form video script about this concept: {concept}\n"
            f"{figure_line}{mode_instruction}\n"
            f"{tone_instruction}\n\n"
            f"{prefix_instruction}\n"
            f"Target word count: {word_count} words, stay within 10 words of this target.\n"
            f"Follow the formula exactly. Return ONLY the JSON object."
        )
    else:
        user_message = (
            f"Write a viral short-form video script about this concept: {concept}\n"
            f"{mode_instruction}\n"
            f"{tone_instruction}\n\n"
            f"{prefix_instruction}\n"
            f"Target word count: {word_count} words, stay within 10 words of this target.\n"
            f"Follow Formula B exactly. Return ONLY the JSON object."
        )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = message.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            raw = json_match.group(1).strip()

        result = json.loads(raw)

        # Validate structure
        if "script" not in result:
            return jsonify({"error": "Invalid response format from AI"}), 500

        result.setdefault("image_prompts", [])
        result["target_word_count"] = word_count

        # Increment usage
        db_update_usage(email, videos_used + 1, current_month)

        # Save to history
        history_id = db_save_history(
            email=email,
            concept=concept,
            script=result.get("script", ""),
            image_prompts=result.get("image_prompts", []),
            animation_directives=[],
            character_id=character_preset,
            formula=formula,
            word_count=word_count
        )
        if history_id:
            result["history_id"] = history_id

        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse AI response. Try again."}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Animation directive generation (from image prompts)
# ---------------------------------------------------------------------------

ANIMATION_PROMPT = """You are an animation director for short-form AI-generated videos. You will receive a list of image prompts. For each image prompt, write ONE natural-language animation directive describing how that shot should move.

RULES:
- One natural flowing sentence per directive
- NEVER use the character's name (Napoleon, Caesar, Alexander, etc). Always refer to them as "the skeleton" or "skeleton character"
- EVERY directive featuring the character MUST end with: "eyeballs remain fixed in skull throughout, skeleton character consistent, goofy expression"
- Describe camera movement, what moves, and the feeling of the shot
- No labels like CAMERA: or MOTION: or TRANSITION:
- Example good directive: "Camera slowly pushes in on the skeleton's face as the engine roars to life, jaw dropping in shock, eyeballs remain fixed in skull throughout, skeleton character consistent, goofy expression."
- Example bad directive: "Napoleon reacts to the aircraft starting up"
- For b-roll shots with no character, describe only the environment or object — no consistency tags needed
- EVERY directive MUST end with "no music" as the final two words
- Generate exactly one directive per image prompt, same order

Return ONLY valid JSON:
{
  "animation_directives": ["Directive 1...", "...one per image prompt"]
}"""

@app.route("/generate-animation-prompts", methods=["POST"])
@login_required
def generate_animation_prompts():
    gate = require_paid_tier()
    if gate: return gate

    data = request.get_json()
    image_prompts = data.get("image_prompts", [])

    if not image_prompts:
        return jsonify({"error": "No image prompts provided"}), 400

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_key_here":
        return jsonify({"error": "Anthropic API key not configured."}), 500

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=ANIMATION_PROMPT,
            messages=[{"role": "user", "content": "Generate animation directives for these image prompts:\n\n" + json.dumps(image_prompts)}],
        )

        raw = message.content[0].text.strip()
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            raw = json_match.group(1).strip()

        result = json.loads(raw)
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse AI response. Try again."}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


GRADE_PROMPT_A = """You are a viral script analyst for TikTok/YouTube Shorts. Grade the provided script on 6 criteria and return ONLY valid JSON — no preamble, no markdown.

CRITERIA:
1. WORD COUNT — Score based on proximity to target. Within ±15 words: 10/10. Within ±25 words: 8/10. Within ±40 words: 6/10. Within ±60 words: 4/10. More than 60 words off: 2/10. Never give 0/10 unless the script is under 30 words or over 500 words. The user chose the target — being close is good enough.
2. SECOND PERSON — The PRIMARY character must be "you". In comparison format scripts (dropout vs student, thief vs cop, etc.) a secondary character using he/she/they is acceptable and expected. Only fail if the main protagonist is referred to in third person instead of second person. Score 10/10 if "you" is clearly the main character even if a comparison character uses he/she.
3. TIME PROGRESSION — Must use Day/Week/Month/Year time markers with escalating stakes at each stage.
4. RECURRING FIGURE — A famous figure should appear 1-2 times and get dismissed with foul language or physical humor.
5. QUIET CLOSER — Must end with a short, understated, reflective sentence. No CTA. No call to action.
6. VISCERAL DETAIL — Script must include specific sensory descriptions: smells, sounds, textures, tastes.

Score each 0-10. Pass = 7 or above.

Return this exact JSON:
{
  "scores": {
    "word_count": {"pass": true, "score": 10, "detail": "320 words — perfect range"},
    "second_person": {"pass": true, "score": 10, "detail": "Fully second person throughout"},
    "time_progression": {"pass": true, "score": 9, "detail": "Clean Day/Week/Month/Year escalation"},
    "recurring_figure": {"pass": true, "score": 8, "detail": "Socrates appears twice, dismissed with humor"},
    "quiet_closer": {"pass": false, "score": 3, "detail": "Ends with a CTA instead of a quiet reflective line"},
    "visceral_detail": {"pass": true, "score": 9, "detail": "Strong sensory grounding — smell of oil, sound of sizzling"}
  },
  "overall_score": 82,
  "grade": "B",
  "issues": ["Closer should be a quiet reflective sentence, not a CTA"],
  "fixed_script": "The complete rewritten script with ALL issues corrected, same concept, same tone, 280-380 words"
}"""

GRADE_PROMPT_B = """You are a viral script analyst for TikTok/YouTube Shorts. Grade the provided script on 6 criteria and return ONLY valid JSON — no preamble, no markdown.

CRITERIA:
1. WORD COUNT — Score based on proximity to target. Within ±15 words: 10/10. Within ±25 words: 8/10. Within ±40 words: 6/10. Within ±60 words: 4/10. More than 60 words off: 2/10. Never give 0/10 unless the script is under 30 words or over 500 words. The user chose the target — being close is good enough.
2. SECOND PERSON — The PRIMARY character must be "you". In comparison format scripts (dropout vs student, thief vs cop, etc.) a secondary character using he/she/they is acceptable and expected. Only fail if the main protagonist is referred to in third person instead of second person. Score 10/10 if "you" is clearly the main character even if a comparison character uses he/she.
3. NAMED OBJECT — Object must receive a human name (Gerald, Karen, etc.) by sentence 2.
4. HEAD FAKE — Must have a sudden tonal shift at 60-70% through the script.
5. CTA FORMAT — Must end with exactly three options: "If you want X, like. If you want Y, follow. If you want Z, share this with someone who [funny reason]."
6. DRY TONE — No exclamation marks. No hype words. Sentences averaging 3-7 words. Deadpan delivery.

Score each 0-10. Pass = 7 or above.

Return this exact JSON:
{
  "scores": {
    "word_count": {"pass": true, "score": 10, "detail": "137 words — perfect range"},
    "second_person": {"pass": true, "score": 10, "detail": "Fully second person throughout"},
    "named_object": {"pass": false, "score": 2, "detail": "Object named at sentence 4, not sentence 2"},
    "head_fake": {"pass": true, "score": 8, "detail": "Strong head fake at ~65%"},
    "cta_format": {"pass": false, "score": 0, "detail": "CTA has one option, needs three"},
    "dry_tone": {"pass": true, "score": 9, "detail": "Excellent deadpan, no hype language"}
  },
  "overall_score": 65,
  "grade": "C",
  "issues": ["Object named too late", "CTA needs three options"],
  "fixed_script": "The complete rewritten script with ALL issues corrected, same concept, same tone, 130-180 words"
}"""


@app.route("/grade-script", methods=["POST"])
@login_required
def grade_script():
    gate = require_paid_tier()
    if gate: return gate

    data = request.get_json()
    script = data.get("script", "").strip()
    formula = data.get("formula", "a")
    target_word_count = data.get("target_word_count", 180)
    history_id = data.get("history_id")
    tolerance = 15

    if not script:
        return jsonify({"error": "Script is required"}), 400

    grade_prompt = GRADE_PROMPT_A if formula == "a" else GRADE_PROMPT_B

    word_count_instruction = (
        f"\nIMPORTANT: The target word count for this script was {target_word_count} words "
        f"(±{tolerance}). Score the word_count criterion based on how close the script is "
        f"to this target, not a fixed range.\n"
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=grade_prompt,
            messages=[{"role": "user", "content": f"{word_count_instruction}\nGrade this script:\n\n{script}"}],
        )

        raw = message.content[0].text.strip()
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            raw = json_match.group(1).strip()

        result = json.loads(raw)

        if history_id:
            cached = {
                "overall_score": result.get("overall_score"),
                "grade": result.get("grade"),
                "scores": result.get("scores"),
                "issues": result.get("issues", []),
                "fixed_script": result.get("fixed_script"),
                "formula": formula,
                "target_word_count": target_word_count,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            db_save_score(history_id, session.get("email", ""), cached)

        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse grader response"}), 500
    except Exception as e:
        return jsonify({"error": f"Grading failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Character reference upload
# ---------------------------------------------------------------------------

@app.route("/upload-reference", methods=["POST"])
@login_required
def upload_reference():
    data = request.get_json()
    character_key = data.get("character_key", "").strip()
    image_data = data.get("image_data")

    if not character_key:
        return jsonify({"error": "character_key required"}), 400

    if image_data:
        image_data = compress_image_if_needed(image_data)

    db_save_reference(character_key, image_data)
    return jsonify({"success": True, "character": character_key})


@app.route("/get-reference", methods=["POST"])
@login_required
def get_reference():
    data = request.get_json()
    character_key = data.get("character_key", "base")
    ref = db_get_reference(character_key)
    has_reference = ref is not None
    return jsonify({"has_reference": has_reference, "character_key": character_key})


# ---------------------------------------------------------------------------
# Image generation endpoint
# ---------------------------------------------------------------------------

@app.route("/generate-image", methods=["POST"])
@login_required
def generate_image():
    if not is_owner():
        return jsonify({"error": "Image generation is not available on your plan."}), 403

    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    character_key = data.get("character_key", "base")
    model_key = data.get("model_key", "nano_banana_2")
    model = IMAGE_MODELS.get(model_key, IMAGE_MODELS["nano_banana_2"])

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_key_here":
        return jsonify({"error": "OpenRouter API key not configured. Add it to .env"}), 500

    try:
        ref_image = db_get_reference(character_key)
        if not ref_image:
            ref_image = load_premade_reference(character_key)
        if ref_image:
            ref_image = compress_image_if_needed(ref_image)

        # Only inject reference if this is a character shot
        skeleton_keywords = ["skeleton", "character consistent", "blue pupils", "skull face", "(use reference)"]
        is_character_shot = any(keyword.lower() in prompt.lower() for keyword in skeleton_keywords)

        if ref_image and is_character_shot:
            message_content = [
                {
                    "type": "image_url",
                    "image_url": {"url": ref_image}
                },
                {
                    "type": "text",
                    "text": f"Use the skeleton character in the reference image as the exact character for this scene. Keep the skeleton's appearance, eye design, and proportions identical. Only change the outfit, pose, and background. Scene: {prompt}. Dark cinematic style, 9:16 vertical format, photorealistic, high detail, dramatic lighting."
                }
            ]
        elif is_character_shot:
            message_content = f"Generate an image: {prompt}. 9:16 vertical format, photorealistic, high detail, dramatic lighting."
        else:
            # Environment/object shot — no character reference needed
            message_content = f"Generate an environment or object shot with no characters: {prompt}. 9:16 vertical format, photorealistic, high detail, dramatic lighting, cinematic composition."

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://boneforge.netlify.app",
                "X-Title": "BoneForge",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "modalities": ["text", "image"],
                "image_generation_config": {
                    "aspect_ratio": "9:16"
                },
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
            },
            timeout=180,
        )

        print(f"Sending max_tokens: 4096 to OpenRouter")

        if resp.status_code != 200:
            return jsonify({"error": f"OpenRouter error: {resp.status_code}"}), 500

        result = resp.json()

        print(f"Raw response keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        if isinstance(result, dict) and 'choices' in result:
            print(f"First choice keys: {list(result['choices'][0].keys())}")
            print(f"Message keys: {list(result['choices'][0]['message'].keys())}")
            content = result['choices'][0]['message'].get('content', '')
            print(f"Content type: {type(content)}, length: {len(str(content))}")

        # Fast path: check 'images' key directly on message
        try:
            choices = result.get('choices', [])
            if choices:
                message = choices[0].get('message', {})
                # Check 'images' key directly
                images_field = message.get('images', [])
                if images_field and len(images_field) > 0:
                    img = images_field[0]
                    if isinstance(img, str):
                        if img.startswith('data:image'):
                            return jsonify({"image": img})
                        else:
                            return jsonify({"image": f"data:image/png;base64,{img}"})
                    elif isinstance(img, dict):
                        url = img.get('url') or img.get('data') or img.get('b64_json', '')
                        if url:
                            if not url.startswith('data:image'):
                                url = f"data:image/png;base64,{url}"
                            return jsonify({"image": url})
        except Exception as e:
            print(f"Direct images extraction failed: {e}")

        # Recursive search for base64 image data in the response
        def find_image(obj):
            if isinstance(obj, str):
                if obj.startswith("data:image"):
                    return obj
                # Check if it's a raw base64 string (long alphanumeric)
                if len(obj) > 1000 and re.match(r'^[A-Za-z0-9+/=]+$', obj[:100]):
                    return f"data:image/png;base64,{obj}"
            elif isinstance(obj, dict):
                # Check common keys first
                for key in ("url", "b64_json", "data", "image", "image_url", "images"):
                    if key in obj:
                        found = find_image(obj[key])
                        if found:
                            return found
                # Then check all other keys
                for key, val in obj.items():
                    found = find_image(val)
                    if found:
                        return found
            elif isinstance(obj, list):
                for item in obj:
                    found = find_image(item)
                    if found:
                        return found
            return None

        # Fall through to existing find_image() recursive search
        image_data = find_image(result)
        if image_data:
            print(f"Image data length: {len(image_data)}")
            print(f"Image prefix: {image_data[:50]}")
            print(f"Image valid base64 start: {image_data.startswith('data:image')}")
            return jsonify({"image": image_data})

        # Debug: dump response structure when no image found
        print(f"NO IMAGE FOUND in response. Keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        if isinstance(result, dict) and "choices" in result:
            for i, choice in enumerate(result["choices"][:2]):
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    print(f"Choice {i} content (str): {content[:200]}")
                elif isinstance(content, list):
                    for j, part in enumerate(content[:5]):
                        print(f"Choice {i} part {j}: type={part.get('type','?')} keys={list(part.keys())}")
                        if "inline_data" in part:
                            print(f"  inline_data keys: {list(part['inline_data'].keys())}")
                else:
                    print(f"Choice {i} content type: {type(content)}")

        return jsonify({
            "error": "Image generation model did not return an image.",
            "text_response": str(result)[:800]
        }), 500

    except requests.Timeout:
        return jsonify({"error": "Image generation timed out. Try again."}), 500
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Custom Generate page (owner only)
# ---------------------------------------------------------------------------

@app.route("/custom-generate")
@login_required
def custom_generate_page():
    if not is_owner():
        return redirect("/dashboard")
    return render_template("custom_generate.html", owner_mode=True, models=IMAGE_MODELS)

@app.route("/custom-generate-image", methods=["POST"])
@login_required
def custom_generate_image():
    if not is_owner():
        return jsonify({"error": "Owner only."}), 403

    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    model_key = data.get("model_key", "nano_banana_2")
    character_key = data.get("character_key", "")
    model = IMAGE_MODELS.get(model_key, IMAGE_MODELS["nano_banana_2"])

    print(f"[single:req] character_key={character_key!r} model_key={model_key!r} prompt_preview={prompt[:60]!r}")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_key_here":
        return jsonify({"error": "OpenRouter API key not configured."}), 500

    try:
        # Load reference image if character selected
        ref_image = None
        if character_key:
            ref_image = db_get_reference(character_key)
            if not ref_image:
                ref_image = load_premade_reference(character_key)
            if ref_image:
                ref_image = compress_image_if_needed(ref_image)
        print(f"[single:ref] ref_loaded={bool(ref_image)} ref_len={len(ref_image) if ref_image else 0}")

        # Detect character shot and inject reference (same pattern as /generate-image)
        skeleton_keywords = ["skeleton", "character consistent", "blue pupils", "skull face", "(use reference)"]
        is_character_shot = any(kw.lower() in prompt.lower() for kw in skeleton_keywords)
        print(f"[single:gen] is_character_shot={is_character_shot} will_inject_ref={bool(ref_image and is_character_shot)}")

        if ref_image and is_character_shot:
            message_content = [
                {
                    "type": "image_url",
                    "image_url": {"url": ref_image}
                },
                {
                    "type": "text",
                    "text": f"Use the skeleton character in the reference image as the exact character for this scene. Keep the skeleton's appearance, eye design, and proportions identical. Only change the outfit, pose, and background. Scene: {prompt}. Dark cinematic style, 9:16 vertical format, photorealistic, high detail, dramatic lighting."
                }
            ]
        elif is_character_shot:
            message_content = f"Generate an image: {prompt}. 9:16 vertical format, photorealistic, high detail, dramatic lighting."
        else:
            message_content = f"Generate an image: {prompt}. 9:16 vertical format, photorealistic, high detail, dramatic lighting, cinematic composition."

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://boneforge.netlify.app",
                "X-Title": "BoneForge",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "modalities": ["text", "image"],
                "image_generation_config": {
                    "aspect_ratio": "9:16"
                },
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
            },
            timeout=180,
        )

        if resp.status_code != 200:
            return jsonify({"error": f"OpenRouter error: {resp.status_code}"}), 500

        result = resp.json()

        # Fast path: check 'images' key directly on message
        choices = result.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            images_field = message.get('images', [])
            if images_field and len(images_field) > 0:
                img = images_field[0]
                if isinstance(img, str):
                    if img.startswith('data:image'):
                        return jsonify({"image": img})
                    else:
                        return jsonify({"image": f"data:image/png;base64,{img}"})
                elif isinstance(img, dict):
                    url = img.get('url') or img.get('data') or img.get('b64_json', '')
                    if url:
                        if not url.startswith('data:image'):
                            url = f"data:image/png;base64,{url}"
                        return jsonify({"image": url})

        # Recursive search fallback
        def find_img(obj):
            if isinstance(obj, str):
                if obj.startswith("data:image"):
                    return obj
                if len(obj) > 1000 and re.match(r'^[A-Za-z0-9+/=]+$', obj[:100]):
                    return f"data:image/png;base64,{obj}"
            elif isinstance(obj, dict):
                for key in ("url", "b64_json", "data", "image", "image_url", "images"):
                    if key in obj:
                        found = find_img(obj[key])
                        if found:
                            return found
                for key, val in obj.items():
                    found = find_img(val)
                    if found:
                        return found
            elif isinstance(obj, list):
                for item in obj:
                    found = find_img(item)
                    if found:
                        return found
            return None

        image_data = find_img(result)
        if image_data:
            return jsonify({"image": image_data})

        return jsonify({"error": "Image generation model did not return an image."}), 500

    except requests.Timeout:
        return jsonify({"error": "Image generation timed out. Try again."}), 500
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Batch image generation (owner only)
# ---------------------------------------------------------------------------

BATCH_MAX_PROMPTS = 30
BATCH_DELAY_SECONDS = 2
BATCH_RESULTS = {}  # batch_id -> [data_url, ...]

_BATCH_HEADER_RE = re.compile(
    r'^\s*Scene\s+\d+\b.*\(\s*\d+\s+prompts?\s*\)\s*$', re.IGNORECASE
)
_BATCH_SHORT_HEADER_RE = re.compile(
    r'^\s*Scene\s+\d+\s*[—\-:]?\s*(?:Day\s+\d+)?\s*$', re.IGNORECASE
)
_BATCH_DAY_HEADER_RE = re.compile(
    r'^\s*Day\s+\d+\s*\(\s*\d+\s+prompts?\s*\)\s*$', re.IGNORECASE
)
_BATCH_PREFIX_RE = re.compile(
    r'^\s*(?:\[\s*\d+\s*\]|\d+\s*[\.\)]|Scene\s+\d+\s*[:\-—])\s*',
    re.IGNORECASE,
)


def parse_batch_prompts(text):
    """Parse a free-form prompt file into a list of prompt strings.

    Accepts paragraphs separated by blank lines OR consecutive numbered
    lines. Strips numbered prefixes like [01], 1., 2), Scene 1:. Skips
    header lines like "Scene 1 — Day 1 (3 prompts)".
    """
    if not text:
        return []
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Force a paragraph break before any line that starts with a numbered
    # prefix, so consecutive numbered items split apart even without a
    # blank line between them.
    text = re.sub(
        r'(?m)(?<=\n)(?=\s*(?:\[\s*\d+\s*\]|\d+\s*[\.\)][ \t]|Scene\s+\d+\b))',
        '\n', text
    )
    paragraphs = re.split(r'\n\s*\n+', text)
    prompts = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        if _BATCH_HEADER_RE.match(stripped):
            continue
        if '\n' not in stripped and len(stripped) < 60 and _BATCH_SHORT_HEADER_RE.match(stripped):
            continue
        cleaned = _BATCH_PREFIX_RE.sub('', stripped, count=1).strip()
        if not cleaned:
            continue
        if _BATCH_DAY_HEADER_RE.match(cleaned):
            continue
        prompts.append(cleaned)
    return prompts


def _generate_one_batch_image(prompt, model_key, ref_image):
    """Generate a single image. Returns (data_url, error). ref_image is the
    pre-loaded character reference data URL or None.
    """
    model = IMAGE_MODELS.get(model_key, IMAGE_MODELS["nano_banana_2"])

    print(f"[batch:gen] ref_image_present={bool(ref_image)} ref_len={len(ref_image) if ref_image else 0} prompt_preview={prompt[:60]!r}")

    # Batch flow: when a character reference is loaded, apply it to every
    # prompt unconditionally (no keyword gating). When no reference, fall
    # back to a plain text prompt.
    if ref_image:
        message_content = [
            {"type": "image_url", "image_url": {"url": ref_image}},
            {
                "type": "text",
                "text": f"Use the skeleton character in the reference image as the exact character for this scene. Keep the skeleton's appearance, eye design, and proportions identical. Only change the outfit, pose, and background. Scene: {prompt}. Dark cinematic style, 9:16 vertical format, photorealistic, high detail, dramatic lighting.",
            },
        ]
        print(f"[batch:gen] sending MULTIMODAL content: parts={len(message_content)} types={[p.get('type') for p in message_content]} image_url_prefix={message_content[0]['image_url']['url'][:40]!r}")
    else:
        message_content = f"Generate an image: {prompt}. 9:16 vertical format, photorealistic, high detail, dramatic lighting, cinematic composition."
        print(f"[batch:gen] sending TEXT-ONLY content (no ref_image)")

    request_body = {
        "model": model,
        "max_tokens": 4096,
        "modalities": ["text", "image"],
        "image_generation_config": {"aspect_ratio": "9:16"},
        "messages": [{"role": "user", "content": message_content}],
    }

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://boneforge.netlify.app",
                "X-Title": "BoneForge",
            },
            json=request_body,
            timeout=180,
        )
    except requests.Timeout:
        return None, "Generation timed out"
    except Exception as e:
        return None, f"Network error: {str(e)}"

    if resp.status_code != 200:
        return None, f"OpenRouter error: {resp.status_code}"

    try:
        result = resp.json()
    except Exception:
        return None, "Invalid response from OpenRouter"

    choices = result.get('choices', [])
    if choices:
        message = choices[0].get('message', {})
        images_field = message.get('images', [])
        if images_field:
            img = images_field[0]
            if isinstance(img, str):
                if img.startswith('data:image'):
                    return img, None
                return f"data:image/png;base64,{img}", None
            elif isinstance(img, dict):
                url = img.get('url') or img.get('data') or img.get('b64_json', '')
                if url:
                    if not url.startswith('data:image'):
                        url = f"data:image/png;base64,{url}"
                    return url, None

    def find_img(obj):
        if isinstance(obj, str):
            if obj.startswith("data:image"):
                return obj
            if len(obj) > 1000 and re.match(r'^[A-Za-z0-9+/=]+$', obj[:100]):
                return f"data:image/png;base64,{obj}"
        elif isinstance(obj, dict):
            for key in ("url", "b64_json", "data", "image", "image_url", "images"):
                if key in obj:
                    found = find_img(obj[key])
                    if found:
                        return found
            for val in obj.values():
                found = find_img(val)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_img(item)
                if found:
                    return found
        return None

    image_data = find_img(result)
    if image_data:
        return image_data, None
    return None, "Model did not return an image"


@app.route("/upload-batch-prompts", methods=["POST"])
@login_required
def upload_batch_prompts():
    if not is_owner():
        return jsonify({"error": "Owner only."}), 403

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded."}), 400

    filename = (f.filename or "").lower()
    if not filename.endswith(".txt"):
        return jsonify({"error": "Only .txt files are accepted."}), 400

    try:
        raw = f.read().decode("utf-8", errors="replace")
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 400

    prompts = parse_batch_prompts(raw)
    if not prompts:
        return jsonify({"error": "No prompts found in file."}), 400

    truncated = False
    if len(prompts) > BATCH_MAX_PROMPTS:
        prompts = prompts[:BATCH_MAX_PROMPTS]
        truncated = True

    return jsonify({
        "prompts": prompts,
        "count": len(prompts),
        "truncated": truncated,
        "limit": BATCH_MAX_PROMPTS,
    })


@app.route("/generate-batch", methods=["POST"])
@login_required
def generate_batch():
    if not is_owner():
        return jsonify({"error": "Owner only."}), 403

    data = request.get_json() or {}
    prompts = data.get("prompts", [])
    character_key = data.get("character_key", "")
    model_key = data.get("model_key", "nano_banana_2")

    print(f"[batch:req] received character_key={character_key!r} model_key={model_key!r} prompt_count={len(prompts) if isinstance(prompts, list) else 'N/A'} body_keys={list(data.keys())}")

    if not isinstance(prompts, list) or not prompts:
        return jsonify({"error": "No prompts provided."}), 400

    if len(prompts) > BATCH_MAX_PROMPTS:
        return jsonify({"error": f"Max {BATCH_MAX_PROMPTS} prompts per batch."}), 400

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_key_here":
        return jsonify({"error": "OpenRouter API key not configured."}), 500

    ref_image = None
    if character_key and character_key.lower() != "none":
        print(f"[batch:ref] looking up character_key={character_key!r}")
        ref_image = db_get_reference(character_key)
        print(f"[batch:ref] db_get_reference returned: {'<data ' + str(len(ref_image)) + ' chars>' if ref_image else 'None'}")
        if not ref_image:
            ref_image = load_premade_reference(character_key)
            print(f"[batch:ref] load_premade_reference returned: {'<data ' + str(len(ref_image)) + ' chars>' if ref_image else 'None'}")
        if ref_image:
            before_len = len(ref_image)
            ref_image = compress_image_if_needed(ref_image)
            print(f"[batch:ref] compress_image_if_needed: before={before_len} after={len(ref_image) if ref_image else 0}")
        print(f"[batch:ref] FINAL ref_image loaded={bool(ref_image)} for character_key={character_key!r}")
    else:
        print(f"[batch:ref] character_key empty/none, skipping reference lookup")

    batch_id = uuid.uuid4().hex
    total = len(prompts)

    def stream():
        results = []
        yield f"data: {json.dumps({'event': 'start', 'total': total, 'batch_id': batch_id})}\n\n"
        for idx, prompt in enumerate(prompts, start=1):
            yield f"data: {json.dumps({'event': 'progress', 'index': idx, 'total': total})}\n\n"
            image_data, err = _generate_one_batch_image(prompt, model_key, ref_image)
            if err:
                yield f"data: {json.dumps({'event': 'error', 'index': idx, 'message': err})}\n\n"
                results.append(None)
            else:
                results.append(image_data)
                yield f"data: {json.dumps({'event': 'image', 'index': idx, 'image': image_data})}\n\n"
            if idx < total:
                time.sleep(BATCH_DELAY_SECONDS)
        BATCH_RESULTS[batch_id] = results
        success_count = sum(1 for r in results if r)
        yield f"data: {json.dumps({'event': 'done', 'batch_id': batch_id, 'success': success_count, 'total': total})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download-batch/<batch_id>", methods=["GET"])
@login_required
def download_batch(batch_id):
    if not is_owner():
        return jsonify({"error": "Owner only."}), 403

    if not re.match(r'^[a-f0-9]{32}$', batch_id):
        return jsonify({"error": "Invalid batch id."}), 400

    images = BATCH_RESULTS.get(batch_id)
    if not images:
        return jsonify({"error": "Batch not found or expired."}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        idx = 0
        for img in images:
            idx += 1
            if not img:
                continue
            try:
                if "," in img:
                    b64 = img.split(",", 1)[1]
                else:
                    b64 = img
                raw = base64.b64decode(b64)
            except Exception:
                continue
            zf.writestr(f"image_{idx:02d}.png", raw)
    buf.seek(0)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"batch_{timestamp}.zip",
    )


# ---------------------------------------------------------------------------
# AI Guide (non-owner chat)
# ---------------------------------------------------------------------------

AI_GUIDE_SYSTEM = """You are BoneForge AI Guide — an expert viral content strategy advisor for short-form video creators on TikTok and YouTube Shorts. You help creators craft better concepts, understand what makes content go viral, and optimize their scripts for maximum engagement.

Keep responses concise (2-4 sentences max). Be direct, opinionated, and actionable. Reference specific viral mechanics: hook strength, watch-time retention, emotional triggers, pattern interrupts, share triggers. Never be generic — every answer should feel like insider knowledge."""


@app.route("/ai-guide-page")
@login_required
def ai_guide_page():
    gate = require_paid_tier()
    if gate: return gate
    return render_template("ai_guide_page.html", owner_mode=is_owner())


@app.route("/ai-guide", methods=["POST"])
@login_required
def ai_guide():
    gate = require_paid_tier()
    if gate: return gate

    data = request.get_json()
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "No messages provided"}), 400

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "API key not configured"}), 500

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=AI_GUIDE_SYSTEM,
            messages=messages,
        )
        reply = message.content[0].text.strip()
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": f"AI Guide error: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

@app.route("/characters")
@login_required
def characters_page():
    gate = require_paid_tier()
    if gate: return gate
    return render_template("characters.html", owner_mode=is_owner())


@app.route("/premade-characters", methods=["GET"])
@login_required
def get_premade_characters():
    return jsonify({"characters": PREMADE_CHARACTERS})


@app.route("/api/characters", methods=["GET"])
@login_required
def get_characters():
    gate = require_paid_tier()
    if gate: return gate
    email = session.get("email", "")
    characters = db_get_characters(email)
    return jsonify({"characters": characters})


@app.route("/characters/create", methods=["POST"])
@login_required
def create_character():
    gate = require_paid_tier()
    if gate: return gate

    email = session.get("email", "")

    existing = db_get_characters(email)
    tier = session.get("tier", "free")
    limit = CHARACTER_LIMITS.get(tier, 1)
    if len(existing) >= limit:
        return jsonify({"error": f"Your plan allows {limit} character(s). Upgrade to add more."}), 403

    data = request.get_json()
    name = data.get("name", "").strip()
    reference_image = data.get("reference_image", "")
    prompt_prefix = data.get("prompt_prefix", "")

    if not name or not reference_image:
        return jsonify({"error": "Name and image required"}), 400

    success = db_create_character(email, name, reference_image, prompt_prefix)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Failed to create character"}), 500


@app.route("/characters/delete", methods=["POST"])
@login_required
def delete_character():
    email = session.get("email", "")
    data = request.get_json()
    character_id = data.get("id", "")
    success = db_delete_character(character_id, email)
    return jsonify({"success": success})


@app.route("/generate-character-prefix", methods=["POST"])
@login_required
def generate_character_prefix():
    data = request.get_json()
    image_data = data.get("image_data", "")

    if not image_data:
        return jsonify({"error": "Image required"}), 400

    image_data = compress_image_if_needed(image_data)

    try:
        if "," in image_data:
            header, b64 = image_data.split(",", 1)
            media_type = header.split(":")[1].split(";")[0]
        else:
            b64 = image_data
            media_type = "image/png"

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64
                        }
                    },
                    {
                        "type": "text",
                        "text": "Describe this character for use as an AI image generation prompt prefix. Always start with exactly: 'Skeleton character consistent, white 3D eyeballs with blue pupils inside the eye sockets, goofy expression, hyper realistic,' then describe only the outfit and distinguishing visual details from the image. Focus on: clothing colors, armor type, accessories, headwear. Keep it under 30 words after the fixed prefix. No sentences, just comma-separated descriptors. Do not mention art style, lighting, or background."
                    }
                ]
            }]
        )

        prefix = message.content[0].text.strip()
        return jsonify({"prefix": prefix})

    except Exception as e:
        return jsonify({"error": f"Failed to generate prefix: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.route("/history")
@login_required
def history_page():
    gate = require_paid_tier()
    if gate: return gate
    return render_template("history.html", owner_mode=is_owner())


@app.route("/history-data", methods=["GET"])
@login_required
def history_data():
    gate = require_paid_tier()
    if gate: return gate
    email = session.get("email", "")
    items = db_get_history(email)
    return jsonify({"history": items})


@app.route("/history/delete", methods=["POST"])
@login_required
def delete_history_item():
    email = session.get("email", "")
    data = request.get_json()
    history_id = data.get("id", "")
    success = db_delete_history(history_id, email)
    return jsonify({"success": success})


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


@app.route("/complete-onboarding", methods=["POST"])
@login_required
def complete_onboarding():
    email = session.get("email", "")
    try:
        if supabase:
            supabase.table("users").update(
                {"onboarded": True}
            ).eq("email", email).execute()
        session["onboarded"] = True
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.route("/settings")
@login_required
def settings_page():
    gate = require_paid_tier()
    if gate: return gate
    tier = session.get("tier", "free")
    email = session.get("email", "")
    return render_template("settings.html", tier=tier, email=email, owner_mode=is_owner())


@app.route("/cancel-subscription", methods=["POST"])
@login_required
def cancel_subscription():
    email = session.get("email", "")
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            return jsonify({"error": "No subscription found"}), 404

        customer = customers.data[0]
        subscriptions = stripe.Subscription.list(customer=customer.id, limit=1)

        if not subscriptions.data:
            return jsonify({"error": "No active subscription"}), 404

        sub = subscriptions.data[0]
        stripe.Subscription.modify(sub.id, cancel_at_period_end=True)

        return jsonify({"success": True, "message": "Subscription will cancel at period end"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    email = session.get("email", "")
    try:
        # Cancel Stripe subscriptions first
        try:
            customers = stripe.Customer.list(email=email, limit=1)
            if customers.data:
                subs = stripe.Subscription.list(customer=customers.data[0].id)
                for sub in subs.data:
                    stripe.Subscription.cancel(sub.id)
        except:
            pass

        # Delete from all Supabase tables
        if supabase:
            supabase.table("history").delete().eq("email", email).execute()
            supabase.table("characters").delete().eq("email", email).execute()
            supabase.table("usage").delete().eq("email", email).execute()
            supabase.table("reference_images").delete().eq("email", email).execute()
            supabase.table("users").delete().eq("email", email).execute()

        session.clear()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Pricing & Stripe
# ---------------------------------------------------------------------------

@app.route("/pricing")
@login_required
def pricing_page():
    email = session.get("email", "")
    tier = session.get("tier", "free")
    usage = db_get_usage(email)
    current_month = datetime.utcnow().strftime("%Y-%m")
    videos_used = 0
    if usage and usage.get("month") == current_month:
        videos_used = usage.get("videos_generated", 0)
    video_cap = VIDEO_CAPS.get(tier, 0)
    return render_template("pricing.html",
        current_tier=tier,
        owner_mode=is_owner(),
        videos_used=videos_used,
        video_cap=video_cap,
        tier=tier)


@app.route("/subscribe/<tier>", methods=["POST"])
@login_required
def subscribe(tier):
    if tier not in STRIPE_PRICES:
        return jsonify({"error": "Invalid tier"}), 400

    email = session.get("email", "")

    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=email,
            line_items=[{
                "price": STRIPE_PRICES[tier],
                "quantity": 1,
            }],
            success_url="https://boneforge.dev/payment-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://boneforge.dev/dashboard",
        )
        return jsonify({"url": checkout.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/payment-success")
@login_required
def payment_success():
    checkout_session_id = request.args.get("session_id", "")
    if checkout_session_id:
        try:
            checkout = stripe.checkout.Session.retrieve(checkout_session_id)
            if checkout.payment_status == "paid":
                email = session.get("email", "")
                subscription = stripe.Subscription.retrieve(checkout.subscription)
                price_id = subscription.items.data[0].price.id
                tier = next((k for k, v in STRIPE_PRICES.items() if v == price_id), "creator")
                if supabase:
                    supabase.table("users").update({"tier": tier}).eq("email", email).execute()
                session["tier"] = tier
        except Exception as e:
            print(f"Payment success error: {e}")
    return redirect(url_for("dashboard"))


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.email
        if supabase:
            supabase.table("users").update({"tier": "free"}).eq("email", email).execute()

    if event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.email
        price_id = sub["items"]["data"][0]["price"]["id"]
        tier = next((k for k, v in STRIPE_PRICES.items() if v == price_id), "creator")
        if supabase:
            supabase.table("users").update({"tier": tier}).eq("email", email).execute()

    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return "ok", 200

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
