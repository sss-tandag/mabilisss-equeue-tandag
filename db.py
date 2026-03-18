"""
═══════════════════════════════════════════════════════════
 MabiliSSS eQueue — Database Layer V1.0 (Supabase)
 Shared by member_app.py and staff_app.py
 All times in PHT (UTC+8)
 © RPTayo / SSS-MND 2026
═══════════════════════════════════════════════════════════
"""

import streamlit as st
try:
    from supabase import create_client
except ImportError as e:
    st.error(f"❌ Supabase import failed: {e}")
    st.stop()
from datetime import date, datetime, timezone, timedelta
import time, uuid, hashlib, re

VER = "V1.0"

# ── Philippine Standard Time ──
PHT = timezone(timedelta(hours=8))

def now_pht():
    return datetime.now(PHT)

def today_pht():
    return now_pht().date()

def today_iso():
    return today_pht().isoformat()

def today_mmdd():
    return today_pht().strftime("%m%d")

# ── SSS Logo — dynamic from branch_config, fallback to default ──
SSS_LOGO_DEFAULT = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Social_Security_System_%28Philippines%29_logo.svg/1200px-Social_Security_System_%28Philippines%29_logo.svg.png"
# Accessed via get_logo() after branch is loaded — see below

def get_logo(branch=None):
    """Return logo URL: branch_config.logo_url > default constant."""
    if branch:
        url = (branch.get("logo_url") or "").strip()
        if url:
            return url
    return SSS_LOGO_DEFAULT

# For backward compat — used in imports (resolved at render time via get_logo)
SSS_LOGO = SSS_LOGO_DEFAULT

# ── Icon Library for category setup ──
ICON_LIBRARY = [
    ("📋", "General / Default"),
    ("💰", "Money / Payments / Collections"),
    ("🏦", "Loans / Financial"),
    ("🎓", "Education / Scholarship"),
    ("🏥", "Medical / Sickness / Maternity"),
    ("⚰️", "Death / Funeral"),
    ("👴", "Retirement / Pension"),
    ("♿", "Disability / PWD"),
    ("👤", "Membership / Registration"),
    ("🏢", "Employers / Compliance"),
    ("📄", "Documents / Records / ID"),
    ("🔄", "Updates / Changes / Correction"),
    ("⭐", "Priority / Courtesy / VIP"),
    ("⚡", "Fast Lane / Express"),
    ("📱", "Digital / Online / E-Services"),
    ("🤝", "Partnership / MOA"),
    ("📢", "Inquiry / Information"),
    ("🛡️", "Insurance / Coverage"),
    ("👶", "Maternity / Paternity"),
    ("🔧", "Technical / Support"),
    ("📊", "Reports / Analytics"),
    ("🏠", "Housing / Real Estate"),
    ("💼", "Employment / HR"),
    ("🌐", "International / OFW"),
    ("🎯", "Special Programs"),
]

# ── Supabase Connection ──
def get_supabase():
    if "sb_client" not in st.session_state:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            import os
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            st.error("❌ Missing Supabase credentials.")
            st.stop()
        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client

# ── ID / Password Helpers ──
def gen_id():
    """Unique ID: microsecond timestamp + 8-char UUID to prevent collision."""
    return f"{int(time.time()*1_000_000)}-{uuid.uuid4().hex[:8]}"

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def validate_mobile_ph(mobile):
    """Validate Philippine mobile: 09XX XXXX XXX (11 digits starting with 09)."""
    digits = re.sub(r'\D', '', mobile)
    if len(digits) == 11 and digits.startswith("09"):
        return digits
    if len(digits) == 12 and digits.startswith("639"):
        return "0" + digits[2:]
    return None

# ═══════════════════════════════════════════════════
#  CACHED LOOKUPS (branch + categories change rarely)
# ═══════════════════════════════════════════════════
@st.cache_data(ttl=60)
def get_branch_cached():
    sb = get_supabase()
    r = sb.table("branch_config").select("*").eq("id", "main").execute()
    if r.data:
        return r.data[0]
    return {"id": "main", "name": "SSS-MND Branch", "address": "", "hours": "",
            "announcement": "", "o_stat": "online"}

def get_branch():
    return get_branch_cached()

def invalidate_branch():
    get_branch_cached.clear()

@st.cache_data(ttl=60)
def get_categories_cached():
    sb = get_supabase()
    r = sb.table("categories").select("*").order("sort_order").execute()
    return r.data or []

@st.cache_data(ttl=60)
def get_services_cached():
    sb = get_supabase()
    r = sb.table("services").select("*").order("sort_order").execute()
    return r.data or []

def get_categories():
    return get_categories_cached()

def get_services(category_id=None):
    svcs = get_services_cached()
    if category_id:
        return [s for s in svcs if s["category_id"] == category_id]
    return svcs

def get_categories_with_services():
    cats = [dict(c) for c in get_categories()]  # copy to avoid mutating cache
    svcs = get_services()
    svc_map = {}
    for s in svcs:
        svc_map.setdefault(s["category_id"], []).append(s)
    for c in cats:
        c["services"] = svc_map.get(c["id"], [])
    return cats

def invalidate_categories():
    get_categories_cached.clear()
    get_services_cached.clear()

# ═══════════════════════════════════════════════════
#  BRANCH CONFIG — WRITES
# ═══════════════════════════════════════════════════
def update_branch(**kwargs):
    sb = get_supabase()
    kwargs["updated_at"] = now_pht().isoformat()
    sb.table("branch_config").update(kwargs).eq("id", "main").execute()
    invalidate_branch()

