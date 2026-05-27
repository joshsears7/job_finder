import streamlit as st
import os
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, xe
from job_market import get_macro_snapshot, get_sector_changes, get_job_news, BLS_PROJECTIONS

inject_css()

st.markdown(
    "<div class='page-title'>Market Intelligence</div>"
    "<div class='page-sub'>Live economic data · BLS 10-year projections · Hiring signals from HackerNews & GitHub.</div>",
    unsafe_allow_html=True
)

tab_macro, tab_bls, tab_signals = st.tabs(["Macro & FRED", "BLS Outlook", "Hiring Signals"])

# ── Macro & FRED ──────────────────────────────────────────────────
with tab_macro:
    has_fred = bool(os.getenv("FRED_KEY", "").strip())

    if not has_fred:
        st.markdown(
            alert(
                "Add <b>FRED_KEY</b> to Streamlit secrets for live FRED data. "
                "Free at <a href='https://fred.stlouisfed.org/docs/api/api_key.html' "
                "target='_blank' style='color:#93c5fd'>fred.stlouisfed.org</a> (2 minutes). "
                "Headlines below are always available.",
                "amber"
            ),
            unsafe_allow_html=True
        )

    if has_fred:
        if st.button("Load Live FRED Data", type="primary", key="load_fred") or st.session_state.get("fred_data"):
            if not st.session_state.get("fred_data"):
                with st.spinner("Fetching FRED data…"):
                    try:
                        macro   = get_macro_snapshot()
                        sectors = get_sector_changes()
                        if macro:
                            st.session_state["fred_data"]   = macro
                            st.session_state["sector_data"] = sectors
                        else:
                            st.warning("FRED returned no data — check your FRED_KEY or try again.")
                    except Exception as e:
                        st.error(f"FRED fetch failed: {e}")

            macro   = st.session_state.get("fred_data", {})
            sectors = st.session_state.get("sector_data", {})

            if macro:
                c1, c2 = st.columns([6, 1])
                with c1:
                    st.markdown("<div class='section-tag'>Key Macro Indicators</div>", unsafe_allow_html=True)
                with c2:
                    if st.button("Refresh", key="refresh_fred", help="Reload FRED data"):
                        st.session_state.pop("fred_data", None)
                        st.session_state.pop("sector_data", None)
                        st.rerun()

                cols = st.columns(min(len(macro), 5))
                for i, (name, data) in enumerate(list(macro.items())[:5]):
                    if i >= len(cols):
                        break
                    val   = data.get("latest", "—")
                    prev  = data.get("prev", None)
                    delta = None
                    if isinstance(val, (int, float)) and isinstance(prev, (int, float)):
                        delta = round(val - prev, 2)
                    cols[i].metric(name, f"{val:,.1f}" if isinstance(val, float) else str(val),
                                   f"{delta:+.2f}" if delta is not None else None)

            if sectors:
                st.markdown("<div class='section-tag' style='margin-top:16px'>Sector Employment Trends</div>", unsafe_allow_html=True)
                sec_cols = st.columns(2)
                for i, (sector, data) in enumerate(list(sectors.items())[:8]):
                    col = sec_cols[i % 2]
                    latest = data.get("latest", 0)
                    change = data.get("change", 0)
                    color  = "#10b981" if change >= 0 else "#ef4444"
                    col.markdown(
                        f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px'>"
                        f"<div style='font-size:12px;font-weight:700;color:#e2e8f0'>{xe(sector)}</div>"
                        f"<div style='display:flex;justify-content:space-between;margin-top:4px'>"
                        f"<span style='font-size:11px;color:#64748b'>{latest:,.0f}k employed</span>"
                        f"<span style='font-size:11px;font-weight:700;color:{color}'>"
                        f"{'+' if change>=0 else ''}{change:,.1f}k MoM</span>"
                        f"</div></div>",
                        unsafe_allow_html=True
                    )

    # News headlines — auto-load on first visit
    st.markdown("<div class='section-tag' style='margin-top:16px'>Job Market News</div>", unsafe_allow_html=True)

    if "job_news" not in st.session_state:
        with st.spinner("Loading headlines…"):
            try:
                news = get_job_news()
                st.session_state["job_news"] = news or []
            except Exception:
                st.session_state["job_news"] = []

    news = st.session_state.get("job_news", [])

    if news:
        rc1, rc2 = st.columns([6, 1])
        with rc2:
            if st.button("Refresh", key="refresh_news", help="Reload headlines"):
                st.session_state.pop("job_news", None)
                st.rerun()
        for item in news:
            title  = item.get("title", "")
            link   = item.get("link", "")
            pub    = item.get("date", "")
            source = item.get("source", "")
            if title:
                st.markdown(
                    f"<div class='card-slate' style='padding:12px 16px;margin-bottom:6px'>"
                    f"<a href='{xe(link)}' target='_blank' style='color:#93c5fd;font-weight:600;"
                    f"font-size:13.5px;text-decoration:none'>{xe(title)}</a>"
                    f"<div style='font-size:11px;color:#475569;margin-top:4px'>"
                    f"{xe(source)} · {xe(pub)}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
    else:
        st.markdown(
            "<div class='card-slate' style='padding:16px;text-align:center;color:#475569'>"
            "No headlines loaded — RSS feeds may be unavailable. "
            "<a href='https://www.bbc.com/news/business' target='_blank' style='color:#93c5fd'>"
            "BBC Business</a> · "
            "<a href='https://www.npr.org/sections/economy/' target='_blank' style='color:#93c5fd'>"
            "NPR Economy</a>"
            "</div>",
            unsafe_allow_html=True
        )
        if st.button("Try again", key="retry_news"):
            st.session_state.pop("job_news", None)
            st.rerun()

# ── BLS Outlook ───────────────────────────────────────────────────
with tab_bls:
    st.markdown("<div class='section-tag'>BLS 2023–2033 Employment Projections</div>", unsafe_allow_html=True)
    st.caption("Official Bureau of Labor Statistics 10-year outlook. Updated semi-annually.")

    col_grow, col_dec = st.columns(2)
    with col_grow:
        st.markdown(
            "<div style='font-size:13px;font-weight:700;color:#10b981;margin-bottom:10px'>"
            "Fastest Growing Roles</div>",
            unsafe_allow_html=True
        )
        for role, pct, sector in BLS_PROJECTIONS["fastest_growing"]:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:8px 0;border-bottom:1px solid #1e293b'>"
                f"<div><div style='font-size:13px;color:#e2e8f0;font-weight:600'>{xe(role)}</div>"
                f"<div style='font-size:11px;color:#64748b'>{xe(sector)}</div></div>"
                f"<div style='font-size:14px;font-weight:900;color:#10b981;"
                f"flex-shrink:0;margin-left:12px'>{xe(pct)}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    with col_dec:
        st.markdown(
            "<div style='font-size:13px;font-weight:700;color:#ef4444;margin-bottom:10px'>"
            "Fastest Declining Roles</div>",
            unsafe_allow_html=True
        )
        for role, pct, sector in BLS_PROJECTIONS["fastest_declining"]:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:8px 0;border-bottom:1px solid #1e293b'>"
                f"<div><div style='font-size:13px;color:#e2e8f0;font-weight:600'>{xe(role)}</div>"
                f"<div style='font-size:11px;color:#64748b'>{xe(sector)}</div></div>"
                f"<div style='font-size:14px;font-weight:900;color:#ef4444;"
                f"flex-shrink:0;margin-left:12px'>{xe(pct)}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.markdown("<div class='section-tag' style='margin-top:24px'>Hot Sectors Right Now</div>", unsafe_allow_html=True)
    for sector_title, narrative in BLS_PROJECTIONS["hot_sectors_narrative"]:
        with st.expander(sector_title):
            st.markdown(
                f"<div style='font-size:13.5px;color:#cbd5e1;line-height:1.7'>{xe(narrative)}</div>",
                unsafe_allow_html=True
            )

# ── Hiring Signals ────────────────────────────────────────────────
with tab_signals:
    hdr_c, btn_c = st.columns([6, 1])
    with hdr_c:
        st.markdown("<div class='section-tag'>HackerNews & GitHub Hiring Intelligence</div>", unsafe_allow_html=True)
        st.caption("Live signals from HackerNews 'Who is Hiring?' and GitHub trending repos. Cached 4 hours.")
    with btn_c:
        if st.button("Refresh", key="refresh_signals", help="Clear cache and reload"):
            st.session_state.pop("market_intel", None)
            st.rerun()

    # Auto-load on first visit
    if "market_intel" not in st.session_state:
        with st.spinner("Loading hiring signals — fetching HackerNews & GitHub (may take 20–40 s)…"):
            try:
                from market_intel import get_market_intel
                intel = get_market_intel()
                st.session_state["market_intel"] = intel
            except Exception as e:
                st.session_state["market_intel"] = {}
                st.error(f"Failed to load hiring signals: {e}")

    intel = st.session_state.get("market_intel", {})

    if not intel or not any(v for v in intel.values()):
        st.markdown(
            "<div class='card-slate' style='padding:20px;text-align:center'>"
            "<div style='font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:8px'>"
            "Hiring signals unavailable right now</div>"
            "<div style='font-size:13px;color:#64748b'>"
            "HackerNews or GitHub APIs may be temporarily slow. Hit Refresh to try again."
            "</div></div>",
            unsafe_allow_html=True
        )
    else:
        hn_col, gh_col = st.columns(2)

        with hn_col:
            st.markdown(
                "<div style='font-size:12px;font-weight:700;color:#f59e0b;"
                "text-transform:uppercase;margin-bottom:12px'>HackerNews Who's Hiring</div>",
                unsafe_allow_html=True
            )
            if intel.get("hn_title"):
                st.markdown(
                    f"<div style='font-size:12px;color:#64748b;margin-bottom:12px'>"
                    f"Thread: {xe(intel['hn_title'])}</div>",
                    unsafe_allow_html=True
                )

            hn_skills = intel.get("hn_skills", [])
            if hn_skills:
                st.markdown(
                    "<div style='font-size:12px;color:#94a3b8;margin-bottom:8px'>"
                    "Most-mentioned skills in job posts:</div>",
                    unsafe_allow_html=True
                )
                for term, count in hn_skills[:18]:
                    bar_pct = min(100, int(count / max(hn_skills[0][1], 1) * 100))
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px'>"
                        f"<div style='font-size:12px;color:#e2e8f0;width:130px;flex-shrink:0'>{xe(term)}</div>"
                        f"<div style='background:#1e293b;border-radius:4px;height:8px;flex:1'>"
                        f"<div style='background:#3b82f6;width:{bar_pct}%;height:8px;border-radius:4px'>"
                        f"</div></div>"
                        f"<div style='font-size:11px;color:#64748b;width:30px;text-align:right'>{count}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
            else:
                st.markdown(
                    "<div style='font-size:13px;color:#475569;padding:12px 0'>"
                    "HackerNews data unavailable right now.</div>",
                    unsafe_allow_html=True
                )

        with gh_col:
            st.markdown(
                "<div style='font-size:12px;font-weight:700;color:#10b981;"
                "text-transform:uppercase;margin-bottom:12px'>GitHub Trending</div>",
                unsafe_allow_html=True
            )

            gh_langs = intel.get("gh_languages", [])
            gh_repos = intel.get("gh_repos", [])

            if not gh_repos:
                st.markdown(
                    "<div style='font-size:13px;color:#475569;padding:4px 0'>"
                    "GitHub data unavailable — rate limited. "
                    "Add <b style='color:#e2e8f0'>GITHUB_TOKEN</b> to Streamlit secrets for reliable access."
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                if gh_langs:
                    st.markdown(
                        "<div style='font-size:12px;color:#94a3b8;margin-bottom:8px'>"
                        "Top languages in trending repos:</div>",
                        unsafe_allow_html=True
                    )
                    for lang, count in gh_langs[:10]:
                        bar_pct = min(100, int(count / max(gh_langs[0][1], 1) * 100))
                        st.markdown(
                            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px'>"
                            f"<div style='font-size:12px;color:#e2e8f0;width:100px;flex-shrink:0'>{xe(lang)}</div>"
                            f"<div style='background:#1e293b;border-radius:4px;height:8px;flex:1'>"
                            f"<div style='background:#10b981;width:{bar_pct}%;height:8px;border-radius:4px'>"
                            f"</div></div>"
                            f"<div style='font-size:11px;color:#64748b;width:30px;text-align:right'>{count}</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                st.markdown(
                    "<div style='font-size:12px;color:#94a3b8;margin-top:14px;margin-bottom:8px'>"
                    "Trending repos this month:</div>",
                    unsafe_allow_html=True
                )
                for repo in gh_repos[:8]:
                    stars = repo.get("stars", 0)
                    lang  = repo.get("language", "")
                    desc  = (repo.get("description", "") or "")[:80]
                    url   = repo.get("url", "")
                    st.markdown(
                        f"<div style='padding:8px 0;border-bottom:1px solid #1e293b'>"
                        f"<a href='{xe(url)}' target='_blank' style='color:#93c5fd;font-size:12.5px;"
                        f"font-weight:600'>{xe(repo['name'])}</a>"
                        f"<span style='font-size:11px;color:#64748b;margin-left:8px'>"
                        f"⭐{stars:,} · {xe(lang)}</span>"
                        f"<div style='font-size:11.5px;color:#64748b;margin-top:2px'>{xe(desc)}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

        jobicy_skills = intel.get("jobicy_skills", [])
        if jobicy_skills:
            st.markdown("---")
            st.markdown("<div class='section-tag'>Live Job Posting Skill Demand (Jobicy)</div>", unsafe_allow_html=True)
            st.caption("Skill mentions across live remote job postings right now.")
            jc_cols = st.columns(2)
            for i, (term, count) in enumerate(jobicy_skills[:16]):
                bar_pct = min(100, int(count / max(jobicy_skills[0][1], 1) * 100))
                jc_cols[i % 2].markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px'>"
                    f"<div style='font-size:12px;color:#e2e8f0;width:130px;flex-shrink:0'>{xe(term)}</div>"
                    f"<div style='background:#1e293b;border-radius:4px;height:8px;flex:1'>"
                    f"<div style='background:#8b5cf6;width:{bar_pct}%;height:8px;border-radius:4px'></div></div>"
                    f"<div style='font-size:11px;color:#64748b;width:30px;text-align:right'>{count}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
