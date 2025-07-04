import ee
import streamlit as st
from datetime import datetime, date, timedelta
import folium
from streamlit_folium import st_folium
from folium import Element
import uuid
import json

# Earth Engine 初期化
# secrets からサービスアカウント情報を取得
key_dict = {
    "type": "service_account",
    "client_email": st.secrets["GEE_EMAIL"],
    "private_key": st.secrets["GEE_PRIVATE_KEY"],
    "token_uri": "https://oauth2.googleapis.com/token"
}

# key_dict を JSON 文字列に変換して渡す
credentials = ee.ServiceAccountCredentials(
    st.secrets["GEE_EMAIL"],
    key_data=json.dumps(key_dict)
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

# 雲の許容率（ユーザー指定）
cloud_threshold = st.sidebar.slider("雲の許容率（%）", min_value=0, max_value=100, value=40)

# 表示する画像タイプ選択
band_option = st.sidebar.selectbox(
    "表示する画像タイプ",
    options=["NDVI", "RGB", "B4（赤）", "B8（近赤外）"],
    index=0
)

# 画像取得
collection = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(akita)
    .filterDate(str(start_date), str(end_date))
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_threshold))
)

count = collection.size().getInfo()
st.sidebar.markdown(f"**対象画像枚数**: {count}")

if count == 0:
    st.sidebar.warning("この期間には雲が少ない画像が見つかりませんでした。")
    st.stop()

# 日付と雲の割合を個別に取得
timestamps = collection.aggregate_array('system:time_start').getInfo()
clouds = collection.aggregate_array('CLOUDY_PIXEL_PERCENTAGE').getInfo()

# 表示用整形
date_cloud_list = []
for ts, cloud in zip(timestamps, clouds):
    dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
    date_cloud_list.append(f"{dt}\n（雲 {cloud:.1f}%）")

st.sidebar.markdown("**合成に使われた画像の日付と雲の割合**:")
st.sidebar.write(date_cloud_list)

# NDVI・RGB・B4・B8 切り替え
if band_option == "NDVI":
    ndvi_collection = (
        collection
        .sort('system:time_start', False)
        .map(lambda img: img.normalizedDifference(['B8', 'B4']).rename('NDVI'))
    )
    image = ndvi_collection.mosaic().clip(akita)
    vis = {'min': 0.1, 'max': 0.7, 'palette': ['white', 'yellow', 'green']}
elif band_option == "RGB":
    image = collection.mosaic().clip(akita).visualize(bands=['B4', 'B3', 'B2'], min=0, max=3000)
    vis = {}
elif band_option == "B4（赤）":
    image = collection.mosaic().select('B4').clip(akita)
    vis = {'min': 0, 'max': 3000, 'palette': ['black', 'white']}
elif band_option == "B8（近赤外）":
    image = collection.mosaic().select('B8').clip(akita)
    vis = {'min': 0, 'max': 3000, 'palette': ['black', 'white']}

# 地図表示
map_id_dict = image.getMapId(vis)
m = folium.Map(location=[center[1], center[0]], zoom_start=12)
layer_id = f'{band_option}_{ref_date}_{uuid.uuid4()}'
folium.TileLayer(
    tiles=map_id_dict['tile_fetcher'].url_format,
    attr='Google Earth Engine',
    name=layer_id,
    overlay=True,
    control=True
).add_to(m)
folium.LayerControl().add_to(m)

# 凡例（NDVIのときだけ表示）
if band_option == "NDVI":
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
st.title("NDVI (正規化植生指数)")

# 解説
with st.expander("NDVIについての解説"):
    st.markdown("""
### 🌱 NDVI（正規化植生指数）とは？

NDVI（Normalized Difference Vegetation Index）は、人工衛星によるリモートセンシングを用いて地表の植生の密度や健康度を測る指標です。
健康な植生はNIR（近赤外）と緑の光をより多く反射し、赤と青の光をより多く吸収します。この性質を用いて、NDVIでは赤色光とNIRの差分をもとに植生密度を指標化します。

- 値の範囲は **-1.0〜+1.0**
- 高い値（0.6〜0.8）：森林などの**豊かな植生**
- 中程度（0.2〜0.5）：草地や耕作地
- 低い値（0.1以下）：裸地、都市、水域など

---

### 📡 データの取得元と処理方法

このアプリでは、**Google Earth Engine（GEE）** を利用し、**Sentinel-2衛星の表面反射データ（S2_SR_HARMONIZED）** を取得しています。  
指定された期間内の雲の少ない画像を対象に、各画像からNDVIを算出し、**モザイク合成**して全体を1枚にまとめて表示しています。

---

### 🧮 NDVIの算出式
""")

    st.latex(r"NDVI = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}")

    st.markdown("""
- **NIR**（近赤外）：Sentinel-2のバンド8（B8） 中心波長 842nm 解像度 10m
- **Red**（赤色）：Sentinel-2のバンド4（B4） 中心波長 665nm 解像度 10m

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