# ═══════════════════════════════════════════════════
#  CATEGORIES — FULL CRUD
# ═══════════════════════════════════════════════════
def add_category(cat_id, label, icon, short_label, avg_time, cap, sort_order,
                 bqms_prefix="", bqms_range_start=None, bqms_range_end=None,
                 description="",
                 priority_lane_enabled=False, priority_cap=10,
                 priority_bqms_start=None, priority_bqms_end=None):
    sb = get_supabase()
    row = {
        "id": cat_id, "label": label, "icon": icon,
        "short_label": short_label, "avg_time": avg_time,
        "cap": cap, "sort_order": sort_order,
        "bqms_prefix": bqms_prefix or "",
        "bqms_range_start": bqms_range_start,
        "bqms_range_end": bqms_range_end,
        "description": description or "",
        # V2.3.0-P3 per-category priority lane fields
        "priority_lane_enabled": bool(priority_lane_enabled),
        "priority_cap": priority_cap or 10,
        "priority_bqms_start": priority_bqms_start,
        "priority_bqms_end": priority_bqms_end,
    }
    sb.table("categories").insert(row).execute()
    try:
        sb.table("bqms_state").insert({"category_id": cat_id}).execute()
    except:
        pass
    invalidate_categories()

def update_category(cat_id, **kwargs):
    sb = get_supabase()
    sb.table("categories").update(kwargs).eq("id", cat_id).execute()
    invalidate_categories()

def delete_category(cat_id):
    """Delete category + its services + bqms_state. Checks for active entries first."""
    sb = get_supabase()
    sb.table("services").delete().eq("category_id", cat_id).execute()
    try:
        sb.table("bqms_state").delete().eq("category_id", cat_id).execute()
    except:
        pass
    sb.table("categories").delete().eq("id", cat_id).execute()
    invalidate_categories()

def has_active_entries(cat_id):
    """Check if category has active (non-terminal) queue entries today."""
    q = get_queue_today()
    return any(r.get("category_id") == cat_id and r.get("status") in ("RESERVED", "ARRIVED", "SERVING")
               for r in q)

# ═══════════════════════════════════════════════════
#  SERVICES (Sub-Categories) — FULL CRUD
# ═══════════════════════════════════════════════════
def add_service(svc_id, category_id, label, sort_order=0, description=""):
    sb = get_supabase()
    sb.table("services").insert({
        "id": svc_id, "category_id": category_id,
        "label": label, "sort_order": sort_order,
        "description": description or "",
    }).execute()
    invalidate_categories()

def update_service(svc_id, **kwargs):
    sb = get_supabase()
    sb.table("services").update(kwargs).eq("id", svc_id).execute()
    invalidate_categories()

def delete_service(svc_id):
    sb = get_supabase()
    sb.table("services").delete().eq("id", svc_id).execute()
    invalidate_categories()

# ═══════════════════════════════════════════════════
#  QUEUE ENTRIES — READS
# ═══════════════════════════════════════════════════
# Terminal statuses: entry is "done" — no more actions
TERMINAL = ("COMPLETED", "CANCELLED", "VOID", "EXPIRED")
# Freed statuses: slot goes back to daily cap pool
FREED = ("CANCELLED", "VOID")

def get_queue_today():
    sb = get_supabase()
    r = sb.table("queue_entries").select("*").eq("queue_date", today_iso()).order("slot").execute()
    return r.data or []

@st.cache_data(ttl=30)
def get_queue_today_cached():
    """Cached version (30s TTL) for read-only display screens.
    Reduces API calls when multiple members refresh simultaneously.
    Use uncached get_queue_today() for form submissions and write operations."""
    sb = get_supabase()
    r = sb.table("queue_entries").select("*").eq("queue_date", today_iso()).order("slot").execute()
    return r.data or []

def get_queue_by_date(target_date):
    sb = get_supabase()
    r = sb.table("queue_entries").select("*").eq("queue_date", target_date).order("slot").execute()
    return r.data or []

def get_queue_date_range(start_date, end_date):
    sb = get_supabase()
    r = (sb.table("queue_entries").select("*")
         .gte("queue_date", start_date)
         .lte("queue_date", end_date)
         .order("queue_date").order("slot")
         .execute())
    return r.data or []

# ═══════════════════════════════════════════════════
#  QUEUE ENTRIES — WRITES
# ═══════════════════════════════════════════════════
def insert_queue_entry(entry):
    sb = get_supabase()
    sb.table("queue_entries").insert(entry).execute()

def update_queue_entry(entry_id, **kwargs):
    sb = get_supabase()
    sb.table("queue_entries").update(kwargs).eq("id", entry_id).execute()

def cancel_entry(entry_id):
    """Member self-cancellation. Frees the slot."""
    update_queue_entry(entry_id, status="CANCELLED", cancelled_at=now_pht().isoformat())

def void_entry(entry_id, reason, voided_by):
    """TH admin void. Frees the slot. Requires reason for audit."""
    update_queue_entry(entry_id,
                       status="VOID",
                       void_reason=reason,
                       voided_by=voided_by,
                       voided_at=now_pht().isoformat())

def expire_old_reserved():
    """Auto-expire: set all RESERVED entries from past dates to EXPIRED.
    Called on app load. Handles entries from any previous day still in RESERVED.
    Wrapped in try/except — migration may not have run yet."""
    try:
        sb = get_supabase()
        today = today_iso()
        sb.table("queue_entries").update({
            "status": "EXPIRED",
            "expired_at": now_pht().isoformat()
        }).eq("status", "RESERVED").lt("queue_date", today).execute()
    except Exception:
        # Migration not yet applied — silently skip, don't crash the app
        pass

# ═══════════════════════════════════════════════════
#  SLOT / CAP LOGIC
# ═══════════════════════════════════════════════════
def count_daily_by_category(queue_list, cat_id, lane=None):
    """Count entries consuming a daily cap slot.
    ALL entries count EXCEPT: CANCELLED, VOID (these free slots).
    COMPLETED still counts — cap is for the WHOLE DAY.
    EXPIRED still counts — they occupied a slot during the day.
    If lane is specified, only count entries in that lane (P3)."""
    entries = [r for r in queue_list
               if r.get("category_id") == cat_id
               and r.get("status") not in FREED]
    if lane:
        entries = [r for r in entries if r.get("lane", "regular") == lane]
    return len(entries)

