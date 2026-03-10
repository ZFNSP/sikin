import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(page_title="Macro Regime Monitor", layout="wide")
st.title("マクロ先行指標 監視ダッシュボード")

@st.cache_data(ttl=3600)
def fetch_macro_data():
    end_date = datetime.today()
    start_date = end_date - timedelta(days=90)
    
    # 1. MOVE指数（債券ボラティリティ）
    move_df = yf.download("^MOVE", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(move_df, pd.DataFrame):
        move_df = move_df.squeeze()
    move_df.index = move_df.index.tz_localize(None)
    
    # 2. 期待インフレ率プロキシ (TIP/IEFレシオ)
    # FREDのBEIの代わりに、インフレ連動債(TIP)と通常国債(IEF)の相対強度でインフレ期待を測定
    tip_df = yf.download("TIP", start=start_date, end=end_date, progress=False)['Close']
    ief_df = yf.download("IEF", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(tip_df, pd.DataFrame): tip_df = tip_df.squeeze()
    if isinstance(ief_df, pd.DataFrame): ief_df = ief_df.squeeze()
    
    tip_df.index = tip_df.index.tz_localize(None)
    ief_df.index = ief_df.index.tz_localize(None)
    
    # レシオの計算（この数値が上がればインフレ懸念増、下がればインフレ懸念後退）
    bei_proxy = tip_df / ief_df
    
    # 3. WTI原油先物（期近）
    wti_df = yf.download("CL=F", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(wti_df, pd.DataFrame):
        wti_df = wti_df.squeeze()
    wti_df.index = wti_df.index.tz_localize(None)
    
    # データフレームの結合と整形
    df = pd.concat([move_df, bei_proxy, wti_df], axis=1)
    df.columns = ['MOVE', 'BEI_Proxy', 'WTI']
    
    df = df.loc[start_date:end_date]
    df = df.ffill().dropna()
    
    return df

def analyze_trend(series, short_window=5, long_window=20):
    """数日〜数週間のトレンドを判定するロジック"""
    current_val = series.iloc[-1]
    prev_val = series.iloc[-2]
    ma_short = series.rolling(window=short_window).mean().iloc[-1]
    ma_long = series.rolling(window=long_window).mean().iloc[-1]
    
    delta = current_val - prev_val
    is_downtrend = (current_val < ma_short) and (ma_short < ma_long)
    
    return current_val, delta, is_downtrend

# データ取得
with st.spinner('マクロデータを取得中...'):
    data = fetch_macro_data()

if not data.empty:
    move_val, move_delta, move_safe = analyze_trend(data['MOVE'])
    bei_val, bei_delta, bei_safe = analyze_trend(data['BEI_Proxy'])
    wti_val, wti_delta, wti_safe = analyze_trend(data['WTI'])
    
    # --- レジーム（環境）判定ロジック ---
    if move_safe and bei_safe:
        regime_status = "🟢 RISK ON (株式市場への資金流入環境)"
        regime_color = "normal"
    elif not move_safe and not bei_safe:
        regime_status = "🔴 RISK OFF (ポジション縮小・警戒環境)"
        regime_color = "inverse"
    else:
        regime_status = "🟡 NEUTRAL (トレンド転換の待機・個別銘柄選別環境)"
        regime_color = "off"

    st.subheader(f"現在のマクロレジーム: {regime_status}")
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="MOVE指数 (債券VIX)", 
            value=f"{move_val:.2f}", 
            delta=f"{move_delta:.2f}",
            delta_color="inverse"
        )
        st.caption("※低下トレンドであれば株式のバリュエーションは正当化されます")
        st.line_chart(data['MOVE'].tail(30))

    with col2:
        st.metric(
            label="インフレ期待プロキシ (TIP/IEFレシオ)", 
            value=f"{bei_val:.4f}", 
            delta=f"{bei_delta:.4f}",
            delta_color="inverse"
        )
        st.caption("※低下トレンドであれば利上げ圧力は後退します")
        st.line_chart(data['BEI_Proxy'].tail(30))

    with col3:
        st.metric(
            label="WTI原油先物 (期近) $", 
            value=f"{wti_val:.2f}", 
            delta=f"{wti_delta:.2f}",
            delta_color="inverse"
        )
        st.caption("※急騰リスクが剥落しているかを確認します")
        st.line_chart(data['WTI'].tail(30))

else:
    st.error("データの取得に失敗しました。")
