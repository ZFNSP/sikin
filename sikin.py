import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(page_title="Macro Regime Monitor", layout="wide")
st.title("マクロ先行指標 監視ダッシュボード (Quant Mode)")

@st.cache_data(ttl=3600)
def fetch_macro_data():
    end_date = datetime.today()
    # ボラティリティ計算用に長め（120日）にデータを取得
    start_date = end_date - timedelta(days=120)
    
    # 取得ティッカーの定義
    tickers = {
        "TNX": "^TNX",  # 10年債利回り
        "TIP": "TIP",   # 物価連動債
        "IEF": "IEF",   # 7-10年国債
        "WTI": "CL=F",  # 原油
        "VIX": "^VIX"   # S&P500恐怖指数
    }
    
    df = pd.DataFrame()
    
    try:
        # 1つずつ独立して確実に取得する（エラー耐性の強化）
        for name, ticker in tickers.items():
            tkr = yf.Ticker(ticker)
            hist = tkr.history(start=start_date, end=end_date)
            if not hist.empty:
                df[name] = hist['Close']
            else:
                st.warning(f"⚠️ {name} ({ticker}) のデータがAPIから返されませんでした。")
                
        if df.empty:
            return pd.DataFrame()

        # タイムゾーン情報の削除と欠損値の前方補完
        df.index = df.index.tz_localize(None)
        df = df.ffill()

        # --- クオンツ指標の独自計算エンジン ---
        # 1. MOVEプロキシ (10年債利回りのヒストリカル・ボラティリティ)
        tnx_log_ret = np.log(df['TNX'] / df['TNX'].shift(1))
        df['MOVE_Proxy'] = tnx_log_ret.rolling(window=20).std() * np.sqrt(252) * 100
        
        # 2. 期待インフレ率プロキシ (TIP/IEFレシオ)
        df['BEI_Proxy'] = df['TIP'] / df['IEF']
        
        # 3. VIXとその加速度（2階微分）の計算
        df['VIX_Velocity'] = df['VIX'] - df['VIX'].shift(3) # 速度 (3日差分)
        df['VIX_Acceleration'] = df['VIX_Velocity'] - df['VIX_Velocity'].shift(3) # 加速度
        
        # NaNを落とし、直近90日分を返す
        return df.dropna().tail(90)
        
    except Exception as e:
        st.error(f"データ計算エンジン内部で致命的エラーが発生しました: {e}")
        return pd.DataFrame()

def analyze_trend(series, short_window=5, long_window=20):
    """数日〜数週間のトレンドを判定するロジック"""
    current_val = series.iloc[-1]
    prev_val = series.iloc[-2]
    ma_short = series.rolling(window=short_window).mean().iloc[-1]
    ma_long = series.rolling(window=long_window).mean().iloc[-1]
    
    delta = current_val - prev_val
    is_downtrend = (current_val < ma_short) and (ma_short < ma_long)
    return float(current_val), float(delta), is_downtrend

# データ取得の実行
with st.spinner('マクロデータを取得・計算中...'):
    data = fetch_macro_data()

if not data.empty:
    move_val, move_delta, move_safe = analyze_trend(data['MOVE_Proxy'])
    bei_val, bei_delta, bei_safe = analyze_trend(data['BEI_Proxy'])
    wti_val, wti_delta, wti_safe = analyze_trend(data['WTI'])
    
    # --- VIX加速度判定ロジック ---
    vix_val = data['VIX'].iloc[-1]
    vix_vel = data['VIX_Velocity'].iloc[-1]
    vix_accel = data['VIX_Acceleration'].iloc[-1]
    
    if vix_accel < 0 and vix_vel < 0:
        vix_status = "🟢 緑 (ボラティリティ完全減衰・打診買い許可)"
    elif vix_accel > 0 and vix_vel < 0:
        vix_status = "🟡 薄い赤 (ボラティリティ残存・待機)"
    else:
        vix_status = "🔴 赤 (ショック進行中・完全静観)"
    
    # --- 全体レジーム判定 ---
    if move_safe and bei_safe and ("🟢" in vix_status):
        regime_status = "🟢 RISK ON (純粋α銘柄へのエントリー環境)"
    elif not move_safe and not bei_safe:
        regime_status = "🔴 RISK OFF (全ポジションの縮小・ヘッジ環境)"
    else:
        regime_status = "🟡 NEUTRAL (トレンド転換の待機・相対的強度の監視環境)"

    st.subheader(f"現在のマクロレジーム: {regime_status}")
    st.markdown(f"**VIX 加速度シグナル:** {vix_status}")
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(label="MOVEプロキシ (債券VIX)", value=f"{move_val:.2f}", delta=f"{move_delta:.2f}", delta_color="inverse")
        st.line_chart(data['MOVE_Proxy'].tail(30))

    with col2:
        st.metric(label="インフレ期待 (TIP/IEF)", value=f"{bei_val:.4f}", delta=f"{bei_delta:.4f}", delta_color="inverse")
        st.line_chart(data['BEI_Proxy'].tail(30))

    with col3:
        st.metric(label="WTI原油先物 ($)", value=f"{wti_val:.2f}", delta=f"{wti_delta:.2f}", delta_color="inverse")
        st.line_chart(data['WTI'].tail(30))
        
    with col4:
        st.metric(label="VIX (S&P500恐怖指数)", value=f"{float(vix_val):.2f}", delta=f"{float(vix_vel):.2f} (速度)", delta_color="inverse")
        st.line_chart(data['VIX'].tail(30))

else:
    st.error("データの取得に失敗しました。ネットワーク接続と yfinance のバージョンを確認してください。")