def slot_counts(cats, queue_list):
    """Returns {cat_id: {used, cap, remaining}} for each category.
    P3: When priority_lane_enabled, adds sub-keys for each lane:
        {used, cap, remaining, regular: {used, cap, remaining}, priority: {used, cap, remaining}}
    """
    m = {}
    for c in cats:
        cat_id = c["id"]
        total_used = count_daily_by_category(queue_list, cat_id)
        reg_cap = c.get("cap", 50)

        if c.get("priority_lane_enabled"):
            pri_cap = c.get("priority_cap", 10)
            reg_used = count_daily_by_category(queue_list, cat_id, lane="regular")
            pri_used = count_daily_by_category(queue_list, cat_id, lane="priority")
            m[cat_id] = {
                "used": total_used, "cap": reg_cap + pri_cap,
                "remaining": max(0, reg_cap - reg_used) + max(0, pri_cap - pri_used),
                "regular":  {"used": reg_used, "cap": reg_cap, "remaining": max(0, reg_cap - reg_used)},
                "priority": {"used": pri_used, "cap": pri_cap, "remaining": max(0, pri_cap - pri_used)},
            }
        else:
            m[cat_id] = {"used": total_used, "cap": reg_cap, "remaining": max(0, reg_cap - total_used)}
    return m

def next_slot_num(queue_list):
    """Next slot number. Uses max existing slot + 1 to handle gaps from deletes."""
    if not queue_list:
        return 1
    max_slot = max(r.get("slot", 0) for r in queue_list)
    return max_slot + 1

# ═══════════════════════════════════════════════════
#  BQMS VALIDATION & SERIES
# ═══════════════════════════════════════════════════
def is_bqms_taken(queue_list, bqms_number, exclude_id=None):
    """Check if BQMS# is already assigned today.
    A BQMS number is 'taken' once assigned, even if the entry is COMPLETED or VOID.
    Only CANCELLED/EXPIRED entries release their BQMS (but they typically don't have one).
    exclude_id: skip this entry (for edit scenarios)."""
    if not bqms_number:
        return False
    bn = bqms_number.strip().upper()
    for r in queue_list:
        if exclude_id and r.get("id") == exclude_id:
            continue
        # BQMS uniqueness: check ALL entries regardless of status
        # (CANCELLED/EXPIRED rarely have BQMS assigned, so no practical impact)
        if (r.get("bqms_number") or "").strip().upper() == bn:
            return True
    return False

def extract_bqms_num(bqms_str):
    """Extract numeric portion from a BQMS string. '2005' → 2005, 'L-023' → 23."""
    digits = re.sub(r'\D', '', str(bqms_str))
    return int(digits) if digits else None

def validate_bqms_range(bqms_str, category, lane="regular"):
    """Check if BQMS# falls within the category's configured range.
    P3: When lane='priority', validate against priority range instead.
    Returns (ok, message)."""
    if lane == "priority" and category.get("priority_lane_enabled"):
        rs = category.get("priority_bqms_start")
        re_ = category.get("priority_bqms_end")
        range_label = "priority"
    else:
        rs = category.get("bqms_range_start")
        re_ = category.get("bqms_range_end")
        range_label = "regular"
    if rs is None or re_ is None:
        return True, ""  # No range configured — skip validation
    num = extract_bqms_num(bqms_str)
    if num is None:
        return False, "Could not parse number from BQMS input."
    if rs <= num <= re_:
        return True, ""
    return False, f"Number {num} is outside {category.get('short_label','')} {range_label} series ({rs}–{re_})."

def suggest_next_bqms(queue_list, category, lane="regular"):
    """Auto-suggest the next BQMS# for a category based on assigned numbers today.
    P3: When lane='priority', use priority BQMS range."""
    cat_id = category["id"]
    prefix = category.get("bqms_prefix", "") or ""

    # P3: Select range based on lane
    if lane == "priority" and category.get("priority_lane_enabled"):
        rs = category.get("priority_bqms_start")
        re_ = category.get("priority_bqms_end")
    else:
        rs = category.get("bqms_range_start")
        re_ = category.get("bqms_range_end")

    # Find highest BQMS number assigned in this category+lane today (ALL statuses)
    max_num = 0
    for r in queue_list:
        if r.get("category_id") != cat_id:
            continue
        # Include ALL entries — even COMPLETED/VOID — to avoid suggesting reused numbers
        # P3: only count entries in matching lane when priority_lane_enabled
        if category.get("priority_lane_enabled"):
            entry_lane = r.get("lane", "regular")
            if entry_lane != lane:
                continue
        bn = r.get("bqms_number", "")
        if not bn:
            continue
        n = extract_bqms_num(bn)
        if n and n > max_num:
            # Verify this number is within our target range (avoid cross-lane contamination)
            if rs and re_:
                if rs <= n <= re_:
                    max_num = n
            else:
                max_num = n

    if max_num > 0:
        suggested = max_num + 1
    elif rs:
        suggested = rs  # Start of range
    else:
        return ""  # No range, no history — can't suggest

    return f"{prefix}{suggested}"

def find_bqms_conflict_category(bqms_str, cats, current_cat_id, current_lane="regular"):
    """Check if a BQMS# belongs to a different category's range (or different lane's range).
    P3: Also checks priority BQMS ranges."""
    num = extract_bqms_num(bqms_str)
    if num is None:
        return None
    for c in cats:
        if c["id"] == current_cat_id:
            # Check if it conflicts with the OTHER lane's range in same category
            if c.get("priority_lane_enabled"):
                if current_lane == "regular":
                    ps = c.get("priority_bqms_start")
                    pe = c.get("priority_bqms_end")
                    if ps and pe and ps <= num <= pe:
                        return c  # Conflicts with own priority range
                else:
                    rs = c.get("bqms_range_start")
                    re_ = c.get("bqms_range_end")
                    if rs and re_ and rs <= num <= re_:
                        return c  # Conflicts with own regular range
            continue
        # Check regular range
        rs = c.get("bqms_range_start")
        re_ = c.get("bqms_range_end")
        if rs and re_ and rs <= num <= re_:
            return c
        # P3: Check priority range
        ps = c.get("priority_bqms_start")
        pe = c.get("priority_bqms_end")
        if ps and pe and ps <= num <= pe:
            return c
    return None

