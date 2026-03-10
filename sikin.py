import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(page_title="Macro Regime Monitor", layout="wide")
st.title("マクロ先行指標 監視ダッシュボード")

@st.cache_data(ttl=3600) # 1時間ごとにキャッシュをクリア
def fetch_macro_data():
    end_date = datetime.today()
    start_date = end_date - timedelta(days=90) # トレンド判定のため過去90日分を取得
    
    # 1. MOVE指数（債券ボラティリティ）の取得
    move_df = yf.download("^MOVE", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(move_df, pd.DataFrame):
        move_df = move_df.squeeze()
    move_df.index = move_df.index.tz_localize(None) # タイムゾーンの除去
    
    # 2. BEI（10年ブレークイーブン・インフレ率）の取得 (スクレイピング対策を突破)
    bei_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE"
    # 一般的なWebブラウザからのアクセスを装うヘッダー
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    response = requests.get(bei_url, headers=headers)
    
    # 取得したテキストデータをPandasに読み込ませる
    bei_df = pd.read_csv(io.StringIO(response.text), parse_dates=['DATE'], index_col='DATE', na_values='.')
    bei_series = bei_df['T10YIE'].astype(float)
    bei_series.index = bei_series.index.tz_localize(None)
    
    # 3. WTI原油先物（期近）の取得
    wti_df = yf.download("CL=F", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(wti_df, pd.DataFrame):
        wti_df = wti_df.squeeze()
    wti_df.index = wti_df.index.tz_localize(None)
    
    # データフレームの結合と整形
    df = pd.concat([move_df, bei_series, wti_df], axis=1)
    df.columns = ['MOVE', 'BEI', 'WTI']
    
    # 指定期間でフィルタリングして欠損値を前方穴埋め
    df = df.loc[start_date:end_date]
    df = df.ffill().dropna()
    
    return df

def analyze_trend(series, short_window=5, long_window=20):
    """数日〜数週間のトレンドを判定するロジック"""
    current_val = series.iloc[-1]
    prev_val = series.iloc[-2]
    ma_short = series.rolling(window=short_window).mean().iloc[-1]
    ma_long = series.rolling(window=long_window).mean().iloc[-1]
    
    # モメンタム（前日比）とトレンド（短期MAと長期MAの位置関係）
    delta = current_val - prev_val
    is_downtrend = (current_val < ma_short) and (ma_short < ma_long)
    
    return current_val, delta, is_downtrend

# データ取得
with st.spinner('マクロデータを取得中...'):
    data = fetch_macro_data()

if not data.empty:
    # 各指標の分析
    move_val, move_delta, move_safe = analyze_trend(data['MOVE'])
    bei_val, bei_delta, bei_safe = analyze_trend(data['BEI'])
    wti_val, wti_delta, wti_safe = analyze_trend(data['WTI'])
    
    # --- レジーム（環境）判定ロジック ---
    # MOVEとBEIが共に下落トレンド（安全圏）にあれば、株式への資金流入（リスクオン）と判定
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
    
    # メトリクスの表示
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="MOVE指数 (債券VIX)", 
            value=f"{move_val:.2f}", 
            delta=f"{move_delta:.2f}",
            delta_color="inverse" # MOVEは下がる方が良いため色を反転
        )
        st.caption("※低下トレンドであれば株式のバリュエーションは正当化されます")
        st.line_chart(data['MOVE'].tail(30))

    with col2:
        st.metric(
            label="BEI (10年期待インフレ率) %", 
            value=f"{bei_val:.2f}", 
            delta=f"{bei_delta:.2f}",
            delta_color="inverse"
        )
        st.caption("※低下トレンドであれば利上げ圧力は後退します")
        st.line_chart(data['BEI'].tail(30))

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
    st.error("データの取得に失敗しました。APIの接続状況を確認してください。")
