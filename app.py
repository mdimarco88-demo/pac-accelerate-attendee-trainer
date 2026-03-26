import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "PAC Accelerate Guest Trainer"
DATA_PATH = "data/accelerate_attendees.csv"

SPORT_TERMS = {
    "Football": ["NFL", "football", "quarterback", "running back", "wide receiver", "linebacker", "cornerback", "safety", "tight end", "offensive tackle", "defensive end"],
    "Basketball": ["NBA", "basketball", "guard", "forward", "center"],
    "Baseball": ["MLB", "baseball", "pitcher", "outfielder", "infielder", "catcher"],
    "Soccer": ["soccer", "footballer", "Premier League", "MLS"],
    "Golf": ["golf", "PGA", "LPGA"],
    "Hockey": ["NHL", "hockey"],
    "Tennis": ["tennis"],
    "Olympics": ["Olympic", "track and field", "swimmer", "gymnast"],
    "Volleyball": ["volleyball"],
    "Softball": ["softball"],
    "Track and Field": ["track and field", "Olympic"],
    "Rugby": ["rugby"],
    "Jockey": ["horse racing", "jockey"],
    "Pro Fighting": ["MMA", "boxing", "fighter", "martial artist"],
}

POSITION_KEYWORDS = [
    "quarterback","running back","wide receiver","tight end","offensive tackle","offensive guard","center",
    "defensive tackle","defensive end","edge rusher","linebacker","inside linebacker","outside linebacker",
    "cornerback","safety","kicker","punter","long snapper",
    "point guard","shooting guard","small forward","power forward","center",
    "pitcher","catcher","first baseman","second baseman","third baseman","shortstop","outfielder","designated hitter",
    "goalkeeper","defender","midfielder","forward",
    "golfer","tennis player","fighter","boxer","wrestler","jockey","coach","executive","agent","analyst"
]

TEAM_PATTERNS = [
    r"for the ([A-Z][A-Za-z0-9&.\- ]+?) of the ",
    r"with the ([A-Z][A-Za-z0-9&.\- ]+?) of the ",
    r"for ([A-Z][A-Za-z0-9&.\- ]+?) of the ",
    r"played for the ([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\.| and )",
    r"is the ([A-Za-z0-9&.\- ]+?) at ([A-Z][A-Za-z0-9&.\- ]+?)(?:,|\.|$)",
]

def normalize_text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()