# ═══════════════════════════════════════════════════
#  BQMS STATE (Now Serving) — P3: Dual lane support
# ═══════════════════════════════════════════════════
def get_bqms_state():
    """Returns {cat_id: {"now_serving": str, "now_serving_priority": str}}."""
    sb = get_supabase()
    r = sb.table("bqms_state").select("*").execute()
    return {row["category_id"]: {
        "now_serving": row.get("now_serving", ""),
        "now_serving_priority": row.get("now_serving_priority", ""),
    } for row in (r.data or [])}

def update_bqms_state(category_id, now_serving, lane="regular"):
    """Update now-serving display. P3: lane param routes to correct field."""
    sb = get_supabase()
    if lane == "priority":
        sb.table("bqms_state").update({
            "now_serving_priority": now_serving,
            "updated_at": now_pht().isoformat()
        }).eq("category_id", category_id).execute()
    else:
        sb.table("bqms_state").update({
            "now_serving": now_serving,
            "updated_at": now_pht().isoformat()
        }).eq("category_id", category_id).execute()

def auto_update_now_serving(entry):
    """Auto-update 'Now Serving' when entry status changes to SERVING or COMPLETED.
    P3: Routes to correct lane field based on entry.lane."""
    bqms = entry.get("bqms_number")
    cat_id = entry.get("category_id")
    if bqms and cat_id:
        entry_lane = entry.get("lane", "regular")
        update_bqms_state(cat_id, bqms, lane=entry_lane)

# ═══════════════════════════════════════════════════
#  QUEUE AHEAD / WAIT ESTIMATION
# ═══════════════════════════════════════════════════
def count_ahead(queue_list, entry):
    """Count active entries in same category (and same lane, P3) with lower BQMS# (ahead in line)."""
    my_bqms = entry.get("bqms_number", "")
    my_cat = entry.get("category_id", "")
    my_lane = entry.get("lane", "regular")
    if not my_bqms:
        return 0
    my_num = extract_bqms_num(my_bqms)
    if my_num is None:
        return 0
    count = 0
    for r in queue_list:
        if r.get("id") == entry.get("id"):
            continue
        if r.get("category_id") != my_cat:
            continue
        if r.get("status") in TERMINAL or r.get("status") == "SERVING":
            continue
        # P3: only count entries in same lane when priority_lane_enabled is active
        # (determined by checking if entry has an explicit lane that differs)
        r_lane = r.get("lane", "regular")
        if my_lane != r_lane:
            continue
        rn = extract_bqms_num(r.get("bqms_number", ""))
        if rn is not None and rn < my_num:
            count += 1
    return count


def get_next_to_serve(queue_list, category_id, lane="regular"):
    """Find the next entry to serve: lowest BQMS# in ARRIVED status for given category/lane.
    Returns the entry dict, or None if no entries waiting."""
    best = None
    best_num = None
    for r in queue_list:
        if r.get("category_id") != category_id:
            continue
        if r.get("status") != "ARRIVED":
            continue
        if not r.get("bqms_number"):
            continue
        r_lane = r.get("lane", "regular")
        if r_lane != lane:
            continue
        rn = extract_bqms_num(r.get("bqms_number", ""))
        if rn is not None and (best_num is None or rn < best_num):
            best = r
            best_num = rn
    return best


def get_unserved_lower_bqms(queue_list, entry):
    """Find ARRIVED entries in same category/lane with lower BQMS# than given entry.
    Returns list of (bqms_number, entry) tuples sorted ascending. Used for skip warnings."""
    my_bqms = entry.get("bqms_number", "")
    my_cat = entry.get("category_id", "")
    my_lane = entry.get("lane", "regular")
    my_num = extract_bqms_num(my_bqms)
    if my_num is None:
        return []
    results = []
    for r in queue_list:
        if r.get("id") == entry.get("id"):
            continue
        if r.get("category_id") != my_cat:
            continue
        if r.get("status") != "ARRIVED":
            continue
        if r.get("lane", "regular") != my_lane:
            continue
        rn = extract_bqms_num(r.get("bqms_number", ""))
        if rn is not None and rn < my_num:
            results.append((r.get("bqms_number", ""), r))
    results.sort(key=lambda x: extract_bqms_num(x[0]) or 0)
    return results


def tier_sort_unassigned(queue_list, categories):
    """Sort unassigned entries by 4-tier model, grouped by category.
    Returns list of (entry, tier_label, position_in_cat, cat_obj) tuples.
    Tier order: T1 Priority+ARRIVED, T2 Regular+ARRIVED,
                T3 Priority+RESERVED, T4 Regular+RESERVED.
    Within each tier: FCFS by arrived_at (T1/T2) or issued_at (T3/T4)."""
    unassigned = [r for r in queue_list
                  if not r.get("bqms_number")
                  and r.get("status") not in TERMINAL]
    if not unassigned:
        return []

    result = []

    for cat in categories:
        cat_id = cat["id"]
        cat_entries = [e for e in unassigned if e.get("category_id") == cat_id]
        if not cat_entries:
            continue

        def tier_key(e):
            is_arrived = e.get("status") == "ARRIVED"
            lane = e.get("lane", "regular")
            is_pri = lane == "priority"
            if is_arrived and is_pri:
                tier = 0  # T1
            elif is_arrived:
                tier = 1  # T2
            elif is_pri:
                tier = 2  # T3
            else:
                tier = 3  # T4
            ts = e.get("arrived_at", "") if is_arrived else e.get("issued_at", "9999")
            return (tier, ts)

        cat_entries.sort(key=tier_key)
        tier_labels = {0: "\u2b50 Priority \u00b7 Arrived", 1: "\U0001f464 Regular \u00b7 Arrived",
                       2: "\u2b50 Priority \u00b7 Reserved", 3: "\U0001f464 Regular \u00b7 Reserved"}

        for pos, e in enumerate(cat_entries):
            is_arrived = e.get("status") == "ARRIVED"
            lane = e.get("lane", "regular")
            is_pri = lane == "priority"
            if is_arrived and is_pri:
                tier = 0
            elif is_arrived:
                tier = 1
            elif is_pri:
                tier = 2
            else:
                tier = 3
            result.append((e, tier_labels[tier], pos + 1, cat))

    return result

