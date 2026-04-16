"""
Umumiy UI: tema tokenlari, responsive CSS, session state.
"""
import streamlit as st


def init_state():
    defaults = {
        "stt_engine": None,
        "search_engine": None,
        "segments": [],
        "video_path": None,
        "video_name": None,
        "index_built": False,
        "processing": False,
        "play_timestamp": 0,
        "last_results": [],
        "engine_name": "",
        "video_duration": 0,
        "whisper_model": "base",
        "target_lang": "uz",
        "theme": "dark",
        "tts_engine": "Muxlisa",
        "engine_choice": "Muxlisa AI (Uzbek Pro)",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def apply_theme_from_query_params():
    requested_theme = st.query_params.get("set_theme")
    if isinstance(requested_theme, list):
        requested_theme = requested_theme[0] if requested_theme else None
    if requested_theme in ("dark", "light") and requested_theme != st.session_state.theme:
        st.session_state.theme = requested_theme


def inject_global_styles():
    if st.session_state.theme == "light":
        bg_color = "#f4f1ec"
        sec_bg_color = "#ebe6df"
        surface_color = "#fffcf7"
        text_color = "#1c1917"
        muted_text = "#6b6560"
        glass_border = "rgba(28, 25, 23, 0.12)"
        primary_color = "#c2410c"
        primary_hover = "#ea580c"
        accent_glow = "rgba(194, 65, 12, 0.08)"
        focus_ring = "rgba(194, 65, 12, 0.28)"
        exp_bg = "#f0ebe4"
        exp_hover = "#e5ddd3"
        exp_text = "#292524"
        shadow_soft = "0 4px 24px rgba(28, 25, 23, 0.06)"
        shadow_strong = "0 12px 40px rgba(28, 25, 23, 0.1)"
        success_color = "#15803d"
        warning_color = "#b45309"
        danger_color = "#b91c1c"
        brand_gradient = "linear-gradient(105deg, #9a3412 0%, #ea580c 48%, #d97706 100%)"
        button_text = "#fffcf7"
    else:
        bg_color = "#0a0a0c"
        sec_bg_color = "#131316"
        surface_color = "#1a1a1f"
        text_color = "#f5f2eb"
        muted_text = "#a8a29e"
        glass_border = "rgba(245, 242, 235, 0.09)"
        primary_color = "#fbbf24"
        primary_hover = "#fcd34d"
        accent_glow = "rgba(251, 191, 36, 0.12)"
        focus_ring = "rgba(251, 191, 36, 0.35)"
        exp_bg = "#1f1f24"
        exp_hover = "#27272e"
        exp_text = "#e7e5e4"
        shadow_soft = "0 4px 28px rgba(0, 0, 0, 0.45)"
        shadow_strong = "0 16px 48px rgba(0, 0, 0, 0.55)"
        success_color = "#4ade80"
        warning_color = "#fbbf24"
        danger_color = "#f87171"
        brand_gradient = "linear-gradient(105deg, #b45309 0%, #f59e0b 45%, #fbbf24 100%)"
        button_text = "#1c1917"

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Syne:wght@600;700;800&display=swap');

    :root {{
        --bg-color: {bg_color};
        --sec-bg-color: {sec_bg_color};
        --surface-color: {surface_color};
        --text-color: {text_color};
        --muted-text: {muted_text};
        --glass-border: {glass_border};
        --primary-color: {primary_color};
        --primary-hover: {primary_hover};
        --focus-ring: {focus_ring};
        --exp-bg: {exp_bg};
        --exp-hover: {exp_hover};
        --exp-text: {exp_text};
        --shadow-soft: {shadow_soft};
        --shadow-strong: {shadow_strong};
        --success-color: {success_color};
        --warning-color: {warning_color};
        --danger-color: {danger_color};
        --brand-gradient: {brand_gradient};
        --button-text: {button_text};
    }}

    /* ── Typography & Global ── */
    html, body, [class*="css"] {{
        font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
    }}

    .stApp {{
        background-color: var(--bg-color) !important;
        background-image: radial-gradient(ellipse 120% 80% at 100% -20%, {accent_glow}, transparent 50%),
            radial-gradient(ellipse 80% 50% at -10% 100%, {accent_glow}, transparent 45%) !important;
        color: var(--text-color) !important;
        transition: background-color 0.35s ease, color 0.35s ease;
    }}

    /* Ensure all markdown text respects the theme */
    .stMarkdown p, .stMarkdown div, .stMarkdown span {{
        color: var(--text-color) !important;
    }}

    /* ── Streamlit Element Overrides ── */
    header[data-testid="stHeader"], [data-testid="stHeader"] {{
        background-color: var(--bg-color) !important;
    }}
    header[data-testid="stHeader"] button, header[data-testid="stHeader"] a {{
        color: var(--primary-color) !important;
    }}
    /* Sidebar collapse/expand tugmasi (lightda ham aniq ko'rinsin) */
    button[aria-label="Collapse sidebar"],
    button[aria-label="Expand sidebar"],
    button[aria-label="Close sidebar"],
    button[aria-label="Open sidebar"],
    [data-testid="collapsedControl"] button,
    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="stSidebar"] button[kind="header"],
    [data-testid="stSidebar"] button[kind="icon"] {{
        color: var(--text-color) !important;
        background: color-mix(in srgb, var(--surface-color) 85%, transparent) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 10px !important;
        opacity: 1 !important;
    }}
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] {{
        opacity: 1 !important;
    }}
    button[aria-label="Collapse sidebar"] svg,
    button[aria-label="Expand sidebar"] svg,
    button[aria-label="Close sidebar"] svg,
    button[aria-label="Open sidebar"] svg,
    [data-testid="collapsedControl"] button svg,
    [data-testid="stSidebarCollapsedControl"] button svg,
    [data-testid="stSidebar"] button[kind="header"] svg,
    [data-testid="stSidebar"] button[kind="icon"] svg,
    [data-testid="stSidebar"] button[kind="header"] path,
    [data-testid="stSidebar"] button[kind="icon"] path,
    [data-testid="stSidebar"] button[kind="header"] span,
    [data-testid="stSidebar"] button[kind="icon"] span {{
        fill: var(--text-color) !important;
        stroke: var(--text-color) !important;
        color: var(--text-color) !important;
    }}
    [data-testid="collapsedControl"] *,
    [data-testid="stSidebarCollapsedControl"] * {{
        color: var(--text-color) !important;
        fill: var(--text-color) !important;
        stroke: var(--text-color) !important;
        opacity: 1 !important;
    }}
    /* Light rejimda aynan qora ko'rinsin */
    .stApp:has([data-testid="stSidebar"]) [data-testid="collapsedControl"] *,
    .stApp:has([data-testid="stSidebar"]) [data-testid="stSidebarCollapsedControl"] * {{
        color: #1c1917 !important;
        fill: #1c1917 !important;
        stroke: #1c1917 !important;
    }}

    /* ALL Expanders (Aggressive Fix) */
    .streamlit-expanderHeader, 
    [data-testid="stExpander"], 
    .stExpander {{
        background-color: var(--exp-bg) !important;
        border-radius: 15px !important;
        border: 1px solid var(--glass-border) !important;
        margin-bottom: 0.5rem !important;
        transition: all 0.3s ease !important;
    }}
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary:hover {{
        background-color: var(--exp-bg) !important;
        color: var(--exp-text) !important;
        border-radius: 14px !important;
    }}
    [data-testid="stExpander"] summary * {{
        color: var(--exp-text) !important;
        fill: var(--exp-text) !important;
    }}

    .streamlit-expanderHeader:hover {{
        background-color: var(--exp-hover) !important;
        border-color: var(--primary-color) !important;
    }}

    .streamlit-expanderHeader p, 
    .streamlit-expanderHeader span, 
    .streamlit-expanderHeader div, 
    .streamlit-expanderHeader svg {{
        color: var(--exp-text) !important;
        fill: var(--exp-text) !important;
        font-weight: 700 !important;
    }}

    .streamlit-expanderContent {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border-radius: 0 0 15px 15px !important;
        border: 1px solid var(--glass-border) !important;
        border-top: none !important;
    }}

    /* Sidebar Elements */
    [data-testid="stSidebar"] {{
        background-color: var(--sec-bg-color) !important;
        border-right: 1px solid var(--glass-border) !important;
    }}
    [data-testid="stSidebar"] .stMarkdown p {{
        color: var(--text-color) !important;
        font-weight: 600 !important;
    }}

    /* Selectboxes and Inputs */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    .stSelectbox div[data-baseweb="select"] {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border-radius: 12px !important;
        border: 1px solid var(--glass-border) !important;
    }}
    div[data-baseweb="input"] input,
    div[data-baseweb="select"] input,
    .stTextInput input,
    .stNumberInput input,
    textarea {{
        color: var(--text-color) !important;
        background: var(--surface-color) !important;
    }}
    div[data-baseweb="input"] input::placeholder,
    .stTextInput input::placeholder,
    .stNumberInput input::placeholder,
    textarea::placeholder {{
        color: var(--muted-text) !important;
        opacity: 1 !important;
    }}
    .stSelectbox label, .stTextInput label, .stTextArea label, .stNumberInput label {{
        color: var(--text-color) !important;
        opacity: 0.95 !important;
        font-weight: 600 !important;
    }}

    /* Selectbox: ochiladigan tugma va pastga qaragan belgi (SVG) — lightda ko‘rinadi */
    [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div > div {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border-color: var(--glass-border) !important;
    }}
    [data-testid="stSelectbox"] div[data-baseweb="select"] svg,
    [data-testid="stSelectbox"] div[data-baseweb="select"] path {{
        fill: var(--text-color) !important;
        color: var(--text-color) !important;
    }}
    div[data-baseweb="select"] svg {{
        fill: var(--text-color) !important;
    }}

    /* Target the dropdown menu itself */
    div[data-baseweb="menu"] {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--glass-border) !important;
    }}
    div[data-baseweb="popover"] {{
        background-color: var(--surface-color) !important;
        border: 1px solid var(--glass-border) !important;
    }}
    ul[role="listbox"] {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 12px !important;
    }}
    li[role="option"] {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
    }}
    li[role="option"][aria-selected="true"] {{
        background-color: color-mix(in srgb, var(--primary-color) 16%, var(--surface-color)) !important;
        color: var(--text-color) !important;
    }}
    li[role="option"]:hover {{
        background-color: var(--sec-bg-color) !important;
        color: var(--text-color) !important;
    }}
    div[role="option"] {{
        color: var(--text-color) !important;
    }}
    div[role="option"]:hover {{
        background-color: var(--sec-bg-color) !important;
    }}

    /* Target Radio Buttons */
    div[data-testid="stRadio"] > div {{
        background-color: transparent !important;
    }}
    div[data-testid="stRadio"] label {{
        color: var(--text-color) !important;
        background-color: var(--surface-color) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 10px !important;
        padding: 8px 15px !important;
        margin-right: 10px !important;
    }}
    div[data-testid="stRadio"] label p,
    div[data-testid="stRadio"] label span,
    div[data-testid="stRadio"] label div {{
        color: var(--text-color) !important;
        opacity: 1 !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) {{
        border-color: var(--primary-color) !important;
        box-shadow: 0 0 0 2px var(--focus-ring) !important;
    }}
    /* Slider yozuvlari (value va min/max) har ikki temada ham ko'rinsin */
    [data-testid="stSlider"] label,
    [data-testid="stSlider"] p,
    [data-testid="stSlider"] span {{
        color: var(--text-color) !important;
        opacity: 1 !important;
    }}

    /* Popover fixes (3-dot menu) */
    [data-testid="stPopover"] > div,
    div[data-baseweb="popover"],
    div[role="dialog"] {{
        background: var(--surface-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--glass-border) !important;
        box-shadow: var(--shadow-strong) !important;
        border-radius: 14px !important;
    }}
    [data-testid="stPopover"] .stMarkdown p,
    [data-testid="stPopover"] .stMarkdown span,
    [data-testid="stPopover"] label,
    [data-testid="stPopover"] div {{
        color: var(--text-color) !important;
    }}
    [data-testid="stPopover"] [data-testid="stVerticalBlock"],
    [data-testid="stPopover"] [data-testid="stMarkdownContainer"],
    [data-testid="stPopover"] [data-testid="stRadio"],
    [data-testid="stPopover"] [data-testid="stRadio"] > div {{
        background: transparent !important;
    }}
    [data-testid="stPopover"] form,
    [data-testid="stPopover"] section,
    [data-testid="stPopover"] [role="radiogroup"] {{
        background: var(--surface-color) !important;
        border-radius: 12px !important;
    }}

    /* Tabs (Media Kiritish: Fayl / Ovoz) — har ikkala rejimda o‘qiladigan matn */
    [data-testid="stTabs"] {{
        background: transparent !important;
    }}
    [data-testid="stTabs"] [role="tablist"],
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        background: transparent !important;
        gap: 0.25rem !important;
        border-bottom: 1px solid var(--glass-border) !important;
    }}
    [data-testid="stTabs"] button[role="tab"] {{
        color: var(--text-color) !important;
        background: transparent !important;
        opacity: 1 !important;
        text-shadow: none !important;
        border-radius: 10px 10px 0 0 !important;
    }}
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
        color: var(--primary-color) !important;
        font-weight: 700 !important;
        border-bottom: 2px solid var(--primary-color) !important;
    }}
    [data-testid="stTabs"] button[role="tab"] p,
    [data-testid="stTabs"] button[role="tab"] span,
    [data-testid="stTabs"] button[role="tab"] div {{
        color: inherit !important;
        opacity: 1 !important;
    }}

    /* File Uploader (Corrected) */
    [data-testid="stFileUploader"] {{
        padding: 0 !important;
        background-color: transparent !important;
    }}
    [data-testid="stFileUploader"] section {{
        background-color: var(--sec-bg-color) !important;
        border: 2px dashed var(--primary-color) !important;
        border-radius: 20px !important;
        padding: 1.5rem !important;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        background-color: var(--bg-color) !important;
        border-radius: 15px !important;
    }}
    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] small {{
        color: var(--text-color) !important;
        font-weight: 500 !important;
    }}
    [data-testid="stFileUploader"] button {{
        background-color: var(--primary-color) !important;
        color: white !important;
        border-radius: 12px !important;
    }}

    /* All Alert Overrides */
    .stAlert {{
        background-color: var(--sec-bg-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 15px !important;
    }}
    .stAlert svg {{ fill: var(--primary-color) !important; }}
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span,
    [data-testid="stAlert"] div,
    [data-testid="stAlert"] .stMarkdown {{
        color: var(--text-color) !important;
        opacity: 1 !important;
    }}
    /* Success xabarlari: yengil yashil fon + asosiy matn rangi */
    [data-testid="stAlert"][kind="success"] {{
        background-color: color-mix(in srgb, var(--success-color) 14%, var(--surface-color)) !important;
        border-color: color-mix(in srgb, var(--success-color) 35%, transparent) !important;
    }}
    [data-testid="stAlert"][kind="success"] p,
    [data-testid="stAlert"][kind="success"] span,
    [data-testid="stAlert"][kind="success"] div {{
        color: var(--text-color) !important;
    }}

    /* ── Main Header ── */
    .main-header {{
        text-align: center;
        padding: 3.5rem 0;
        margin-bottom: 2rem;
        background: radial-gradient(circle at center, {accent_glow} 0%, transparent 70%);
        border-radius: 30px;
    }}
    .main-header h1 {{
        font-size: 4rem !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 35%, #58a6ff 70%, var(--primary-color) 100%);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shine 4s linear infinite;
        letter-spacing: -3px;
        margin: 0 !important;
    }}
    .main-header p {{
        color: var(--text-color) !important;
        opacity: 0.7;
        font-size: 1.3rem;
        margin-top: 0.8rem;
        font-weight: 400;
    }}

    @keyframes shine {{
        to {{ background-position: 200% center; }}
    }}

    /* ── Info Banner (Welcome) ── */
    .info-banner {{
        background: var(--sec-bg-color);
        border: 1px solid var(--glass-border);
        border-radius: 28px;
        padding: 3rem;
        text-align: center;
        margin: 2rem 0;
        box-shadow: var(--shadow-soft);
    }}
    .info-banner h3 {{
        color: var(--primary-color) !important;
        font-weight: 800;
        font-size: 1.8rem !important;
        margin-bottom: 1rem !important;
    }}
    .info-banner p {{
        color: var(--text-color) !important;
        font-size: 1.1rem !important;
        opacity: 0.8;
    }}

    /* ── Premium Cards ── */
    .result-card {{
        background: var(--sec-bg-color);
        border: 1px solid var(--glass-border);
        border-radius: 24px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        transition: all 0.4s ease;
        box-shadow: var(--shadow-soft);
    }}
    .result-card:hover {{
        border-color: var(--primary-color);
        transform: translateY(-8px);
        box-shadow: var(--shadow-strong);
    }}

    /* ── Badges ── */
    .score-badge {{
        padding: 0.5rem 1.2rem;
        border-radius: 50px;
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
    }}
    .score-high {{ background: color-mix(in srgb, var(--success-color) 16%, transparent); color: var(--success-color); border: 1px solid color-mix(in srgb, var(--success-color) 30%, transparent); }}
    .score-mid  {{ background: color-mix(in srgb, var(--warning-color) 16%, transparent); color: var(--warning-color); border: 1px solid color-mix(in srgb, var(--warning-color) 30%, transparent); }}
    .score-low  {{ background: color-mix(in srgb, var(--danger-color) 16%, transparent); color: var(--danger-color); border: 1px solid color-mix(in srgb, var(--danger-color) 30%, transparent); }}

    .time-badge {{
        background: color-mix(in srgb, var(--primary-color) 16%, transparent);
        color: var(--primary-color);
        border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
        border-radius: 12px;
        padding: 0.4rem 0.8rem;
        font-weight: 800;
        font-size: 0.85rem;
    }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{
        border-right: 1px solid var(--glass-border);
        background-color: var(--sec-bg-color) !important;
    }}

    [data-testid="stSidebar"] .stMarkdown p {{
        font-weight: 600;
        color: var(--text-color) !important;
    }}

    /* Buttons (Premium Glow) */
    .stButton > button {{
        border-radius: 18px !important;
        background: var(--brand-gradient) !important;
        color: var(--button-text) !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        padding: 0.7rem 2rem !important;
        border: none !important;
        transition: all 0.4s ease !important;
        box-shadow: var(--shadow-soft) !important;
        width: 100%;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        background: var(--brand-gradient) !important;
        color: var(--button-text) !important;
        border: 1px solid var(--glass-border) !important;
    }}
    /* Tema tugmalari: har o'lchamda ixcham va yonma-yon */
    [data-testid="stSidebar"] .st-key-theme_dark_btn button,
    [data-testid="stSidebar"] .st-key-theme_light_btn button {{
        width: 2.75rem !important;
        min-width: 2.75rem !important;
        height: 2.75rem !important;
        min-height: 2.75rem !important;
        padding: 0 !important;
        border-radius: 0.75rem !important;
        font-size: 1.02rem !important;
        line-height: 1 !important;
    }}
    /* Sidebar pastidagi mini tema tugmalari */
    [data-testid="stSidebar"] .st-key-theme_dark_bottom_btn,
    [data-testid="stSidebar"] .st-key-theme_light_bottom_btn {{
        margin-top: 0 !important;
    }}
    [data-testid="stSidebar"] .st-key-theme_dark_bottom_btn .stButton > button,
    [data-testid="stSidebar"] .st-key-theme_light_bottom_btn .stButton > button {{
        width: 2rem !important;
        min-width: 2rem !important;
        height: 2rem !important;
        min-height: 2rem !important;
        padding: 0 !important;
        border-radius: 0.62rem !important;
        font-size: 0.88rem !important;
        line-height: 1 !important;
    }}
    /* Sidebar'dagi tema switch (fixed gap, responsive bo'lsa ham uzoqlashmaydi) */
    .theme-toggle-row {{
        display: flex !important;
        align-items: center !important;
        gap: 0.7rem !important;
        margin: 0.15rem 0 0.35rem 0 !important;
    }}
    .theme-toggle-btn {{
        width: 2.8rem !important;
        height: 2.8rem !important;
        border-radius: 0.9rem !important;
        border: 1px solid var(--glass-border) !important;
        background: var(--surface-color) !important;
        color: var(--text-color) !important;
        text-decoration: none !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 1.1rem !important;
        line-height: 1 !important;
        transition: all 0.2s ease !important;
    }}
    .theme-toggle-btn:hover {{
        border-color: var(--primary-color) !important;
        transform: translateY(-1px) !important;
    }}
    .theme-toggle-btn.active {{
        background: var(--brand-gradient) !important;
        color: var(--button-text) !important;
        border-color: color-mix(in srgb, var(--primary-color) 55%, var(--glass-border)) !important;
    }}

    /* Streamlit default secondary tugmalar (masalan Cache) — qora qolib ketmasin */
    [data-testid="stBaseButton-secondary"] {{
        background-color: var(--surface-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--glass-border) !important;
        box-shadow: none !important;
    }}
    [data-testid="stBaseButton-secondary"]:hover {{
        background-color: var(--sec-bg-color) !important;
        border-color: var(--primary-color) !important;
    }}
    [data-testid="stBaseButton-primary"] {{
        background: var(--brand-gradient) !important;
        color: var(--button-text) !important;
    }}

    /* Ovoz yozish (st.audio_input) — fon va yozuvlar theme bo‘yicha */
    [data-testid="stAudioInput"] > div:nth-child(2),
    .stAudioInput > div:nth-child(2) {{
        background-color: var(--surface-color) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 12px !important;
    }}
    [data-testid="stAudioInput"] [data-testid="stWidgetLabel"] p,
    [data-testid="stAudioInput"] [data-testid="stWidgetLabel"] label,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] label {{
        color: var(--text-color) !important;
        opacity: 1 !important;
    }}
    [data-testid="stAudioInput"] [data-testid="stAudioInputWaveformTimeCode"] {{
        color: var(--text-color) !important;
        background-color: transparent !important;
    }}
    [data-testid="stAudioInput"] button[data-testid="stAudioInputActionButton"] {{
        color: var(--primary-color) !important;
    }}

    .stButton > button:hover {{
        transform: translateY(-5px) !important;
        box-shadow: var(--shadow-strong) !important;
        filter: brightness(1.04);
    }}

    /* ── Animated Search Bar ── */
    .stTextInput input {{
        border-radius: 18px !important;
        border: 1px solid var(--glass-border) !important;
        background: var(--bg-color) !important;
        color: var(--text-color) !important;
        padding: 0.8rem 1.2rem !important;
    }}

    .stTextInput input:focus {{
        border-color: var(--primary-color) !important;
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
    }}

    /* --- Stats --- */
    .stat-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.8rem;
        margin-top: 1rem;
    }}
    .stat-item {{
        background: var(--sec-bg-color);
        border: 1px solid var(--glass-border);
        border-radius: 15px;
        padding: 0.8rem;
        text-align: center;
    }}
    .stat-value {{ font-size: 1.2rem; font-weight: 800; color: var(--primary-color); }}
    .stat-label {{ font-size: 0.7rem; color: var(--text-color); opacity: 0.6; text-transform: uppercase; margin-top: 0.2rem; }}

    
