import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlencode
import datetime
import os
import json
from dotenv import load_dotenv

st.set_page_config(page_title="請求書作成効率化", page_icon="🚀")
st.title("🚀 請求書作成効率化")

st.markdown("""
<style>
h1, h2, h3 { color: #1A56DB; }
div.stButton > button[kind="primary"] {
    background-color: #1A56DB;
    border-color: #1A56DB;
    color: white;
    font-size: 1rem;
    padding: 0.6rem 2rem;
    border-radius: 8px;
    width: 100%;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #1648C0;
    border-color: #1648C0;
}
section[data-testid="stSidebar"] { background-color: #F0F4FF; }
div[data-testid="stSuccess"] { border-left-color: #1A56DB; }
</style>
""", unsafe_allow_html=True)

# --- freee API 設定 ---
AUTH_URL = "https://accounts.secure.freee.co.jp/public_api/authorize"
TOKEN_URL = "https://accounts.secure.freee.co.jp/public_api/token"
API_BASE = "https://api.freee.co.jp/api/1"
API_BASE_IV = "https://api.freee.co.jp/iv"
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8501")
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".freee_invoice_token.json")

# --- .envから認証情報を読み込む ---
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
CLIENT_ID = st.secrets.get("CLIENT_ID", "") or os.getenv("CLIENT_ID", "")
CLIENT_SECRET = st.secrets.get("CLIENT_SECRET", "") or os.getenv("CLIENT_SECRET", "")
# --- 会社設定 ---
COMPANY_CONFIG = {
    "フリー株式会社": {
        "content_col": "【内容】",
        "qty_col": "【数量】",
        "price_col": "【単価】",
        "unit": "件",
        "tax_entry_method": "out",
        "withholding_tax_entry_method": "out",
        "tax_fraction": "round",
    },
    "ipartners株式会社": {
        "content_col": "【内容】",
        "qty_col": "【数量】",
        "price_col": "【単価】",
        "unit": "時間",
        "tax_entry_method": "in",
        "withholding_tax_entry_method": "in",
        "tax_fraction": "omit",
    },
}

# --- トークン保存・読み込み ---
def save_tokens(access_token, refresh_token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return {}

def refresh_access_token(refresh_token):
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    })
    if resp.ok:
        data = resp.json()
        save_tokens(data["access_token"], data["refresh_token"])
        return data["access_token"]
    return None

# --- サイドバー ---
with st.sidebar:
    st.header("freee 設定")
    if st.button("ログアウト"):
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- 認証フロー ---
if "access_token" not in st.session_state:
    # 1. OAuthコールバック処理
    params = st.query_params
    if "code" in params:
        if not CLIENT_ID or not CLIENT_SECRET:
            st.error(".envファイルにCLIENT_IDとCLIENT_SECRETを設定してください")
            st.stop()
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": params["code"],
            "redirect_uri": REDIRECT_URI,
        })
        if resp.ok:
            data = resp.json()
            save_tokens(data["access_token"], data["refresh_token"])
            st.session_state.access_token = data["access_token"]
            st.query_params.clear()
            st.rerun()
        else:
            st.error(f"認証エラー: {resp.text}")
            st.stop()

    # 2. 保存済みトークンで自動ログイン
    tokens = load_tokens()
    if tokens.get("refresh_token"):
        access_token = refresh_access_token(tokens["refresh_token"])
        if access_token:
            st.session_state.access_token = access_token
            st.rerun()

    # 3. 初回ログイン
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error(".envファイルにCLIENT_IDとCLIENT_SECRETを設定してください")
        st.stop()

    st.info("初回ログインが必要です")
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "prompt": "select_company",
    }
    auth_link = f"{AUTH_URL}?{urlencode(auth_params)}"
    st.markdown(
        f'<a href="{auth_link}" target="_self" style="display:inline-block;padding:0.5rem 1.5rem;background-color:#1A56DB;color:white;border-radius:8px;text-decoration:none;font-size:1rem;">🔑 freeeにログイン</a>',
        unsafe_allow_html=True
    )
    st.stop()

# --- 認証済み: メイン画面 ---
token = st.session_state.access_token
headers = {"Authorization": f"Bearer {token}"}


@st.cache_data
def get_companies(_token):
    resp = requests.get(f"{API_BASE}/companies", headers={"Authorization": f"Bearer {_token}"})
    return resp.json().get("companies", [])


@st.cache_data
def get_partners(_token, _company_id):
    resp = requests.get(
        f"{API_BASE}/partners",
        headers={"Authorization": f"Bearer {_token}"},
        params={"company_id": _company_id},
    )
    return resp.json().get("partners", [])