# ═══════════════════════════════════════════════════
#  V2.3.0 — BATCH ASSIGN
# ═══════════════════════════════════════════════════
def batch_assign_category(queue_list, category, assigned_by, branch=None, target_window=None):
    """Batch-assign BQMS# to all unassigned entries in a category.
    Sort order (4-tier):
      1. ARRIVED + priority  → arrived_at ASC
      2. ARRIVED + regular   → arrived_at ASC
      3. RESERVED + priority → issued_at ASC
      4. RESERVED + regular  → issued_at ASC
    P3: When priority_lane_enabled, assigns BQMS# from lane-specific ranges.
    P3.2: When branch provided and time_slot_enabled, only assigns entries
          whose preferred_time_slot is current/past (window-gated).
          When target_window set, only assigns that specific window's entries.
    Returns (count_assigned, first_bqms, last_bqms) or (0, None, None)."""
    cat_id = category["id"]
    prefix = category.get("bqms_prefix", "") or ""
    has_pri_lane = category.get("priority_lane_enabled", False)

    # Collect unassigned, non-terminal entries for this category
    pool = [e for e in queue_list
            if e.get("category_id") == cat_id
            and not e.get("bqms_number")
            and e.get("status") not in TERMINAL]

    # P3.2: Window-gate filter — only assign due entries
    pool = filter_due_for_assignment(pool, branch, target_window=target_window)

    if not pool:
        return 0, None, None

    # Build 4 tiers
    def sort_key_arrived(e):
        return e.get("arrived_at") or "9999"
    def sort_key_issued(e):
        return e.get("issued_at") or "9999"

    t1 = sorted([e for e in pool if e.get("status") == "ARRIVED" and e.get("lane", "regular") == "priority"], key=sort_key_arrived)
    t2 = sorted([e for e in pool if e.get("status") == "ARRIVED" and e.get("lane", "regular") != "priority"], key=sort_key_arrived)
    t3 = sorted([e for e in pool if e.get("status") != "ARRIVED" and e.get("lane", "regular") == "priority"], key=sort_key_issued)
    t4 = sorted([e for e in pool if e.get("status") != "ARRIVED" and e.get("lane", "regular") != "priority"], key=sort_key_issued)

    ordered = t1 + t2 + t3 + t4

    # P3: Get starting numbers for each lane
    if has_pri_lane:
        # Two separate BQMS counters
        next_str_reg = suggest_next_bqms(queue_list, category, lane="regular")
        next_str_pri = suggest_next_bqms(queue_list, category, lane="priority")

        next_num_reg = extract_bqms_num(next_str_reg) if next_str_reg else None
        if next_num_reg is None:
            next_num_reg = category.get("bqms_range_start") or 1

        next_num_pri = extract_bqms_num(next_str_pri) if next_str_pri else None
        if next_num_pri is None:
            next_num_pri = category.get("priority_bqms_start") or 1
    else:
        # Single BQMS counter (original behavior)
        next_num_str = suggest_next_bqms(queue_list, category)
        if not next_num_str:
            rs = category.get("bqms_range_start")
            next_num_reg = rs if rs else 1
        else:
            next_num_reg = extract_bqms_num(next_num_str)
            if next_num_reg is None:
                next_num_reg = category.get("bqms_range_start", 1)

    ts = now_pht().isoformat()
    first_bqms = None
    last_bqms = None

    for entry in ordered:
        # P3: Determine lane and pick correct counter
        entry_lane = entry.get("lane", "regular")
        if has_pri_lane and entry_lane == "priority":
            bqms_str = f"{prefix}{next_num_pri}"
            next_num_pri += 1
        else:
            bqms_str = f"{prefix}{next_num_reg}"
            next_num_reg += 1

        if first_bqms is None:
            first_bqms = bqms_str
        last_bqms = bqms_str

        upd = {"bqms_number": bqms_str, "bqms_assigned_at": ts}
        # Promote RESERVED → ARRIVED
        if entry.get("status") == "RESERVED":
            upd["status"] = "ARRIVED"
            upd["arrived_at"] = ts
        update_queue_entry(entry["id"], **upd)

    # Log the batch assign
    insert_batch_log(cat_id, category.get("label", ""), len(ordered), assigned_by,
                     f"BQMS {first_bqms}–{last_bqms}")
    return len(ordered), first_bqms, last_bqms


def batch_assign_all(queue_list, categories, assigned_by, branch=None):
    """Batch-assign all categories at once. Returns dict {cat_id: (count, first, last)}.
    P3.2: Passes branch for window-gated assignment."""
    results = {}
    # Must re-read queue after each category to get correct next BQMS
    for cat in categories:
        fresh_q = get_queue_today()
        cnt, first, last = batch_assign_category(fresh_q, cat, assigned_by, branch=branch)
        if cnt > 0:
            results[cat["id"]] = (cnt, first, last)
    return results


# ═══════════════════════════════════════════════════
#  V2.3.0 — QUICK CHECK-IN (Guard confirms arrival)
# ═══════════════════════════════════════════════════
def quick_checkin(entry_id):
    """Guard confirms member has arrived. Sets ARRIVED + timestamp."""
    ts = now_pht().isoformat()
    update_queue_entry(entry_id, status="ARRIVED", arrived_at=ts)