/* —— Universal responsive (telefon / planshet / kompyuter) —— */
.block-container {{
    max-width: min(1200px, 100%) !important;
    padding-left: clamp(0.75rem, 3vw, 2rem) !important;
    padding-right: clamp(0.75rem, 3vw, 2rem) !important;
}}
@media (max-width: 640px) {{
    .main-header {{ padding: 1.25rem 0.5rem !important; margin-bottom: 1rem !important; border-radius: 18px !important; }}
    .main-header h1 {{
        font-size: 1.75rem !important;
        letter-spacing: -0.5px !important;
        background-size: 220% auto !important;
        animation: shine 5.5s linear infinite !important;
    }}
    .main-header p {{ font-size: 0.95rem !important; }}
    .info-banner {{ padding: 1.25rem 1rem !important; margin: 1rem 0 !important; border-radius: 18px !important; }}
    .info-banner h3 {{ font-size: 1.25rem !important; }}
    .result-card {{ padding: 1rem !important; border-radius: 16px !important; }}
    .result-card:hover {{ transform: none !important; }}
    .stButton > button {{ font-size: 0.92rem !important; padding: 0.5rem 1rem !important; }}
    div[data-testid="stHorizontalBlock"] {{ flex-direction: column !important; flex-wrap: wrap !important; gap: 0.75rem !important; }}
    div[data-testid="column"] {{ width: 100% !important; min-width: 0 !important; flex: 1 1 auto !important; }}
    /* Sidebar ichida columns mobilga tushganda ham yonma-yon qolsin */
    [data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {{
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 0.45rem !important;
        align-items: center !important;
    }}
    [data-testid="stSidebar"] div[data-testid="column"] {{
        width: auto !important;
        min-width: 0 !important;
        flex: 0 0 auto !important;
    }}
    [data-testid="stSidebar"] .st-key-theme_dark_bottom_btn .stButton > button,
    [data-testid="stSidebar"] .st-key-theme_light_bottom_btn .stButton > button {{
        width: 1.9rem !important;
        min-width: 1.9rem !important;
        height: 1.9rem !important;
        min-height: 1.9rem !important;
        font-size: 0.84rem !important;
    }}
    div[data-testid="stRadio"] > div {{ flex-wrap: wrap !important; }}
    .stat-grid {{ grid-template-columns: 1fr !important; }}
}}
@media (min-width: 641px) and (max-width: 1024px) {{
    .main-header h1 {{ font-size: 2.5rem !important; }}
    .main-header {{ padding: 2.25rem 1rem !important; }}
    div[data-testid="stHorizontalBlock"] {{ gap: 1rem !important; }}
}}
@media (min-width: 1025px) {{
    .main-header h1 {{ font-size: 3.35rem !important; }}
}}

</style>
    """
    st.markdown(css, unsafe_allow_html=True)