companies = get_companies(token)
if not companies:
    st.error("freeeの会社情報が取得できませんでした。")
    st.stop()

company = companies[0]
company_id = company["id"]
st.success(f"ログイン中: {company['display_name']}")

# --- 会社選択 ---
st.header("会社を選択")
selected_company = st.selectbox("請求書を作成する会社を選んでください", list(COMPANY_CONFIG.keys()))
config = COMPANY_CONFIG[selected_company]

# --- Step 1: Excel読み込み ---
st.header("Step 1｜Excelファイルを読み込む")
uploaded_file = st.file_uploader("ファイルを選択してください（Excel / CSV）", type=["xlsx", "xls", "csv"])

if not uploaded_file:
    st.stop()

if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
else:
    xl = pd.ExcelFile(uploaded_file)
    sheet_name = st.selectbox("シートを選択", xl.sheet_names)
    df = xl.parse(sheet_name)
df.columns = df.columns.str.strip()
st.write("読み込んだデータ:")
st.dataframe(df)

content_col = config["content_col"]
qty_col = config["qty_col"]
price_col = config["price_col"]

missing_cols = [c for c in [content_col, qty_col, price_col] if c not in df.columns]
if missing_cols:
    st.error(f"必要な列が見つかりません: {missing_cols}")
    st.stop()

# --- Step 2: 請求書設定 ---
st.header("Step 2｜請求書の設定")

partners = get_partners(token, company_id)
if not partners:
    st.error("freeeの取引先が取得できませんでした。")
    st.stop()

partner_names = [p["name"] for p in partners]
default_idx = partner_names.index(selected_company) if selected_company in partner_names else 0
selected_partner_name = st.selectbox("請求先（取引先）", partner_names, index=default_idx)
selected_partner = next(p for p in partners if p["name"] == selected_partner_name)

_today = datetime.date.today()
_default_issue = _today.replace(day=1) - datetime.timedelta(days=1)
_next_month = (_today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
_default_due = _next_month - datetime.timedelta(days=1)
col1, col2 = st.columns(2)
with col1:
    issue_date = st.date_input("請求日", _default_issue)
with col2:
    due_date = st.date_input("支払期日", _default_due)

# --- Step 3: プレビュー ---
st.header("Step 3｜内容を確認して請求書を作成")

def _round_tax(val, method):
    import math
    if method == "omit": return math.floor(val)
    if method == "round_up": return math.ceil(val)
    return round(val)

_subtotal = sum(
    int(pd.to_numeric(_row[price_col], errors="coerce") or 0) *
    float(pd.to_numeric(_row[qty_col], errors="coerce") or 0)
    for _, _row in df.iterrows()
)
if config["tax_entry_method"] == "in":
    _net = _round_tax(_subtotal * 100 / 110, config["tax_fraction"])
    _tax = _round_tax(_subtotal * 10 / 110, config["tax_fraction"])
    total = _net + _tax
else:
    total = _subtotal + _round_tax(_subtotal * 0.1, config["tax_fraction"])
st.write(f"**会社:** {selected_company}")
st.write(f"**請求先:** {selected_partner_name}")
st.write(f"**請求日:** {issue_date}")
st.write(f"**支払期日:** {due_date}")
st.metric("合計金額", f"¥{total:,.0f}")
st.dataframe(df[[content_col, qty_col, price_col]])

if st.button("✅ freeeに請求書を作成する", type="primary"):
    lines = []
    for _, row in df.iterrows():
        desc_val = str(row[content_col])
        price_val = float(pd.to_numeric(row[price_col], errors="coerce") or 0)
        qty_val = float(pd.to_numeric(row[qty_col], errors="coerce") or 0)
        line = {
            "type": "item",
            "description": desc_val,
            "quantity": qty_val,
            "unit_price": str(int(price_val)),
            "tax_rate": 10,
        }
        if config["unit"]:
            line["unit"] = config["unit"]
        lines.append(line)

    payload = {
        "company_id": company_id,
        "billing_date": str(issue_date),
        "payment_date": str(due_date),
        "partner_id": selected_partner["id"],
        "partner_title": "御中",
        "tax_entry_method": config["tax_entry_method"],
        "tax_fraction": config["tax_fraction"],
        "withholding_tax_entry_method": config["withholding_tax_entry_method"],
        "lines": lines,
    }

    resp = requests.post(
        f"{API_BASE_IV}/invoices",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
    )

    if resp.ok:
        invoice = resp.json().get("invoice", {})
        st.success(f"請求書を作成しました！請求書番号: {invoice.get('invoice_number', '(番号なし)')}")
        st.balloons()
    else:
        st.error(f"エラーが発生しました: {resp.text}")