# ═══════════════════════════════════════════════════
#  V2.3.0 — PRE-8AM TRACKER HELPERS
# ═══════════════════════════════════════════════════
def count_arrived_in_category(queue_list, cat_id, lane=None):
    """Count members physically at the branch (ARRIVED status) in a category.
    P3: Optional lane filter."""
    entries = [e for e in queue_list
               if e.get("category_id") == cat_id
               and e.get("status") == "ARRIVED"
               and e.get("status") not in TERMINAL]
    if lane:
        entries = [e for e in entries if e.get("lane", "regular") == lane]
    return len(entries)


def count_reserved_position(queue_list, entry):
    """Get this entry's position among RESERVED entries in its category (by issued_at).
    P3: Filters by same lane when entry has explicit lane.
    Returns 1-based position."""
    cat_id = entry.get("category_id", "")
    my_issued = entry.get("issued_at", "9999")
    my_id = entry.get("id", "")
    my_lane = entry.get("lane", "regular")

    reserved = [e for e in queue_list
                if e.get("category_id") == cat_id
                and e.get("status") == "RESERVED"
                and not e.get("bqms_number")
                and e.get("status") not in TERMINAL
                and e.get("lane", "regular") == my_lane]
    reserved.sort(key=lambda e: e.get("issued_at", "9999"))

    for idx, e in enumerate(reserved):
        if e.get("id") == my_id:
            return idx + 1
    return len(reserved) + 1


# ═══════════════════════════════════════════════════
#  V2.3.0 — ESTIMATED WAIT TIME (actual speed)
# ═══════════════════════════════════════════════════
def calc_est_wait(queue_list, entry, categories):
    """Calculate estimated wait time based on today's actual service speed.
    P3: count_ahead is already lane-aware, so this automatically works per-lane.
    Returns (est_min_low, est_min_high, source_label) or (None, None, None)."""
    cat_id = entry.get("category_id", "")
    cat_obj = next((c for c in categories if c["id"] == cat_id), None)
    if not cat_obj:
        return None, None, None

    ahead = count_ahead(queue_list, entry)
    if ahead == 0:
        return 0, 0, "next"

    # Try actual speed from today's completed entries with serving_at
    # P3: filter by lane for more accurate per-lane speed
    entry_lane = entry.get("lane", "regular")
    completed = [e for e in queue_list
                 if e.get("category_id") == cat_id
                 and e.get("status") == "COMPLETED"
                 and e.get("serving_at") and e.get("completed_at")
                 and (not cat_obj.get("priority_lane_enabled") or e.get("lane", "regular") == entry_lane)]

    avg_minutes = None
    if len(completed) >= 3:
        durations = []
        for e in completed:
            try:
                srv = datetime.fromisoformat(e["serving_at"])
                cmp = datetime.fromisoformat(e["completed_at"])
                dur = (cmp - srv).total_seconds() / 60.0
                if 0.5 <= dur <= 120:  # sanity: 30s to 2h
                    durations.append(dur)
            except (ValueError, TypeError):
                continue
        if len(durations) >= 3:
            avg_minutes = sum(durations) / len(durations)

    if avg_minutes is not None:
        est = ahead * avg_minutes
        return round(est * 0.75), round(est * 1.35), "today"
    else:
        # Fall back to configured avg_time
        avg = cat_obj.get("avg_time", 10)
        est = ahead * avg
        return round(est * 0.75), round(est * 1.35), "typical"


# ═══════════════════════════════════════════════════
#  V2.3.0 — BATCH ASSIGN LOG
# ═══════════════════════════════════════════════════
def get_batch_log_today():
    """Get all batch assign log entries for today."""
    sb = get_supabase()
    r = sb.table("batch_assign_log").select("*").eq("queue_date", today_iso()).execute()
    return r.data or []


def insert_batch_log(cat_id, cat_label, count, assigned_by, detail=""):
    """Insert a batch assign audit log entry."""
    sb = get_supabase()
    sb.table("batch_assign_log").insert({
        "id": gen_id(),
        "category_id": cat_id,
        "category_label": cat_label,
        "assigned_count": count,
        "assigned_by": assigned_by,
        "assigned_at": now_pht().isoformat(),
        "queue_date": today_iso(),
        "detail": detail,
    }).execute()


# ═══════════════════════════════════════════════════
#  DUPLICATE DETECTION
# ═══════════════════════════════════════════════════
def is_duplicate(queue_list, last, first, mobile_clean):
    """Check for duplicate active entry. Uses cleaned mobile (digits only)."""
    nk = f"{last}|{first}"
    for r in queue_list:
        if r.get("status") in TERMINAL:
            continue
        if f"{r.get('last_name', '')}|{r.get('first_name', '')}" == nk:
            return True
        if mobile_clean and r.get("mobile"):
            r_clean = re.sub(r'\D', '', r["mobile"])
            if r_clean == mobile_clean:
                return True
    return False

# ═══════════════════════════════════════════════════
#  STAFF USERS — FULL CRUD
# ═══════════════════════════════════════════════════
def get_users():
    sb = get_supabase()
    r = sb.table("staff_users").select("*").execute()
    return r.data or []

def authenticate(username, password):
    """Authenticate using HASHED password only. No plain-text fallback."""
    users = get_users()
    u = next((x for x in users
              if x["username"].lower() == username.strip().lower()
              and x.get("active", True)), None)
    if not u:
        return None
    if u["password_hash"] == hash_pw(password):
        return u
    return None

def add_user(user_id, username, display_name, role, password):
    sb = get_supabase()
    sb.table("staff_users").insert({
        "id": user_id, "username": username.strip().lower(),
        "display_name": display_name.strip(),
        "role": role, "password_hash": hash_pw(password),
        "active": True,
        "created_at": now_pht().isoformat(),
        "updated_at": now_pht().isoformat(),
    }).execute()

def update_user(user_id, **kwargs):
    sb = get_supabase()
    kwargs["updated_at"] = now_pht().isoformat()
    sb.table("staff_users").update(kwargs).eq("id", user_id).execute()

