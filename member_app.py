"""
═══════════════════════════════════════════════════════════
 MabiliSSS eQueue — Member Portal V1.0 (Public)
 © RPTayo / SSS-MND 2026
═══════════════════════════════════════════════════════════
"""

import streamlit as st
from datetime import datetime
from db import (
    VER, SSS_LOGO, PHT, now_pht, today_pht, today_iso, today_mmdd,
    get_branch, get_categories_with_services, get_queue_today,
    get_queue_today_cached,
    insert_queue_entry, get_bqms_state, slot_counts, next_slot_num,
    is_duplicate, count_ahead, cancel_entry, expire_old_reserved,
    validate_mobile_ph, gen_id, extract_bqms_num,
    count_arrived_in_category, count_reserved_position, calc_est_wait,
    get_services,
    is_reservation_open, format_time_12h, get_logo,
    OSTATUS, STATUS_LABELS, TERMINAL, FREED,
    # P3.2: Time-slot appointment system
    online_slots_remaining, get_window_availability,
)

st.set_page_config(page_title="MabiliSSS eQueue", page_icon="🏛️", layout="centered")

st.markdown("""<style>
.sss-header{background:linear-gradient(135deg,#002E52,#0066A1);color:#fff!important;padding:18px 22px;border-radius:12px;margin-bottom:16px}
.sss-header h2{margin:0;font-size:22px;color:#fff!important}
.sss-header p{margin:4px 0 0;opacity:.75;font-size:13px;color:#fff!important}
.sss-card{background:var(--secondary-background-color,#fff);color:var(--text-color,#1a1a2e);border-radius:10px;padding:16px;margin-bottom:12px;border:1px solid rgba(128,128,128,.15)}
.sss-card strong,.sss-card b{color:var(--text-color,#1a1a2e)}
.sss-metric{text-align:center;padding:14px 8px;border-radius:10px;background:var(--secondary-background-color,#f5f5f5);border:1px solid rgba(128,128,128,.1)}
.sss-metric .val{font-size:30px;font-weight:900;line-height:1.2}
.sss-metric .lbl{font-size:12px;color:var(--text-color,#555);margin-top:4px;font-weight:600}
.sss-alert{border-radius:8px;padding:12px 16px;margin-bottom:12px;font-weight:600;text-align:center}
.sss-alert-red{background:rgba(220,53,69,.15);color:#ef4444;border:1px solid rgba(220,53,69,.3)}
.sss-alert-green{background:rgba(15,157,88,.12);color:#22c55e;border:1px solid rgba(15,157,88,.25)}
.sss-alert-blue{background:rgba(59,130,246,.12);color:#60a5fa;border:1px solid rgba(59,130,246,.25)}
.sss-alert-yellow{background:rgba(217,119,6,.12);color:#f59e0b;border:1px solid rgba(217,119,6,.25)}
.sss-alert strong,.sss-alert b{color:inherit}
.sss-bqms{font-family:monospace;font-size:36px;font-weight:900;color:#22B8CF;text-align:center}
.sss-resnum{font-family:monospace;font-size:26px;font-weight:900;color:#3399CC;text-align:center}
.sss-card td{color:var(--text-color,#1a1a2e);padding:4px 0}
.stButton>button{border-radius:8px;font-weight:700}
@keyframes sss-scroll{0%{transform:translateX(0%)}100%{transform:translateX(-33.33%)}}
</style>""", unsafe_allow_html=True)

# ── Auto-refresh ──
_ar_ok = False
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, limit=None, key="member_ar")
    _ar_ok = True
except ImportError:
    pass

