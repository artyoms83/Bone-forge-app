import os
import json
import base64
import re
import hashlib
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, flash
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

OWNER_MODE = os.getenv("OWNER_MODE", "false").lower() == "true"

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

def db_create_user(email, password_hash, tier="founding_member"):
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

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# ---------------------------------------------------------------------------
# Character presets — injected into image prompts for consistency
# ---------------------------------------------------------------------------

CHARACTER_PRESETS = {
    "napoleon": {
        "name": "Napoleon Skeleton",
        "prompt_prefix": "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, Napoleonic French infantry uniform, navy blue coat, red facings, white crossbelt, shako hat, photorealistic environment, natural lighting, realistic textures",
    },
    "knight": {
        "name": "Knight Skeleton",
        "prompt_prefix": "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, full medieval plate armor, skull face fully exposed, photorealistic environment, natural lighting, realistic textures",
    },
    "viking": {
        "name": "Viking Skeleton",
        "prompt_prefix": "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, Viking warrior outfit, brown fur cloak over chainmail, horned iron helmet, leather arm wraps, photorealistic environment, natural lighting, realistic textures",
    },
    "samurai": {
        "name": "Samurai Skeleton",
        "prompt_prefix": "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, traditional Japanese samurai armor, red and black lacquered plates, horned kabuto helmet, photorealistic environment, natural lighting, realistic textures",
    },
}

PROFESSION_BASE_PREFIX = "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, photorealistic environment, natural lighting, realistic textures"

# ---------------------------------------------------------------------------
# Video caps
# ---------------------------------------------------------------------------

VIDEO_CAPS = {
    "starter": 15,
    "creator": 26,
    "pro": 30,
    "founding_member": 30,
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
                session["tier"] = user.get("tier", "founding_member")
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
                        session["tier"] = "founding_member"
                        return redirect(url_for("dashboard"))
                    else:
                        error = "Registration failed. Please try again."
        except Exception as e:
            print(f"Register route error: {e}")
            error = f"Unexpected error: {str(e)}"

    return render_template("login.html", error=error, mode="register")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", owner_mode=OWNER_MODE)


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
  "image_prompts": ["Prompt 1...", "...28-32 prompts total"],
  "animation_directives": ["Natural language sentence 1...", "...28-32 directives matching image prompts"]
}

IMAGE PROMPT RULES:
- CRITICAL: Each image prompt must work as a completely standalone photograph. The AI image generator has NO memory of previous images generated. Each prompt must describe everything needed to generate that single image independently.
- For CHARACTER shots: Begin with the full character prefix provided. Include character appearance, outfit, pose, expression, and environment all in one prompt. Never reference "the previous scene" or assume anything carries over.
- For NO-CHARACTER shots (object close-ups, crowd reactions, environment shots): Describe only what is in that single frame. No character prefix needed.
- Every prompt must include: subject, environment, lighting, camera angle, mood — all self-contained.
- 30% of prompts should be no-character shots for visual variety.
- Bad example: "skeleton continues riding as before" — references previous frame, will fail.
- Good example: "skeleton character consistent, eyeballs with black pupils in skull, goofy expressive eyes, 3D, riding a dirt bike through muddy medieval street, leaning forward at speed, stone buildings blurred behind him, torchlight, low angle shot, 9:16"
- Art style: dark, cinematic, slightly absurd, photorealistic, high detail, 9:16 vertical format.
- When the script involves a named historical figure (Napoleon, Caesar, Alexander, Genghis Khan, pharaohs etc), generate a photorealistic environment shot of that figure in their period-appropriate setting as a reaction/witness shot. Describe their appearance fully in that single prompt without relying on any other prompt for context.
- When a character outfit changes mid-script (promotion, disguise, transformation), update the character prefix description in all subsequent prompts to reflect the new outfit. Keep it consistent from that point forward. Never mix outfit descriptions between before and after the change.
- Generate 28-32 prompts total matching script length

ANIMATION DIRECTIVE RULES:
- One natural flowing sentence per directive
- Describe camera movement, what moves, and the feeling of the shot
- No labels like CAMERA: or MOTION: or TRANSITION:
- Example: "Slow push-in on the character's face as his jaw drops, torchlight flickering across stone walls behind him"
- Must match corresponding image prompt number exactly
- Generate same count as image prompts
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
  "image_prompts": ["Prompt 1...", "...15-20 prompts"],
  "animation_directives": ["Directive 1...", "...15-20 directives"]
}

IMAGE PROMPT RULES:
- CRITICAL: Each image prompt must work as a completely standalone photograph. The AI image generator has NO memory of previous images generated. Each prompt must describe everything needed to generate that single image independently.
- For CHARACTER shots: Begin with the full character prefix provided. Include character appearance, outfit, pose, expression, and environment all in one prompt. Never reference "the previous scene" or assume anything carries over.
- For NO-CHARACTER shots (object close-ups, crowd reactions, environment shots): Describe only what is in that single frame. No character prefix needed.
- Every prompt must include: subject, environment, lighting, camera angle, mood — all self-contained.
- 30% of prompts should be no-character shots for visual variety.
- Art style: dark, cinematic, slightly absurd, photorealistic, high detail, 9:16 vertical format.
- When the script involves a named historical figure (Napoleon, Caesar, Alexander, Genghis Khan, pharaohs etc), generate a photorealistic environment shot of that figure in their period-appropriate setting as a reaction/witness shot. Describe their appearance fully in that single prompt without relying on any other prompt for context.
- When a character outfit changes mid-script (promotion, disguise, transformation), update the character prefix description in all subsequent prompts to reflect the new outfit. Keep it consistent from that point forward. Never mix outfit descriptions between before and after the change.
- Generate 15-20 prompts total