@st.cache_data(ttl=60 * 60)
def load_attendees(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    expected = ["full_name","sport","pro_league","email","phone","type_guess","organization_hint",
                "title_override","organization_override","position_override","image_url_override","notes"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    for col in expected:
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df

@st.cache_data(ttl=24 * 60 * 60)
def wiki_search(name: str, sport_hint: str, type_guess: str) -> Dict:
    query = name
    if sport_hint:
        query += f" {sport_hint}"
    elif type_guess == "executive":
        query += " executive"

    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 5,
        }
        r = requests.get("https://en.wikipedia.org/w/api.php", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        results = (data.get("query", {}) or {}).get("search", [])
        if not results:
            return {}

        best = None
        best_score = -999
        hint_terms = SPORT_TERMS.get(sport_hint, [])
        for res in results:
            title = (res.get("title") or "")
            snippet = re.sub(r"<.*?>", "", res.get("snippet") or "")
            text = f"{title} {snippet}".lower()
            score = 0
            if title.lower() == name.lower():
                score += 12
            elif name.lower() in title.lower():
                score += 8
            if sport_hint and sport_hint.lower() in text:
                score += 6
            for term in hint_terms:
                if term.lower() in text:
                    score += 2
            if type_guess == "executive" and any(k in text for k in ["executive","ceo","founder","president","chairman","business"]):
                score += 3
            if type_guess == "athlete" and any(k in text for k in ["player","athlete","football","basketball","baseball","golfer"]):
                score += 3
            if score > best_score:
                best = res
                best_score = score

        if not best:
            return {}

        title = best.get("title", "")
        encoded_title = quote(title.replace(" ", "_"))
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        r2 = requests.get(summary_url, timeout=20)
        if r2.status_code != 200:
            return {"title": title}
        s = r2.json()
        return {
            "title": s.get("title", title),
            "description": s.get("description", ""),
            "extract": s.get("extract", ""),
            "image_url": (s.get("thumbnail") or {}).get("source", "") or (s.get("originalimage") or {}).get("source", ""),
            "content_urls": s.get("content_urls", {}),
        }
    except Exception:
        return {}

def infer_position(text: str) -> str:
    lower = (text or "").lower()
    for kw in POSITION_KEYWORDS:
        if kw in lower:
            return kw.title()
    return ""

def infer_association(text: str) -> str:
    if not text:
        return ""
    for pat in TEAM_PATTERNS:
        m = re.search(pat, text)
        if m:
            value = m.group(1).strip()
            value = re.sub(r"\s+", " ", value)
            return value
    return ""

def domain_org(email: str, org_hint: str) -> str:
    if org_hint:
        return org_hint
    email = normalize_text(email).lower()
    if "@" not in email:
        return ""
    domain = email.split("@", 1)[1]
    if domain in {"gmail.com","yahoo.com","hotmail.com","outlook.com","icloud.com","mac.com","me.com","aol.com","proton.me","protonmail.com"}:
        return ""
    core = domain.split(".")[-2] if "." in domain else domain
    core = core.replace("-", " ").replace("_", " ").strip()
    return core.title()

@st.cache_data(ttl=24 * 60 * 60)
def enrich_person(row: Dict) -> Dict:
    sport = row.get("sport", "")
    type_guess = row.get("type_guess", "") or ("executive" if not sport else "athlete")
    wiki = wiki_search(row.get("full_name", ""), sport, type_guess)

    description = wiki.get("description", "")
    extract = wiki.get("extract", "")
    text = f"{description}. {extract}".strip()

    image_url = row.get("image_url_override") or wiki.get("image_url", "")
    position = row.get("position_override") or infer_position(text)
    association = row.get("organization_override") or infer_association(extract)

    if type_guess == "executive":
        title = row.get("title_override") or description.title() if description else ""
        organization = association or domain_org(row.get("email", ""), row.get("organization_hint", ""))
        if not organization and row.get("organization_override"):
            organization = row.get("organization_override")
    else:
        title = position
        organization = association or row.get("organization_override", "") or row.get("organization_hint", "")

    if not title and type_guess == "athlete" and sport:
        title = sport
    if not organization and row.get("pro_league"):
        organization = row.get("pro_league")

    return {
        **row,
        "wiki_title": wiki.get("title", ""),
        "wiki_description": description,
        "wiki_extract": extract,
        "wiki_url": ((wiki.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
        "image_url": image_url,
        "display_role": title,
        "display_org": organization,
        "entity_type": type_guess,
    }

def show_image(person: Dict):
    url = person.get("image_url", "")
    if not url:
        st.caption("No headshot found.")
        return
    st.markdown(
        f'<div style="width:100%; display:flex; justify-content:center;">'
        f'<img src="{url}" style="max-width:100%; max-height:420px; height:auto; border-radius:12px;" '
        f'onerror="this.style.display=\'none\'" /></div>',
        unsafe_allow_html=True,
    )

def init_state():
    st.session_state.setdefault("mode", "Quiz")
    st.session_state.setdefault("current_index", 0)
    st.session_state.setdefault("reveal", False)
    st.session_state.setdefault("clear_inputs", False)
    st.session_state.setdefault("order", [])
    if st.session_state.clear_inputs:
        for k in ["guess_name","guess_role","guess_org"]:
            st.session_state[k] = ""
        st.session_state.clear_inputs = False

def build_order(df: pd.DataFrame, shuffle: bool) -> List[int]:
    idx = list(df.index)
    if shuffle:
        import random
        random.shuffle(idx)
    return idx

def current_person(df: pd.DataFrame) -> Dict:
    order = st.session_state.order
    if not order:
        st.session_state.order = build_order(df, shuffle=True)
        order = st.session_state.order
    return enrich_person(df.loc[order[st.session_state.current_index]].to_dict())

def next_person(df: pd.DataFrame):
    if st.session_state.current_index + 1 >= len(st.session_state.order):
        st.session_state.current_index = 0
    else:
        st.session_state.current_index += 1
    st.session_state.reveal = False
    st.session_state.clear_inputs = True

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.caption("Private event trainer for Accelerate attendees. Uses your attendee CSV and live Wikipedia lookups for headshots and public bio hints.")

init_state()
df = load_attendees(DATA_PATH)

with st.sidebar:
    st.header("Filters")
    types = sorted([v for v in df["type_guess"].unique().tolist() if v])
    selected_types = st.multiselect("Guest type", options=types, default=types)
    sports = sorted([v for v in df["sport"].unique().tolist() if v])
    selected_sports = st.multiselect("Sport", options=sports, default=[])
    leagues = sorted([v for v in df["pro_league"].unique().tolist() if v])
    selected_leagues = st.multiselect("League", options=leagues, default=[])
    name_filter = st.text_input("Search name")
    mode = st.radio("Mode", options=["Quiz", "Flash", "Reveal"], index=["Quiz","Flash","Reveal"].index(st.session_state.mode))
    st.session_state.mode = mode
    reshuffle = st.button("Reshuffle order")
    st.caption("Tip: fill any *_override columns in the CSV to manually correct titles, orgs, positions, or images.")

view = df.copy()
if selected_types:
    view = view[view["type_guess"].isin(selected_types)]
if selected_sports:
    view = view[view["sport"].isin(selected_sports)]
if selected_leagues:
    view = view[view["pro_league"].isin(selected_leagues)]
if name_filter:
    view = view[view["full_name"].str.contains(name_filter, case=False, na=False)]

view = view.reset_index(drop=True)

if len(view) == 0:
    st.warning("No attendees match your current filters.")
    st.stop()

if not st.session_state.order or reshuffle:
    st.session_state.order = build_order(view, shuffle=True)
    st.session_state.current_index = 0

if len(st.session_state.order) != len(view):
    st.session_state.order = build_order(view, shuffle=True)
    st.session_state.current_index = 0

person = current_person(view)

c1, c2, c3 = st.columns(3)
c1.metric("Guests in pool", len(view))
c2.metric("Current guest", st.session_state.current_index + 1)
c3.metric("Type", person.get("entity_type","").title())

st.divider()
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("Face")
    show_image(person)
    if st.session_state.mode == "Reveal" or st.session_state.reveal:
        st.markdown(f"### **{person.get('full_name','')}**")
    else:
        st.markdown("### (Answer first)")

with right:
    st.subheader("Recall")
    if st.session_state.mode == "Flash":
        st.markdown(f"### **{person.get('full_name','')}**")
        label1 = "Sport" if person.get("entity_type") == "athlete" else "Title"
        label2 = "Team/Org"
        st.write(f"**{label1}:** {person.get('display_role','') or 'Unknown'}")
        st.write(f"**{label2}:** {person.get('display_org','') or 'Unknown'}")
        if person.get("sport"):
            st.write(f"**Sport:** {person.get('sport')}")
        if person.get("wiki_extract"):
            st.caption(person.get("wiki_extract"))
        if st.button("Next now", type="primary"):
            next_person(view)
            st.rerun()
        st.caption("Flash mode shows the answer immediately. Use Reshuffle anytime.")
    else:
        st.write("Study the face first, then guess the person.")
        st.text_input("Name", key="guess_name")
        if person.get("entity_type") == "athlete":
            st.text_input("Position / sport role", key="guess_role")
            st.text_input("Most-known team / current org", key="guess_org")
        else:
            st.text_input("Title", key="guess_role")
            st.text_input("Current organization", key="guess_org")

        a, b, c = st.columns(3)
        if a.button("Reveal", type="secondary"):
            st.session_state.reveal = True
        if b.button("Next", type="primary"):
            next_person(view)
            st.rerun()

        if st.session_state.reveal or st.session_state.mode == "Reveal":
            st.markdown(f"### **{person.get('full_name','')}**")
            label1 = "Position / role" if person.get("entity_type") == "athlete" else "Title"
            st.write(f"**{label1}:** {person.get('display_role','') or 'Unknown'}")
            st.write(f"**Most-known team / org:** {person.get('display_org','') or 'Unknown'}")
            if person.get("sport"):
                st.write(f"**Sport:** {person.get('sport')}")
            if person.get("pro_league"):
                st.write(f"**League:** {person.get('pro_league')}")
            if person.get("wiki_extract"):
                st.caption(person.get("wiki_extract"))
            if person.get("wiki_url"):
                st.markdown(f"[Open source page]({person.get('wiki_url')})")

with st.expander("Show current filtered list"):
    st.dataframe(view[["full_name","type_guess","sport","pro_league","organization_hint"]], use_container_width=True)