# ── Session state ──
for k, v in {"screen": "home", "sel_cat": None,
             "sel_svc": None, "sel_timeslot": None, "ticket": None, "tracked_id": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

def go(scr):
    st.session_state.screen = scr
    st.rerun()

# ── Auto-expire old RESERVED entries (runs once per session) ──
if "expired_run" not in st.session_state:
    expire_old_reserved()
    st.session_state.expired_run = True

# ── Time (PHT) ──
now = now_pht()
screen = st.session_state.screen

# ── Conditional data loading (PERF fix: only load what's needed) ──
branch = get_branch()
cats = None
queue = None
bqms = None
sc = None

def load_queue_data():
    global cats, queue, sc
    if cats is None:
        cats = get_categories_with_services()
    if queue is None:
        queue = get_queue_today_cached()  # PERF: 30s cache for display screens
    if sc is None:
        sc = slot_counts(cats, queue)

def load_bqms_data():
    global bqms
    if bqms is None:
        bqms = get_bqms_state()

# Screens that need full data
if screen in ("home", "select_cat", "select_svc", "select_timeslot", "member_form"):
    load_queue_data()
if screen == "tracker":
    load_queue_data()
    load_bqms_data()

o_stat = branch.get("o_stat", "online")
is_open = o_stat != "offline"

# Dynamic logo: use branch config if set, fallback to default
logo_url = get_logo(branch)

# ═══════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════
st.markdown(f"""<div class="sss-header">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:12px;">
            <div><div style="font-size:12px;opacity:.7;letter-spacing:1px;">MABILISSS eQUEUE</div>
                <h2 style="margin:2px 0 0;font-size:22px;letter-spacing:0.5px;">🏛️ {branch.get('name','SSS Branch').upper()}</h2>
                <p style="margin:2px 0 0;opacity:.5;font-size:10px;">{VER}</p></div>
        </div>
        <div style="text-align:right;font-size:13px;opacity:.8;">
            {now.strftime('%A, %b %d, %Y')}<br/>{now.strftime('%I:%M %p')} PHT</div>
    </div></div>""", unsafe_allow_html=True)

# ── Status bar ──
sm = OSTATUS.get(o_stat, OSTATUS["online"])
st.markdown(f"""<div class="sss-alert sss-alert-{sm['color']}" style="font-size:15px;">
    <strong>{sm['emoji']} {sm['label']}</strong></div>""", unsafe_allow_html=True)

# ── Announcement ──
_ann = branch.get("announcement", "").strip()
if _ann:
    st.markdown(f"""<div style="background:linear-gradient(90deg,#002E52,#0066A1);
        color:#fff;padding:10px 0;margin-bottom:12px;border-radius:8px;overflow:hidden;
        box-shadow:0 2px 8px rgba(0,0,0,.15);">
        <div style="display:inline-block;white-space:nowrap;
            animation:sss-scroll 18s linear infinite;font-weight:700;font-size:14px;">
            📢&nbsp;&nbsp;{_ann}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            📢&nbsp;&nbsp;{_ann}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            📢&nbsp;&nbsp;{_ann}
        </div></div>""", unsafe_allow_html=True)

# ── Manual refresh fallback ──
if not _ar_ok:
    if st.button("🔄 Refresh Page", type="primary", use_container_width=True):
        st.rerun()

# ── Persistent 🏠 Home button (every screen except home) ──
if screen != "home":
    if st.button("🏠 Home", key="nav_home"):
        go("home")

# ═══════════════════════════════════════════════════
#  HOME
# ═══════════════════════════════════════════════════
if screen == "home":
    waiting_q = len([r for r in queue if r.get("status") in ("RESERVED", "ARRIVED")])
    serving_q = len([r for r in queue if r.get("status") == "SERVING"])
    total_remaining = sum(sc.get(c["id"], {}).get("remaining", 0) for c in cats)

    # ── Live Queue Snapshot — helps members decide if now is a good time ──
    st.markdown(f"""<div class="sss-card" style="padding:10px 14px;">
        <div style="font-size:11px;opacity:.5;text-align:center;margin-bottom:8px;letter-spacing:1px;">
            📊 LIVE QUEUE STATUS — {branch.get('name','').upper()}</div></div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        wc = "#f59e0b" if waiting_q > 0 else "#22c55e"
        st.markdown(f'<div class="sss-metric"><div class="val" style="color:{wc};">📋 {waiting_q}</div><div class="lbl">In Queue</div></div>', unsafe_allow_html=True)
    with c2:
        sc_color = "#3399CC" if serving_q > 0 else "rgba(128,128,128,.4)"
        st.markdown(f'<div class="sss-metric"><div class="val" style="color:{sc_color};">🔵 {serving_q}</div><div class="lbl">Being Served</div></div>', unsafe_allow_html=True)
    with c3:
        rc = "#22c55e" if total_remaining > 10 else "#f59e0b" if total_remaining > 0 else "#ef4444"
        rl = "FULL" if total_remaining <= 0 else str(total_remaining)
        st.markdown(f'<div class="sss-metric"><div class="val" style="color:{rc};">🎫 {rl}</div><div class="lbl">Slots Left Today</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    # V2.3.0-P2: Reservation time gate
    res_open, res_msg = is_reservation_open(branch)
    can_reserve = is_open and res_open

    with c1:
        if st.button("📋 Reserve a Slot", use_container_width=True, type="primary", disabled=not can_reserve):
            st.session_state.sel_cat = None
            st.session_state.sel_svc = None
            st.session_state.sel_timeslot = None  # P3.2: Clear stale time slot
            go("select_cat")
    with c2:
        if st.button("🔍 Track My Queue", use_container_width=True):
            st.session_state.tracked_id = None
            go("track_input")

    if not is_open:
        st.warning("🔴 Reservation is currently closed.")
    elif not res_open:
        # Show reservation hours info
        open_t = format_time_12h(branch.get("reservation_open_time", "06:00") or "06:00")
        close_t = format_time_12h(branch.get("reservation_close_time", "17:00") or "17:00")
        st.markdown(f"""<div class="sss-alert sss-alert-yellow" style="font-size:13px;">
            <strong>🕐 {res_msg}</strong><br/>
            Online reservations: <b>{open_t} – {close_t}</b>
        </div>""", unsafe_allow_html=True)
    if branch.get("test_mode"):
        st.markdown('<div class="sss-alert sss-alert-blue" style="font-size:11px;">🧪 TEST MODE — Time restrictions bypassed</div>', unsafe_allow_html=True)

    st.markdown(f"""<div class="sss-card" style="border-left:4px solid #0066A1;">
        <strong>📌 Paano Gamitin / How It Works</strong><br/><br/>
        <b>Step 1:</b> Tap <b>"Reserve a Slot"</b> → choose your transaction → fill in your name and mobile number.<br/><br/>
        <b>Step 2:</b> Save your <b>Reservation Number</b> (ex: R-0215-001).<br/><br/>
        <b>Step 3:</b> <b>Wait for your official BQMS queue number</b> — the branch will assign it starting when the branch opens. Tap <b>"Track My Queue"</b> to check.<br/><br/>
        <b>Step 4:</b> Once you have your BQMS number, <b>monitor your position</b> and <b>be at {branch.get('name','SSS Branch')} when your number is called.</b><br/><br/>
        <b>⚠️ Important:</b> If you are not present when your number is called, you will need to queue again, subject to slot availability.<br/><br/>
        <b>📱 Need to cancel?</b> Tap "Track My Queue" → find your entry → tap <b>Cancel</b>. Your slot will be released for other members.
    </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════
#  SELECT CATEGORY — V2.3.0-P3.1: Direct category list
# ═══════════════════════════════════════════════════
elif screen == "select_cat":
    if st.button("← Back to Home"):
        go("home")
    st.subheader("Step 1: Choose Transaction")

    ts_enabled = branch.get("time_slot_enabled", False)

    for cat in cats:
        cat_id = cat["id"]
        s = sc.get(cat_id, {"remaining": cat.get("cap", 50), "cap": cat.get("cap", 50)})
        remaining = s.get("remaining", 0)

        # P3.2: When time slots ON, online reservations are capped at online ceiling
        online_rem = None
        if ts_enabled:
            online_rem = online_slots_remaining(queue, cat, branch)
            if online_rem is not None:
                remaining = min(remaining, online_rem)

        full = remaining <= 0

        c1, c2 = st.columns([5, 1])
        with c1:
            btn_label = f"{cat['icon']} {cat['label']}"
            if st.button(btn_label, key=f"cat_{cat_id}", disabled=full, use_container_width=True):
                st.session_state.sel_cat = cat_id
                go("select_svc")
        with c2:
            if full:
                st.markdown('<div style="text-align:center;"><span style="font-size:12px;font-weight:900;color:#ef4444;">FULL</span></div>', unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;'><span style='font-size:20px;font-weight:900;color:#3399CC;'>{remaining}</span><br/><span style='font-size:10px;opacity:.5;'>left</span></div>", unsafe_allow_html=True)

        # Show category description
        if cat.get("description"):
            st.caption(f"ℹ️ {cat['description']}")

    all_full = all(sc.get(c["id"], {}).get("remaining", 0) <= 0 for c in cats)
    if all_full:
        open_t = format_time_12h(branch.get("reservation_open_time", "06:00") or "06:00")
        st.markdown(f"""<div class="sss-alert sss-alert-red" style="font-size:14px;">
            <strong>⚠️ All slots for today are full.</strong><br/>
            Please try again on the next working day starting at {open_t}.
            <br/><br/>Thank you for your patience!
        </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════
#  SELECT SERVICE — V2.3.0-P3.1: Direct service list
# ═══════════════════════════════════════════════════
elif screen == "select_svc":
    sel_cat_id = st.session_state.sel_cat
    if not sel_cat_id:
        go("select_cat")
    else:
        cat = next((c for c in cats if c["id"] == sel_cat_id), None)
        if not cat:
            st.error("Category not found. It may have been removed.")
            if st.button("← Back"):
                go("select_cat")
        else:
            if st.button("← Back"):
                go("select_cat")

            # Re-check cap with loaded data (sc pre-computed by load_queue_data)
            s = sc.get(cat["id"], {"remaining": 0, "cap": cat.get("cap", 50)})

            if s["remaining"] <= 0:
                open_t = format_time_12h(branch.get("reservation_open_time", "06:00") or "06:00")
                st.markdown(f"""<div class="sss-alert sss-alert-red" style="font-size:14px;">
                    <strong>⚠️ No available slots for {cat['icon']} {cat['label']} today.</strong><br/>
                    Daily limit of <b>{s['cap']}</b> has been reached.<br/><br/>
                    Please try again on the next working day starting at {open_t}.
                </div>""", unsafe_allow_html=True)
            else:
                st.subheader("Step 2: Choose Service")
                st.markdown(f"**{cat['icon']} {cat.get('short_label', cat['label'])}**")
                st.caption(f"Slots remaining: {s['remaining']} of {s['cap']}")

                if cat.get("description"):
                    st.caption(f"ℹ️ {cat['description']}")

                # P3.1: Direct service lookup by category_id
                svcs_list = get_services(category_id=cat["id"])
                if not svcs_list:
                    st.info("No specific services configured. Please contact branch staff.")
                for svc in svcs_list:
                    svc_desc = svc.get("description", "")
                    btn_text = f"● {svc['label']}"
                    if st.button(btn_text, key=f"svc_{svc['id']}", use_container_width=True):
                        st.session_state.sel_svc = svc["id"]
                        # P3.2: Route to time slot selection if enabled
                        if branch.get("time_slot_enabled"):
                            go("select_timeslot")
                        else:
                            go("member_form")
                    if svc_desc:
                        st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;ℹ️ {svc_desc}")

# ═══════════════════════════════════════════════════
#  P3.2: SELECT TIME SLOT
# ═══════════════════════════════════════════════════
elif screen == "select_timeslot":
    sel_cat_id = st.session_state.sel_cat
    sel_svc_id = st.session_state.sel_svc
    if not sel_cat_id or not sel_svc_id:
        go("select_cat")
    else:
        cat = next((c for c in cats if c["id"] == sel_cat_id), None)
        svcs_list = get_services(category_id=cat["id"]) if cat else []
        svc = next((s for s in svcs_list if s["id"] == sel_svc_id), None)
        if not cat or not svc:
            st.error("Selection not found.")
            if st.button("← Start Over"):
                go("select_cat")
        else:
            if st.button("← Back"):
                go("select_svc")

            st.subheader("Step 3: Choose Appointment Time")
            st.markdown(f'<div class="sss-card">{cat["icon"]} <strong>{svc["label"]}</strong><br/><span style="opacity:.6;">{cat["label"]}</span></div>', unsafe_allow_html=True)
            st.caption("Select your preferred time window. Please arrive at the branch within your chosen time slot.")

            # P3.2: Get per-window availability (queue pre-loaded by load_queue_data)
            windows = get_window_availability(queue, cat, branch)

            if not windows:
                st.warning("No appointment windows configured. Please contact the branch.")
                if st.button("← Back to Home"):
                    go("home")
            else:
                # "📌 Earliest Available" shortcut
                first_open = next((w for w in windows if w["available"] > 0), None)
                if first_open:
                    ea_label = f"📌 Earliest Available — {format_time_12h(first_open['window'])} to {format_time_12h(first_open['window_end'])}"
                    if st.button(ea_label, key="ts_earliest", type="primary", use_container_width=True):
                        st.session_state.sel_timeslot = first_open["window"]
                        go("member_form")
                    st.markdown("---")

                # All windows
                now = now_pht()
                now_min = now.hour * 60 + now.minute
                for w in windows:
                    try:
                        wh, wm = map(int, w["window"].split(":"))
                        eh, em = map(int, w["window_end"].split(":"))
                        w_start_min = wh * 60 + wm
                        w_end_min = eh * 60 + em
                    except (ValueError, TypeError):
                        w_start_min = 0
                        w_end_min = 0

                    # Skip past windows (unless test mode)
                    is_past = now_min >= w_end_min and not branch.get("test_mode")
                    is_full = w["available"] <= 0
                    disabled = is_past or is_full

                    w_label = f"🕐 {format_time_12h(w['window'])} – {format_time_12h(w['window_end'])}"

                    tc1, tc2 = st.columns([5, 1])
                    with tc1:
                        if st.button(w_label, key=f"ts_{w['window']}", disabled=disabled, use_container_width=True):
                            st.session_state.sel_timeslot = w["window"]
                            go("member_form")
                    with tc2:
                        if is_past:
                            st.markdown('<div style="text-align:center;"><span style="font-size:11px;opacity:.4;">Past</span></div>', unsafe_allow_html=True)
                        elif is_full:
                            st.markdown('<div style="text-align:center;"><span style="font-size:12px;font-weight:900;color:#ef4444;">FULL</span></div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div style='text-align:center;'><span style='font-size:20px;font-weight:900;color:#3399CC;'>{w['available']}</span><br/><span style='font-size:10px;opacity:.5;'>left</span></div>", unsafe_allow_html=True)

                if not first_open:
                    st.error("All appointment windows are full for today. Please try the next working day.")

# ═══════════════════════════════════════════════════
#  MEMBER FORM — V2.3.0-P3.1
# ═══════════════════════════════════════════════════
elif screen == "member_form":
    sel_cat_id = st.session_state.sel_cat
    sel_svc_id = st.session_state.sel_svc
    if not sel_cat_id or not sel_svc_id:
        go("select_cat")
    else:
        cat = next((c for c in cats if c["id"] == sel_cat_id), None)
        # P3.1: Direct service lookup
        svcs_list = get_services(category_id=cat["id"]) if cat else []
        svc = next((s for s in svcs_list if s["id"] == sel_svc_id), None)
        if not cat or not svc:
            st.error("Selection not found. Please start over.")
            if st.button("← Start Over"):
                go("select_cat")
        else:
            if st.button("← Back"):
                # P3.2: Back to timeslot when enabled, otherwise services
                if branch.get("time_slot_enabled"):
                    go("select_timeslot")
                else:
                    go("select_svc")

            _step_num = "4" if branch.get("time_slot_enabled") else "3"
            st.subheader(f"Step {_step_num}: Your Details")

            # P3.2: Show selected time slot if applicable
            _sel_ts = st.session_state.get("sel_timeslot")
            if branch.get("time_slot_enabled") and _sel_ts:
                _ts_end_min = int(_sel_ts.split(":")[0]) * 60 + int(_sel_ts.split(":")[1]) + int(branch.get("slot_interval_minutes", 30) or 30)
                _teh, _tem = divmod(_ts_end_min, 60)
                _ts_end = f"{_teh:02d}:{_tem:02d}"
                st.markdown(f'<div class="sss-card" style="border-left:4px solid #22B8CF;">🕐 <strong>Appointment Window:</strong> {format_time_12h(_sel_ts)} – {format_time_12h(_ts_end)}</div>', unsafe_allow_html=True)

            st.markdown(f'<div class="sss-card">{cat["icon"]} <strong>{svc["label"]}</strong><br/><span style="opacity:.6;">{cat["label"]}</span></div>', unsafe_allow_html=True)

            with st.form("reserve_form"):
                fc1, fc2 = st.columns(2)
                with fc1:
                    last_name = st.text_input("Last Name *", placeholder="DELA CRUZ")
                with fc2:
                    first_name = st.text_input("First Name *", placeholder="JUAN")
                fc1, fc2 = st.columns([1, 3])
                with fc1:
                    mi = st.text_input("M.I.", max_chars=2)
                with fc2:
                    mobile = st.text_input("Mobile * (09XX XXX XXXX)", placeholder="09171234567")

                # P3.1: Priority lane — shown when per-category priority is enabled
                pri_value = "regular"
                lane_value = "regular"

                if cat.get("priority_lane_enabled"):
                    pri = st.radio("Lane:", ["👤 Regular", "⭐ Priority (Senior/PWD/Pregnant)"], horizontal=True, key="pri_lane_p3")
                    if "Priority" in pri:
                        pri_value = "priority"
                        lane_value = "priority"
                        st.markdown("""<div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);
                            border-radius:8px;padding:10px 14px;margin:6px 0;font-size:12px;">
                            ⚠️ <b>Priority Lane — Verification Required</b><br/><br/>
                            Reserved for: 👴 <b>Senior Citizens</b> (60+) · ♿ <b>PWD</b> · 🤰 <b>Pregnant Women</b><br/><br/>
                            📋 You will be asked to present <b>valid proof at the counter</b>:<br/>
                            &nbsp;&nbsp;• Senior Citizen ID or gov't ID showing date of birth<br/>
                            &nbsp;&nbsp;• PWD ID<br/>
                            &nbsp;&nbsp;• Medical certificate or visible evidence of pregnancy<br/><br/>
                            ❌ <b>If you cannot present valid proof, you will be moved to the Regular Lane</b>
                            and your queue position will be adjusted accordingly.
                        </div>""", unsafe_allow_html=True)
                else:
                    # No priority lane — inform about branch accommodation
                    st.caption("💡 Senior Citizens, PWD, and Pregnant Women: Please inform the guard at the branch for priority accommodation.")

                # Unified consent checkbox — combines data privacy + priority confirmation
                if pri_value == "priority":
                    consent = st.checkbox("I consent to data collection for this queue and confirm I qualify for priority service (Senior/PWD/Pregnant). I will present valid proof at the counter.")
                else:
                    consent = st.checkbox("I consent to data collection for today's queue.")

                if st.form_submit_button("📋 Reserve My Slot", type="primary", use_container_width=True):
                    lu = last_name.strip().upper()
                    fu = first_name.strip().upper()
                    mob_raw = mobile.strip()

                    errors = []
                    if not lu:
                        errors.append("Last Name required.")
                    if not fu:
                        errors.append("First Name required.")

                    mob_clean = validate_mobile_ph(mob_raw)
                    if not mob_raw:
                        errors.append("Mobile number required.")
                    elif not mob_clean:
                        errors.append("Invalid mobile. Use 09XX format (11 digits).")

                    if not consent:
                        if pri_value == "priority":
                            errors.append("Please confirm your consent and priority qualification.")
                        else:
                            errors.append("Please check the consent box.")

                    # Fresh cap check — P3: lane-specific when priority_lane_enabled
                    fresh_q = get_queue_today()
                    fsc = slot_counts(cats, fresh_q)
                    cat_sc = fsc.get(cat["id"], {})
                    if cat.get("priority_lane_enabled") and lane_value in cat_sc:
                        remaining = cat_sc[lane_value].get("remaining", 0)
                        cap_display = cat_sc[lane_value].get("cap", 0)
                        lane_label = "Priority" if lane_value == "priority" else "Regular"
                    else:
                        remaining = cat_sc.get("remaining", 0)
                        cap_display = cat_sc.get("cap", 0)
                        lane_label = ""
                    if remaining <= 0:
                        lane_suffix = f" ({lane_label} lane)" if lane_label else ""
                        errors.append(f"No slots left for {cat['label']}{lane_suffix} today (cap: {cap_display}). Try next working day.")

                    # P3.2: Online ceiling re-check (prevents exceeding online allocation)
                    if branch.get("time_slot_enabled") and remaining > 0:
                        _ol_rem = online_slots_remaining(fresh_q, cat, branch, lane=lane_value if cat.get("priority_lane_enabled") else None)
                        if _ol_rem is not None and _ol_rem <= 0:
                            errors.append(f"Online reservation limit reached for {cat['label']}. Walk-in slots may still be available at the branch.")
                        # Also check per-window availability
                        _sel_ts_check = st.session_state.get("sel_timeslot")
                        if _ol_rem is not None and _ol_rem > 0 and _sel_ts_check:
                            _win_avail = get_window_availability(fresh_q, cat, branch,
                                            lane=lane_value if cat.get("priority_lane_enabled") else None)
                            _sel_win = next((w for w in _win_avail if w["window"] == _sel_ts_check), None)
                            if _sel_win and _sel_win["available"] <= 0:
                                errors.append(f"The {format_time_12h(_sel_ts_check)} window is now full. Please go back and choose another time.")

                    if mob_clean and is_duplicate(fresh_q, lu, fu, mob_clean):
                        errors.append("You already have an active reservation today.")

                    if errors:
                        for e in errors:
                            st.error(f"❌ {e}")
                    else:
                        slot = next_slot_num(fresh_q)
                        rn = f"R-{today_mmdd()}-{slot:03d}"
                        ts = now_pht().isoformat()
                        entry = {
                            "id": gen_id(),
                            "queue_date": today_iso(),
                            "slot": slot,
                            "res_num": rn,
                            "last_name": lu,
                            "first_name": fu,
                            "mi": mi.strip().upper(),
                            "mobile": mob_clean,
                            "service": svc["label"],
                            "service_id": svc["id"],
                            "category": cat["label"],
                            "category_id": cat["id"],
                            "cat_icon": cat["icon"],
                            "priority": pri_value,
                            "lane": lane_value,
                            "status": "RESERVED",
                            "bqms_number": None,
                            "source": "ONLINE",
                            "issued_at": ts,
                        }
                        # P3.2: Only include preferred_time_slot when time slots are enabled and selected
                        _sel_ts_val = st.session_state.get("sel_timeslot") if branch.get("time_slot_enabled") else None
                        if _sel_ts_val:
                            entry["preferred_time_slot"] = _sel_ts_val
                        insert_queue_entry(entry)
                        st.session_state.ticket = entry
                        go("ticket")

# ═══════════════════════════════════════════════════
#  TICKET
# ═══════════════════════════════════════════════════
elif screen == "ticket":
    t = st.session_state.ticket
    if not t:
        go("home")
    else:
        st.markdown('<div style="text-align:center;"><span style="font-size:48px;">✅</span><h2 style="color:#22c55e;">Slot Reserved!</h2></div>', unsafe_allow_html=True)

        pri_badge = ""
        if t.get("lane") == "priority":
            pri_badge = '<div style="margin:4px 0;"><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(245,158,11,.15);color:#f59e0b;">⭐ PRIORITY LANE</span></div>'

        # P3.2: Time slot badge
        ts_badge = ""
        _pts = t.get("preferred_time_slot")
        if _pts:
            _interval = int(branch.get("slot_interval_minutes", 30) or 30)
            try:
                _ph, _pm = map(int, _pts.split(":"))
                _em = _ph * 60 + _pm + _interval
                _eeh, _eem = divmod(_em, 60)
                _ts_disp = f"{format_time_12h(_pts)} – {format_time_12h(f'{_eeh:02d}:{_eem:02d}')}"
            except (ValueError, TypeError):
                _ts_disp = _pts
            ts_badge = f'<div style="margin:4px 0;"><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(34,184,207,.15);color:#22B8CF;">🕐 {_ts_disp}</span></div>'

        # Pre-compute display name and mobile for ticket
        if t.get("last_name"):
            _tdn = f"{t['last_name']}, {t['first_name']} {t.get('mi', '')}".strip()
        elif t.get("bqms_number"):
            _tdn = f"Walk-in #{t['bqms_number']}"
        else:
            _tdn = "Walk-in"
        _tmob = f'<div style="font-size:12px;">📱 {t["mobile"]}</div>' if t.get("mobile") else ""

        st.markdown(f"""<div class="sss-card" style="border-top:4px solid #3399CC;text-align:center;">
<div style="font-size:10px;opacity:.5;letter-spacing:2px;">MABILISSS eQUEUE</div>
<div style="font-size:16px;font-weight:900;color:#3399CC;margin:4px 0;">🏛️ {branch.get('name','').upper()}</div>
<div style="font-weight:700;margin:4px 0;">{t['category']} — {t['service']}</div>
{pri_badge}
{ts_badge}
<div style="border-top:1px dashed rgba(128,128,128,.2);margin:8px 0;"></div>
<div style="font-size:11px;opacity:.5;">RESERVATION NUMBER</div>
<div class="sss-resnum">{t['res_num']}</div>
<div style="border-top:1px dashed rgba(128,128,128,.2);margin:8px 0;"></div>
<div style="font-size:12px;">{_tdn}</div>
{_tmob}
</div>""", unsafe_allow_html=True)

        # P3.2: Time-slot aware instructions
        _ts_note = ""
        if t.get("preferred_time_slot"):
            _ts_note = f'<b>2.</b> 🕐 <strong>Your appointment window is {ts_badge.strip()}</strong>. Please plan to arrive at the branch within this time.<br/>'
            _step_offset = 1
        else:
            _step_offset = 0

        st.markdown(f"""<div class="sss-card" style="border-left:4px solid #0066A1;">
            <strong>📋 What to Do Next:</strong><br/><br/>
            <b>1.</b> Save your Reservation Number: <code style="font-size:16px;font-weight:900;">{t['res_num']}</code><br/>
            {_ts_note}<b>{2 + _step_offset}.</b> <strong>Wait for your official BQMS queue number</strong> — the branch will assign it starting when the branch opens. Tap <strong>"Track My Queue"</strong> to check.<br/>
            <b>{3 + _step_offset}.</b> Once you have your BQMS number, <strong>monitor your position</strong> and <strong>be at {branch.get('name','SSS Branch')} when your number is called.</strong><br/>
            <b>{4 + _step_offset}.</b> ⚠️ If you are not present when your number is called, you will need to queue again, subject to slot availability.<br/>
            <b>{5 + _step_offset}.</b> Need to cancel? Track your queue and tap <strong>Cancel</strong>.
        </div>""", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🏠 Home", use_container_width=True):
                st.session_state.ticket = None
                go("home")
        with c2:
            if st.button("🔍 Track Now", use_container_width=True, type="primary"):
                st.session_state.tracked_id = t["id"]
                go("tracker")

# ═══════════════════════════════════════════════════
#  TRACK INPUT
# ═══════════════════════════════════════════════════
elif screen == "track_input":
    if st.button("← Back to Home"):
        go("home")
    st.markdown('<div style="text-align:center;"><span style="font-size:36px;">🔍</span><h3>Track Your Queue</h3></div>', unsafe_allow_html=True)
    st.caption("💡 Online = **R-** prefix (R-0215-001). Walk-in = **K-** prefix (K-0215-001). BQMS = queue number assigned at branch.")

    track_mode = st.radio("Search by:", ["📱 Mobile Number", "#️⃣ Reservation Number", "🎫 BQMS Number"], horizontal=True)
    with st.form("track_form"):
        if "Mobile" in track_mode:
            track_val = st.text_input("Mobile number", placeholder="09171234567")
        elif "BQMS" in track_mode:
            track_val = st.text_input("BQMS Number", placeholder="1001")
        else:
            track_val = st.text_input("Reservation #", placeholder="R-0215-005 or K-0215-001")

        if st.form_submit_button("🔍 Find My Queue", type="primary", use_container_width=True):
            fresh = get_queue_today()
            v = track_val.strip()
            if not v:
                st.error("Enter a value.")
            else:
                found = None
                if "Mobile" in track_mode:
                    v_clean = validate_mobile_ph(v) or v.strip()
                    # Prefer active entry, fall back to any
                    for r in fresh:
                        r_mob = r.get("mobile", "")
                        if r_mob == v_clean and r.get("status") not in TERMINAL:
                            found = r
                            break
                    if not found:
                        for r in fresh:
                            if r.get("mobile", "") == v_clean:
                                found = r
                                break
                elif "BQMS" in track_mode:
                    vu = v.upper()
                    # Search by BQMS number — prefer active entry
                    for r in fresh:
                        if r.get("bqms_number", "") == vu and r.get("status") not in TERMINAL:
                            found = r
                            break
                    if not found:
                        for r in fresh:
                            if r.get("bqms_number", "") == vu:
                                found = r
                                break
                else:
                    vu = v.upper()
                    for r in fresh:
                        if r.get("res_num") == vu and r.get("status") not in TERMINAL:
                            found = r
                            break
                    if not found:
                        for r in fresh:
                            if r.get("res_num") == vu:
                                found = r
                                break

                if not found:
                    st.error(f"❌ Not found for '{v}'. Check your input or try the other search method.")
                else:
                    st.session_state.tracked_id = found["id"]
                    go("tracker")

# ═══════════════════════════════════════════════════
#  TRACKER (with CANCEL option)
# ═══════════════════════════════════════════════════
elif screen == "tracker":
    tid = st.session_state.tracked_id
    fresh = queue  # Already loaded by load_queue_data() — no redundant DB call
    fbq = bqms     # Already loaded by load_bqms_data() — no redundant DB call
    t = next((r for r in fresh if r.get("id") == tid), None)

    if not t:
        st.error("❌ Entry not found.")
        if st.button("← Try Again"):
            go("track_input")
    else:
        has_bqms = bool(t.get("bqms_number"))
        status = t.get("status", "")
        is_done = status == "COMPLETED"
        is_cancelled = status == "CANCELLED"
        is_void = status == "VOID"
        is_expired = status == "EXPIRED"
        is_terminal = status in TERMINAL
        is_srv = status == "SERVING"

        # ── Status banners ──
        if is_srv:
            st.markdown('<div class="sss-alert sss-alert-blue" style="font-size:18px;">🎉 <strong>YOU\'RE BEING SERVED!</strong></div>', unsafe_allow_html=True)
        elif is_done:
            st.markdown('<div class="sss-alert sss-alert-green">✅ <strong>Transaction Completed</strong> — Thank you for visiting SSS!</div>', unsafe_allow_html=True)
        elif is_cancelled:
            st.markdown('<div class="sss-alert sss-alert-yellow">🚫 <strong>Reservation Cancelled</strong> — Your slot has been released.</div>', unsafe_allow_html=True)
        elif is_void:
            st.markdown(f'<div class="sss-alert sss-alert-yellow">⚙️ <strong>Entry Voided</strong> — {t.get("void_reason","Administrative action")}.</div>', unsafe_allow_html=True)
        elif is_expired:
            st.markdown('<div class="sss-alert sss-alert-yellow">⏰ <strong>Reservation Expired</strong> — This was from a previous day.</div>', unsafe_allow_html=True)

        # ── Entry card ──
        status_color = "#22B8CF" if has_bqms else "#3399CC"
        # P3.2: Time slot badge for tracker
        _trk_ts = t.get("preferred_time_slot")
        _trk_ts_html = ""
        if _trk_ts:
            _ti = int(branch.get("slot_interval_minutes", 30) or 30)
            try:
                _th, _tm = map(int, _trk_ts.split(":"))
                _te = _th * 60 + _tm + _ti
                _teh2, _tem2 = divmod(_te, 60)
                _trk_ts_html = f'<div style="margin:4px 0;"><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(34,184,207,.15);color:#22B8CF;">🕐 {format_time_12h(_trk_ts)} – {format_time_12h(f"{_teh2:02d}:{_tem2:02d}")}</span></div>'
            except (ValueError, TypeError):
                _trk_ts_html = ""
        st.markdown(f"""<div class="sss-card" style="border-top:4px solid {status_color};text-align:center;">
            <div style="font-size:10px;opacity:.5;letter-spacing:1px;">MABILISSS eQUEUE</div>
            <div style="font-size:14px;font-weight:900;color:#3399CC;margin:2px 0;">🏛️ {branch.get('name','').upper()}</div>
            <div style="font-weight:700;margin:4px 0;">{t.get('category','')} — {t.get('service','')}</div>
            <span style="display:inline-block;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;
                background:rgba(51,153,204,.15);color:#3399CC;">
                {STATUS_LABELS.get(status, status)}</span>
            {_trk_ts_html}
        </div>""", unsafe_allow_html=True)

        # ── BQMS and queue position ──
        if has_bqms:
            st.markdown(f'<div class="sss-card" style="text-align:center;"><div style="font-size:11px;opacity:.5;">YOUR BQMS NUMBER</div><div class="sss-bqms">{t["bqms_number"]}</div></div>', unsafe_allow_html=True)

            if not is_terminal:
                cat_obj = next((c for c in cats if c["id"] == t.get("category_id")), None)
                # P3: bqms_state now returns dict with now_serving + now_serving_priority
                bqms_info = fbq.get(t.get("category_id", ""), {})
                if isinstance(bqms_info, str):
                    bqms_info = {"now_serving": bqms_info, "now_serving_priority": ""}
                entry_lane = t.get("lane", "regular")
                # Show the now-serving for the member's own lane
                if entry_lane == "priority" and cat_obj and cat_obj.get("priority_lane_enabled"):
                    ns_val = bqms_info.get("now_serving_priority", "")
                    ns_label = "Now Serving (Priority)"
                else:
                    ns_val = bqms_info.get("now_serving", "")
                    ns_label = "Now Serving"
                ahead = count_ahead(fresh, t)

                m1, m2 = st.columns(2)
                with m1:
                    ns_display = ns_val if ns_val else "—"
                    st.markdown(f'<div class="sss-metric"><div class="val" style="color:#22B8CF;">{ns_display}</div><div class="lbl">{ns_label}</div></div>', unsafe_allow_html=True)
                with m2:
                    st.markdown(f'<div class="sss-metric"><div class="val" style="color:#3399CC;">{t["bqms_number"]}</div><div class="lbl">Your Number</div></div>', unsafe_allow_html=True)

                m3, m4 = st.columns(2)
                with m3:
                    ahead_display = "You're Next!" if ahead == 0 else str(ahead)
                    ahead_color = "#22c55e" if ahead == 0 else "#f59e0b"
                    st.markdown(f'<div class="sss-metric"><div class="val" style="color:{ahead_color};">{ahead_display}</div><div class="lbl">Queue Ahead</div></div>', unsafe_allow_html=True)
                with m4:
                    # V2.3.0: Improved estimated wait (range, actual speed)
                    if ahead == 0:
                        wt = "Any moment!"
                        wt_note = ""
                    else:
                        est_low, est_high, est_src = calc_est_wait(fresh, t, cats)
                        if est_low is not None and est_high is not None:
                            if est_high < 60:
                                wt = f"~{est_low}–{est_high} min"
                            else:
                                wt = f"~{est_low // 60}h{est_low % 60}m–{est_high // 60}h{est_high % 60}m"
                            wt_note = "today's speed" if est_src == "today" else "typical speed"
                        else:
                            avg = cat_obj["avg_time"] if cat_obj else 10
                            est = ahead * avg
                            wt = f"~{est} min" if est < 60 else f"~{est // 60}h {est % 60}m"
                            wt_note = "estimate"
                    st.markdown(f'<div class="sss-metric"><div class="val" style="color:#3399CC;">{wt}</div><div class="lbl">Est. Wait</div></div>', unsafe_allow_html=True)

                # V2.3.0: Wait time disclaimer + proactive guidance
                if ahead == 0:
                    st.markdown('<div class="sss-alert sss-alert-green">🔔 <strong>Your number is next! Please stay near the counter.</strong></div>', unsafe_allow_html=True)
                elif ahead <= 3:
                    st.markdown(f'<div class="sss-alert sss-alert-yellow">⚠️ <strong>Your number is approaching!</strong> Only <b>{ahead}</b> ahead. Please proceed to the waiting area.</div>', unsafe_allow_html=True)
                elif ahead > 3:
                    # Compute estimated serving time for guidance
                    avg = cat_obj.get("avg_time", 10) if cat_obj else 10
                    est_min = round(ahead * avg * 0.75)
                    est_max = round(ahead * avg * 1.35)
                    if est_max >= 30:
                        st.markdown(f"""<div class="sss-alert sss-alert-blue" style="font-size:13px;">
                            💡 You have approximately <b>{est_min}–{est_max} minutes</b> before your turn.
                            Monitor this page and <b>be at the branch when your number is approaching.</b><br/>
                            <span style="font-size:11px;color:#ef4444;">⚠️ If you are not present when called, you will need to queue again, subject to slot availability.</span>
                        </div>""", unsafe_allow_html=True)
                    else:
                        st.caption("⏱ Estimate based on average service speed. Actual wait may vary.")

                if not ns_val:
                    st.caption("💡 'Now Serving' updates automatically when staff processes entries.")
        else:
            # ── V2.3.0: PRE-8AM TRACKER (no BQMS yet) ──
            if not is_terminal:
                st.markdown(f'<div class="sss-card" style="text-align:center;"><div style="font-size:11px;opacity:.5;">RESERVATION NUMBER</div><div class="sss-resnum">{t["res_num"]}</div></div>', unsafe_allow_html=True)

                cat_id = t.get("category_id", "")
                cat_obj_pre = next((c for c in cats if c["id"] == cat_id), None)
                cat_name = cat_obj_pre["label"] if cat_obj_pre else t.get("category", "")
                entry_lane_pre = t.get("lane", "regular")
                # Count at branch for this category
                if cat_obj_pre and cat_obj_pre.get("priority_lane_enabled"):
                    at_branch = count_arrived_in_category(fresh, cat_id, lane=entry_lane_pre)
                    lane_label = "Priority" if entry_lane_pre == "priority" else "Regular"
                else:
                    at_branch = count_arrived_in_category(fresh, cat_id)
                    lane_label = ""
                my_pos = count_reserved_position(fresh, t)
                # Count total online reservations in this category
                total_online = len([e for e in fresh
                                    if e.get("category_id") == cat_id
                                    and e.get("status") == "RESERVED"
                                    and not e.get("bqms_number")
                                    and (not cat_obj_pre or not cat_obj_pre.get("priority_lane_enabled")
                                         or e.get("lane", "regular") == entry_lane_pre)])
                is_arrived = t.get("status") == "ARRIVED"
                batch_time = branch.get("batch_assign_time", "08:00")
                # Time-aware messaging: check if we're before or after batch assign time
                try:
                    bh, bm = [int(x) for x in batch_time.split(":")]
                    batch_passed = now.hour > bh or (now.hour == bh and now.minute >= bm)
                except (ValueError, TypeError):
                    batch_passed = now.hour >= 8

                if is_arrived:
                    # Member is at the branch, checked in, waiting for BQMS assign
                    if batch_passed:
                        st.markdown(f"""<div class="sss-alert sss-alert-green">
                            ✅ <strong>You're checked in!</strong><br/>
                            BQMS numbers are being assigned. Please wait — staff will assign your number shortly.<br/>
                            You are among <b>{at_branch} members</b> at the branch for <b>{cat_name}</b>.
                        </div>""", unsafe_allow_html=True)
                    else:
                        bt_display = format_time_12h(batch_time)
                        st.markdown(f"""<div class="sss-alert sss-alert-green">
                            ✅ <strong>You're checked in!</strong><br/>
                            BQMS numbers will be assigned starting at <b>{bt_display}</b>.<br/>
                            You are among <b>{at_branch} members</b> at the branch for <b>{cat_name}</b>.
                        </div>""", unsafe_allow_html=True)
                else:
                    # Member reserved online, not yet at branch
                    m1, m2 = st.columns(2)
                    with m1:
                        at_color = "#f59e0b" if at_branch > 0 else "#22c55e"
                        st.markdown(f'<div class="sss-metric"><div class="val" style="color:{at_color};">{at_branch}</div><div class="lbl">Members at Branch<br/><span style="font-size:10px;">for {cat_name}</span></div></div>', unsafe_allow_html=True)
                    with m2:
                        st.markdown(f'<div class="sss-metric"><div class="val" style="color:#3399CC;">#{my_pos}</div><div class="lbl">Your Online Position<br/><span style="font-size:10px;">of {total_online} in {cat_name}</span></div></div>', unsafe_allow_html=True)

                    # P3.2: 3-tier messaging based on time slot status
                    _pts_trk = t.get("preferred_time_slot")
                    if _pts_trk:
                        # Has time slot — compute window times for display
                        _ti_trk = int(branch.get("slot_interval_minutes", 30) or 30)
                        try:
                            _pth, _ptm = map(int, _pts_trk.split(":"))
                            _pt_min = _pth * 60 + _ptm
                            _pte = _pt_min + _ti_trk
                            _pteh, _ptem = divmod(_pte, 60)
                            _win_disp = f"{format_time_12h(_pts_trk)} – {format_time_12h(f'{_pteh:02d}:{_ptem:02d}')}"
                            _now_min = now.hour * 60 + now.minute
                            _window_started = _now_min >= _pt_min
                        except (ValueError, TypeError):
                            _win_disp = _pts_trk
                            _window_started = batch_passed

                        if _window_started:
                            # Tier 2: Window has started — assignment coming shortly
                            st.markdown(f"""<div class="sss-alert sss-alert-yellow">
                                ⏳ <strong>Waiting for BQMS Number</strong><br/>
                                Your <strong>🕐 {_win_disp}</strong> window has started. The branch will assign your BQMS number shortly.<br/>
                                <span style="font-size:12px;opacity:.8;">You are online reservation <b>#{my_pos} of {total_online}</b> for <b>{cat_name}</b>.</span><br/>
                                <span style="font-size:12px;opacity:.8;">📱 Your BQMS number will appear here automatically — just tap <b>Refresh</b> to check.</span><br/>
                                <span style="font-size:12px;color:#ef4444;">⚠️ Once assigned, <b>be at {branch.get('name','SSS Branch')} when your number is called.</b> If not present, you will need to queue again, subject to slot availability.</span>
                            </div>""", unsafe_allow_html=True)
                        else:
                            # Tier 1: Window is future — tell member when to expect
                            st.markdown(f"""<div class="sss-alert sss-alert-yellow">
                                ⏳ <strong>Waiting for BQMS Number</strong><br/>
                                You selected the <strong>🕐 {_win_disp}</strong> appointment window.<br/>
                                Your BQMS number will be assigned <strong>starting at {format_time_12h(_pts_trk)}</strong>.<br/>
                                <span style="font-size:12px;opacity:.8;">You are online reservation <b>#{my_pos} of {total_online}</b> for <b>{cat_name}</b>.</span><br/>
                                <span style="font-size:12px;opacity:.8;">📱 Your BQMS number will appear here automatically — just tap <b>Refresh</b> to check.</span><br/>
                                <span style="font-size:12px;color:#ef4444;">⚠️ Once assigned, <b>be at {branch.get('name','SSS Branch')} when your number is called.</b> If not present, you will need to queue again, subject to slot availability.</span>
                            </div>""", unsafe_allow_html=True)
                    elif batch_passed:
                        st.markdown(f"""<div class="sss-alert sss-alert-yellow">
                            ⏳ <strong>Waiting for BQMS Number</strong><br/>
                            The branch is open and will assign your official queue number shortly.<br/>
                            <span style="font-size:12px;opacity:.8;">You are online reservation <b>#{my_pos} of {total_online}</b> for <b>{cat_name}</b>.</span><br/>
                            <span style="font-size:12px;opacity:.8;">📱 Your BQMS number will appear here automatically — just tap <b>Refresh</b> to check.</span><br/>
                            <span style="font-size:12px;color:#ef4444;">⚠️ Once assigned, <b>be at {branch.get('name','SSS Branch')} when your number is called.</b> If not present, you will need to queue again, subject to slot availability.</span>
                        </div>""", unsafe_allow_html=True)
                    else:
                        bt_display = format_time_12h(batch_time)
                        st.markdown(f"""<div class="sss-alert sss-alert-yellow">
                            ⏳ <strong>Waiting for BQMS Number</strong><br/>
                            Your queue number will be assigned starting at <b>{bt_display}</b> when the branch opens.<br/>
                            <span style="font-size:12px;opacity:.8;">You are online reservation <b>#{my_pos} of {total_online}</b> for <b>{cat_name}</b>.</span><br/>
                            <span style="font-size:12px;opacity:.8;">📱 Your BQMS number will appear here automatically — just tap <b>Refresh</b> to check.</span><br/>
                            <span style="font-size:12px;color:#ef4444;">⚠️ Once assigned, <b>be at {branch.get('name','SSS Branch')} when your number is called.</b> If not present, you will need to queue again, subject to slot availability.</span>
                        </div>""", unsafe_allow_html=True)

        # ── Action buttons ──
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Refresh", use_container_width=True, type="primary"):
                st.rerun()
        with c2:
            if st.button("🔍 Track Another", use_container_width=True):
                st.session_state.tracked_id = None
                go("track_input")

        # ── CANCEL BUTTON (member self-service) ──
        # Available for RESERVED and ARRIVED (before SERVING)
        if status in ("RESERVED", "ARRIVED"):
            st.markdown("---")
            st.markdown(f"""<div class="sss-card" style="border-left:4px solid #ef4444;">
                <strong>Need to cancel?</strong><br/>
                <span style="font-size:13px;opacity:.7;">
                Your slot will be released for other members. You may reserve again tomorrow.</span>
            </div>""", unsafe_allow_html=True)

            # Use session state for confirmation to avoid accidental cancels
            if f"confirm_cancel_{tid}" not in st.session_state:
                st.session_state[f"confirm_cancel_{tid}"] = False

            if not st.session_state[f"confirm_cancel_{tid}"]:
                if st.button("🚫 Cancel My Reservation", use_container_width=True):
                    st.session_state[f"confirm_cancel_{tid}"] = True
                    st.rerun()
            else:
                st.warning("⚠️ Are you sure? This cannot be undone.")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Yes, Cancel", type="primary", use_container_width=True):
                        cancel_entry(tid)
                        st.session_state[f"confirm_cancel_{tid}"] = False
                        st.rerun()
                with cc2:
                    if st.button("← Keep It", use_container_width=True):
                        st.session_state[f"confirm_cancel_{tid}"] = False
                        st.rerun()

        # ── Auto-refresh note ──
        if not is_terminal:
            st.caption(f"🔄 Auto-refreshes every 60s · Last: {now.strftime('%I:%M:%S %p')} PHT")

# ═══════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown(f"""<div style="text-align:center;font-size:10px;opacity:.3;padding:8px;">
    RPTayo / SSS-MND · MabiliSSS eQueue {VER}
</div>""", unsafe_allow_html=True)