def delete_user(user_id):
    sb = get_supabase()
    sb.table("staff_users").delete().eq("id", user_id).execute()

def reset_password(user_id, new_password):
    sb = get_supabase()
    sb.table("staff_users").update({
        "password_hash": hash_pw(new_password),
        "updated_at": now_pht().isoformat()
    }).eq("id", user_id).execute()

def update_password(user_id, new_password):
    reset_password(user_id, new_password)

# ═══════════════════════════════════════════════════
#  V2.3.0-P2 — REORDER HELPERS
# ═══════════════════════════════════════════════════
def swap_category_order(cat_id_a, cat_id_b):
    """Swap sort_order of two categories."""
    cats = get_categories()
    a = next((c for c in cats if c["id"] == cat_id_a), None)
    b = next((c for c in cats if c["id"] == cat_id_b), None)
    if a and b:
        sb = get_supabase()
        sb.table("categories").update({"sort_order": b["sort_order"]}).eq("id", cat_id_a).execute()
        sb.table("categories").update({"sort_order": a["sort_order"]}).eq("id", cat_id_b).execute()
        invalidate_categories()


def swap_service_order(svc_id_a, svc_id_b):
    """Swap sort_order of two services."""
    svcs = get_services()
    a = next((s for s in svcs if s["id"] == svc_id_a), None)
    b = next((s for s in svcs if s["id"] == svc_id_b), None)
    if a and b:
        sb = get_supabase()
        sb.table("services").update({"sort_order": b["sort_order"]}).eq("id", svc_id_a).execute()
        sb.table("services").update({"sort_order": a["sort_order"]}).eq("id", svc_id_b).execute()
        invalidate_categories()


# ═══════════════════════════════════════════════════
#  V2.3.0-P2 — RESERVATION TIME GATE
# ═══════════════════════════════════════════════════
def is_reservation_open(branch):
    """Check if online reservations are currently open.
    Returns (is_open, reason_msg).
    Checks: test_mode → working_day → holiday → time window."""
    # Test mode bypasses all restrictions
    if branch.get("test_mode"):
        return True, "🧪 Test mode active"

    now = now_pht()
    today = now.date()
    day_name = today.strftime("%a")  # Mon, Tue, etc.

    # Check working days
    working = [d.strip() for d in (branch.get("working_days", "Mon,Tue,Wed,Thu,Fri") or "Mon,Tue,Wed,Thu,Fri").split(",") if d.strip()]
    if day_name not in working:
        return False, f"Reservations are not available on {today.strftime('%A')}s. Working days: {', '.join(working)}."

    # Check holidays
    holidays_str = branch.get("holidays", "") or ""
    if holidays_str.strip():
        holiday_dates = [h.strip() for h in holidays_str.split(",") if h.strip()]
        today_str = today.isoformat()
        if today_str in holiday_dates:
            return False, "Today is a holiday. Online reservations are closed."

    # Check time window
    open_t = branch.get("reservation_open_time", "06:00") or "06:00"
    close_t = branch.get("reservation_close_time", "17:00") or "17:00"
    try:
        open_h, open_m = map(int, open_t.split(":"))
        close_h, close_m = map(int, close_t.split(":"))
    except (ValueError, AttributeError):
        open_h, open_m = 6, 0
        close_h, close_m = 17, 0

    current_mins = now.hour * 60 + now.minute
    open_mins = open_h * 60 + open_m
    close_mins = close_h * 60 + close_m

    if current_mins < open_mins:
        return False, f"Online reservations open at {open_t} AM. Please come back later."
    if current_mins >= close_mins:
        return False, f"Online reservations closed at {close_t}. Please visit the branch directly."

    return True, ""


def format_time_12h(time_str):
    """Convert HH:MM (24h) to 12h format. '08:00' → '8:00 AM', '15:30' → '3:30 PM'."""
    try:
        h, m = map(int, time_str.split(":"))
        suffix = "AM" if h < 12 else "PM"
        h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        return f"{h12}:{m:02d} {suffix}"
    except (ValueError, AttributeError):
        return time_str


# ═══════════════════════════════════════════════════
#  P3.2: TIME-SLOT APPOINTMENT SYSTEM
# ═══════════════════════════════════════════════════

def generate_time_windows(branch):
    """Generate appointment windows from branch settings.
    Returns list of HH:MM start-time strings. Empty if disabled."""
    if not branch.get("time_slot_enabled"):
        return []
    first = branch.get("first_appointment_time", "08:00") or "08:00"
    last = branch.get("last_appointment_time", "15:00") or "15:00"
    interval = int(branch.get("slot_interval_minutes", 30) or 30)
    try:
        fh, fm = map(int, first.split(":"))
        lh, lm = map(int, last.split(":"))
    except (ValueError, TypeError):
        return []
    windows = []
    cur = fh * 60 + fm
    end = lh * 60 + lm
    while cur <= end:
        h, m = divmod(cur, 60)
        windows.append(f"{h:02d}:{m:02d}")
        cur += interval
    return windows


def get_online_ceiling(cat, branch, lane=None):
    """Max online reservations for a category (or lane) today.
    Online ceiling = lane_cap × (100 − walk_in_floor_pct) / 100.
    When time_slot_enabled is OFF, returns full cap (P3.1.1 behavior)."""
    if lane == "priority" and cat.get("priority_lane_enabled"):
        raw_cap = cat.get("priority_cap", 10) or 10
    else:
        raw_cap = cat.get("cap", 50)
    if not branch.get("time_slot_enabled"):
        return raw_cap
    floor_pct = int(branch.get("walk_in_floor_pct", 40) or 40)
    return max(1, int(raw_cap * (100 - floor_pct) / 100))