ANIMATION DIRECTIVE RULES:
- One natural flowing sentence per directive — no labels or structured tags
- Generate same count as image prompts
"""


# ---------------------------------------------------------------------------
# Generation endpoint
# ---------------------------------------------------------------------------

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    data = request.get_json()
    concept = data.get("concept", "").strip()
    formula = data.get("formula", "a")
    recurring_figure = data.get("recurring_figure", "socrates")
    character_mode = data.get("character_mode", "library")
    character_preset = data.get("character_preset", "napoleon")
    word_count = data.get("word_count", 180)

    if not concept:
        return jsonify({"error": "Concept is required"}), 400

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_key_here":
        return jsonify({"error": "Anthropic API key not configured. Add it to .env"}), 500

    # Video cap check
    email = session.get("email", "legacy")
    tier = session.get("tier", "founding_member")
    cap = VIDEO_CAPS.get(tier, 30)
    current_month = datetime.now().strftime("%Y-%m")
    usage_row = db_get_usage(email)
    videos_used = 0
    if usage_row and usage_row.get("month") == current_month:
        videos_used = usage_row.get("videos_generated", 0)
    if videos_used >= cap:
        return jsonify({"error": f"You've reached your {cap} video limit for this month. Upgrade to Pro for more."}), 429

    # Resolve character prefix based on mode
    if character_mode == "library":
        preset = CHARACTER_PRESETS.get(character_preset, list(CHARACTER_PRESETS.values())[0])
        character_prompt_prefix = preset["prompt_prefix"]
        mode_instruction = ""
    else:  # profession or custom
        character_prompt_prefix = PROFESSION_BASE_PREFIX
        mode_instruction = "\nCharacter mode is PROFESSION AUTO. Append character_outfit to all character image prompts after the base prefix.\n"

    # Select system prompt based on formula
    system_prompt = SYSTEM_PROMPT if formula == "a" else SYSTEM_PROMPT_B

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
            f"For every character image prompt, begin with this exact prefix:\n"
            f'"{character_prompt_prefix}"\n\n'
            f"Target word count: {word_count} words, stay within 10 words of this target.\n"
            f"Follow the formula exactly. Return ONLY the JSON object."
        )
    else:
        user_message = (
            f"Write a viral short-form video script about this concept: {concept}\n"
            f"{mode_instruction}\n"
            f"For every character image prompt, begin with this exact prefix:\n"
            f'"{character_prompt_prefix}"\n\n'
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
        result.setdefault("animation_directives", [])

        # Increment usage
        db_update_usage(email, videos_used + 1, current_month)

        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse AI response. Try again."}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


GRADE_PROMPT_A = """You are a viral script analyst for TikTok/YouTube Shorts. Grade the provided script on 6 criteria and return ONLY valid JSON — no preamble, no markdown.

CRITERIA:
1. WORD COUNT — Must be 280-380 words. Count every word precisely.
2. SECOND PERSON — Must use "you/your" throughout. Any "he/she/they/the skeleton/the pharaoh" = fail. The viewer IS the character.
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
1. WORD COUNT — Must be 130-180 words. Count every word precisely.
2. SECOND PERSON — Must use "you/your" throughout. Any third-person reference = fail.
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
    data = request.get_json()
    script = data.get("script", "").strip()
    formula = data.get("formula", "a")

    if not script:
        return jsonify({"error": "Script is required"}), 400

    grade_prompt = GRADE_PROMPT_A if formula == "a" else GRADE_PROMPT_B

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=grade_prompt,
            messages=[{"role": "user", "content": f"Grade this script:\n\n{script}"}],
        )

        raw = message.content[0].text.strip()
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            raw = json_match.group(1).strip()

        result = json.loads(raw)
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
    if not OWNER_MODE:
        return jsonify({"error": "Image generation is not available on your plan."}), 403

    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    character_key = data.get("character_key", "base")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_key_here":
        return jsonify({"error": "OpenRouter API key not configured. Add it to .env"}), 500

    try:
        ref_image = db_get_reference(character_key)

        # Only inject reference if this is a character shot
        skeleton_keywords = ["skeleton", "character consistent", "eyeballs with black pupils", "skull face"]
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
                "model": "google/gemini-3.1-flash-image-preview",
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
# AI Guide (non-owner chat)
# ---------------------------------------------------------------------------

AI_GUIDE_SYSTEM = """You are BoneForge AI Guide — an expert viral content strategy advisor for short-form video creators on TikTok and YouTube Shorts. You help creators craft better concepts, understand what makes content go viral, and optimize their scripts for maximum engagement.

Keep responses concise (2-4 sentences max). Be direct, opinionated, and actionable. Reference specific viral mechanics: hook strength, watch-time retention, emotional triggers, pattern interrupts, share triggers. Never be generic — every answer should feel like insider knowledge."""


@app.route("/ai-guide", methods=["POST"])
@login_required
def ai_guide():
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
# Health check
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return "ok", 200

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
