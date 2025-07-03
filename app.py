import ee
import streamlit as st
from datetime import datetime, date, timedelta
import folium
from streamlit_folium import st_folium
from folium import Element
import uuid

# Earth Engine 初期化
# secrets からサービスアカウント情報を取得
key_dict = {
    "type": "service_account",
    "client_email": st.secrets["GEE_EMAIL"],
    "private_key": st.secrets["GEE_KEY"],
    ...
}
credentials = ee.ServiceAccountCredentials(
    st.secrets["GEE_EMAIL"],
    key_data=key_dict
)
ee.Initialize(credentials)

# 地理範囲（秋田県）
akita = ee.Geometry.Rectangle([138.8, 38.92, 141.18, 41.1])
center = akita.centroid().coordinates().getInfo()

# 全画面レイアウト
st.set_page_config(layout="wide")

# サイドバー UI
st.sidebar.title("期間設定")
ref_date = st.sidebar.date_input("基準日（この日を含む過去3週間）", value=date(2025, 7, 3))
start_date = ref_date - timedelta(days=20)
end_date = ref_date
st.sidebar.markdown(f"**対象期間**: {start_date} ～ {end_date}")

# NDVI画像取得処理
collection = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(akita)
    .filterDate(str(start_date), str(end_date))
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))
)

count = collection.size().getInfo()
st.sidebar.markdown(f"**対象画像枚数**: {count}")

if count == 0:
    st.sidebar.warning("この期間には雲が少ない画像が見つかりませんでした。")
    st.stop()

# 合成画像に使った日付一覧
dates = collection.aggregate_array('system:time_start').getInfo()
date_list = [datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d') for ts in dates]
st.sidebar.markdown("**合成に使われた画像の日付**:")
st.sidebar.write(date_list)

# NDVIモザイク作成
ndvi_collection = (
    collection
    .sort('system:time_start', False)
    .map(lambda img: img.normalizedDifference(['B8', 'B4']).rename('NDVI'))
)
ndvi_image = ndvi_collection.mosaic().clip(akita)

# 地図作成
vis = {'min': 0.1, 'max': 0.7, 'palette': ['white', 'yellow', 'green']}
map_id_dict = ndvi_image.getMapId(vis)

m = folium.Map(location=[center[1], center[0]], zoom_start=12)
layer_id = f'NDVI_{ref_date}_{uuid.uuid4()}'
folium.TileLayer(
    tiles=map_id_dict['tile_fetcher'].url_format,
    attr='Google Earth Engine',
    name=layer_id,
    overlay=True,
    control=True
).add_to(m)
folium.LayerControl().add_to(m)

# 凡例（HTML直埋め）
legend_html = """
<div style="
    position: fixed;
    top: 10px;
    right: 10px;
    z-index:9999;
    background-color: white;
    padding: 10px;
    border: 2px solid grey;
    border-radius: 5px;
    font-size: 14px;
    line-height: 18px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
">
    <b>NDVI 凡例</b><br>
    <i style="background:white; width: 12px; height: 12px; float:left; margin-right:5px;"></i>
    0.1 以下：植生なしまたは非常に少ない<br>
    <i style="background:yellow; width: 12px; height: 12px; float:left; margin-right:5px;"></i>
    ～ 0.4：中程度の植生<br>
    <i style="background:green; width: 12px; height: 12px; float:left; margin-right:5px;"></i>
    ～ 0.7：植生が豊富（高密度）<br>
</div>
"""
m.get_root().html.add_child(Element(legend_html))

# メイン画面タイトル
st.title("NDVI (Normalized Difference Vegetation Index)")

# 折りたたみ形式の解説
with st.expander("NDVIについての解説"):
    st.markdown("""
### 🌱 NDVI（正規化植生指数）とは？

NDVI（Normalized Difference Vegetation Index）は、人工衛星によるリモートセンシングを用いて地表の植生の密度や健康度を測る指標です。

- 値の範囲は **-1.0〜+1.0**
- 高い値（0.6〜0.8）：森林などの**豊かな植生**
- 中程度（0.2〜0.5）：草地や耕作地
- 低い値（0.1以下）：裸地、都市、水域など

---

### 📡 データの取得元と処理方法

このアプリでは、**Google Earth Engine（GEE）** を利用し、**Sentinel-2衛星の表面反射データ（S2_SR_HARMONIZED）** を取得しています。  
指定された期間内の雲の少ない画像を対象に、各画像からNDVIを算出し、**モザイク合成**して全体を1枚にまとめて表示しています。

---

### 🧮 NDVIの算出式""")

    st.latex(r"NDVI = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}")

    st.markdown("""
- **NIR**（近赤外）：Sentinel-2のバンド8（B8）
- **Red**（赤色）：Sentinel-2のバンド4（B4）

---

### ⚠️ NDVI画像が表示されない場合

次のようなケースではNDVIが表示されません：

- 指定期間に観測データが存在しない
- 雲の影響で利用可能な画像がない
- Google Earth Engine 側のAPI制限や不具合

その場合は、**期間を変更**するか、**雲の許容率を変更**して試してください。
""")

# 地図表示
st_folium(m, width=1000, height=600, returned_objects=[], key=f"map_{uuid.uuid4()}")