def count_online_in_category(queue_list, cat_id, lane=None, time_slot=None):
    """Count active ONLINE entries for a category, optionally by lane and window."""
    n = 0
    for r in queue_list:
        if r.get("category_id") != cat_id:
            continue
        if r.get("source") != "ONLINE":
            continue
        if r.get("status") in ("CANCELLED", "VOID", "EXPIRED"):
            continue
        if lane and r.get("lane", "regular") != lane:
            continue
        if time_slot and r.get("preferred_time_slot") != time_slot:
            continue
        n += 1
    return n


def online_slots_remaining(queue_list, cat, branch, lane=None):
    """Total online slots remaining for a category today.
    Returns None when time_slot_enabled is OFF (caller uses existing cap logic)."""
    if not branch.get("time_slot_enabled"):
        return None
    ceiling = get_online_ceiling(cat, branch, lane=lane)
    booked = count_online_in_category(queue_list, cat["id"], lane=lane)
    return max(0, ceiling - booked)


def get_window_availability(queue_list, cat, branch, lane=None):
    """Per-window slot availability for member portal.
    Returns list of {window, window_end, slots, booked, available}.
    Empty when disabled."""
    if not branch.get("time_slot_enabled"):
        return []
    windows = generate_time_windows(branch)
    if not windows:
        return []
    ceiling = get_online_ceiling(cat, branch, lane=lane)
    n_win = len(windows)
    base = ceiling // n_win
    rem = ceiling % n_win
    interval = int(branch.get("slot_interval_minutes", 30) or 30)
    result = []
    for i, w in enumerate(windows):
        slots = base + (1 if i < rem else 0)
        booked = count_online_in_category(queue_list, cat["id"], lane=lane, time_slot=w)
        try:
            wh, wm = map(int, w.split(":"))
            end_min = wh * 60 + wm + interval
            eh, em = divmod(end_min, 60)
            w_end = f"{eh:02d}:{em:02d}"
        except (ValueError, TypeError):
            w_end = w
        result.append({
            "window": w, "window_end": w_end,
            "slots": slots, "booked": booked,
            "available": max(0, slots - booked),
        })
    return result


def get_current_window(branch):
    """Returns the current appointment window start time (HH:MM) or None."""
    windows = generate_time_windows(branch)
    if not windows:
        return None
    now = now_pht()
    now_min = now.hour * 60 + now.minute
    current = None
    for w in windows:
        try:
            wh, wm = map(int, w.split(":"))
            if now_min >= wh * 60 + wm:
                current = w
        except (ValueError, TypeError):
            continue
    return current


def get_entries_by_window(queue_list, cat_id, time_slot, status_filter=None):
    """Get queue entries for a specific category + time window."""
    results = []
    for r in queue_list:
        if r.get("category_id") != cat_id:
            continue
        if r.get("preferred_time_slot") != time_slot:
            continue
        if status_filter and r.get("status") not in status_filter:
            continue
        results.append(r)
    return results


def filter_due_for_assignment(pool, branch, target_window=None):
    """P3.2: Window-gate filter. Returns only entries whose preferred_time_slot
    is current/past, OR has no time slot (walk-ins, legacy entries).
    When target_window is set, ONLY returns entries matching that specific window.
    When time_slot_enabled is OFF, returns pool unchanged."""
    if not branch or not branch.get("time_slot_enabled"):
        return pool
    # P3.2: If a specific window is targeted, only match that window + no-slot entries
    if target_window:
        return [e for e in pool
                if e.get("preferred_time_slot") == target_window
                or not e.get("preferred_time_slot")]
    cur_win = get_current_window(branch)
    if not cur_win:
        # Before first window — only allow entries with no time slot
        return [e for e in pool if not e.get("preferred_time_slot")]
    # Current window as minutes for comparison
    try:
        ch, cm = map(int, cur_win.split(":"))
        cur_min = ch * 60 + cm
    except (ValueError, TypeError):
        return pool
    interval = int(branch.get("slot_interval_minutes", 30) or 30)
    cur_end = cur_min + interval
    due = []
    for e in pool:
        ts = e.get("preferred_time_slot")
        if not ts:
            # No time slot (walk-in, legacy) — always due
            due.append(e)
            continue
        try:
            th, tm = map(int, ts.split(":"))
            e_min = th * 60 + tm
        except (ValueError, TypeError):
            due.append(e)
            continue
        # Entry is due if its window start <= current window end
        if e_min <= cur_min:
            due.append(e)
    return due


def count_due_for_assignment(queue_list, cat_id, branch):
    """P3.2: Count entries eligible for batch assign (window-gated).
    Returns (due_count, total_unassigned_count)."""
    pool = [e for e in queue_list
            if e.get("category_id") == cat_id
            and not e.get("bqms_number")
            and e.get("status") not in TERMINAL]
    total = len(pool)
    if not branch or not branch.get("time_slot_enabled"):
        return total, total
    due = filter_due_for_assignment(pool, branch)
    return len(due), total


# ═══════════════════════════════════════════════════
#  STATUS CONSTANTS
# ═══════════════════════════════════════════════════
OSTATUS = {
    "online":       {"label": "Reservation Open",             "emoji": "🟢", "color": "green"},
    "intermittent": {"label": "Intermittent — Expect Delays", "emoji": "🟡", "color": "yellow"},
    "offline":      {"label": "Reservation Closed",           "emoji": "🔴", "color": "red"},
}

STATUS_LABELS = {
    "RESERVED":  "📋 Reserved",
    "ARRIVED":   "✅ Arrived",
    "SERVING":   "🔵 Serving",
    "COMPLETED": "✅ Completed",
    "CANCELLED": "🚫 Cancelled",
    "VOID":      "⚙️ Voided",
    "EXPIRED":   "⏰ Expired",
}

ROLES = ["kiosk", "staff", "th", "bh", "dh"]
ROLE_LABELS = {"kiosk": "Kiosk Operator", "staff": "Staff In-Charge",
               "th": "Team Head / Section Head", "bh": "Branch Head", "dh": "Division Head"}
ROLE_ICONS = {"kiosk": "🏢", "staff": "🛡️", "th": "👔", "bh": "🏛️", "dh": "⭐"}
