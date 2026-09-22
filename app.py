import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os
import json
from datetime import datetime
from io import BytesIO

# ============================================================
# НАСТРОЙКА
# ============================================================
st.set_page_config(page_title="D1,3 PRO MAX", layout="wide", page_icon="🌲")

theme = st.sidebar.radio("🎨 Тема", ["Светлая", "Тёмная"], index=0)
if theme == "Тёмная":
    st.markdown("""
        <style>
            .stApp { background-color: #1e1e1e; color: #e0e0e0; }
            h1, h2, h3 { color: #ffffff; }
        </style>
    """, unsafe_allow_html=True)

st.title("🌲 Калькулятор диаметра ствола PRO MAX")
st.markdown("**Формула:** D1,3 = a · H + b · Dкр + c")

DB_FILE = "trees.db"
SETTINGS_FILE = "settings.json"

# ============================================================
# НАБОРЫ КОЭФФИЦИЕНТОВ
# ============================================================
DEFAULT_PRESETS = {
    "Лиственница Гмелина (Путорана, дисс. Вьюхин)": {"a": 0.38, "b": 0.52, "c": 2.45},
    "Своя формула": {"a": 0.38, "b": 0.52, "c": 2.45},
}

def load_presets():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_PRESETS.copy()

def save_presets(presets):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)

presets = load_presets()

# ============================================================
# БАЗА ДАННЫХ
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, region TEXT, species TEXT, bonitet TEXT, age INTEGER,
            H REAL, Dkr REAL, D13_fact REAL, D13_calc REAL,
            latitude REAL, longitude REAL,
            a REAL, b REAL, c REAL, created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_to_db(df, a, b, c, name, region, species):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO trees (name, region, species, bonitet, age, H, Dkr, D13_fact, D13_calc, latitude, longitude, a, b, c, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, region, species,
            row.get("Разряд_высот", None),
            row.get("Возраст", None),
            row.get("Высота_дерева_м", None),
            row.get("Dкр, м", None),
            row.get("Диаметр_ствола_см", None),
            row.get("D1,3 расч, см", None),
            row.get("Y", None),   # Y — широта
            row.get("X", None),   # X — долгота
            a, b, c, now
        ))
    conn.commit()
    conn.close()

def load_from_db():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM trees ORDER BY id DESC", conn)
    conn.close()
    return df

init_db()

# ============================================================
# ШКАЛЫ БОНИТЕТОВ
# ============================================================
BONITET_SCALES = {
    "Ель (общая)": {
        20:  {"Ia": 12, "I": 10, "II": 8, "III": 6, "IV": 4, "V": 2},
        40:  {"Ia": 20, "I": 17, "II": 14, "III": 11, "IV": 8, "V": 5},
        60:  {"Ia": 26, "I": 22, "II": 18, "III": 14, "IV": 10, "V": 7},
        80:  {"Ia": 30, "I": 26, "II": 21, "III": 17, "IV": 13, "V": 9},
        100: {"Ia": 33, "I": 28, "II": 23, "III": 18, "IV": 14, "V": 10},
    },
    "Сосна (общая)": {
        20:  {"Ia": 14, "I": 12, "II": 10, "III": 8, "IV": 6, "V": 4},
        40:  {"Ia": 24, "I": 21, "II": 18, "III": 14, "IV": 10, "V": 7},
        60:  {"Ia": 30, "I": 27, "II": 23, "III": 19, "IV": 14, "V": 10},
        80:  {"Ia": 34, "I": 30, "II": 26, "III": 21, "IV": 16, "V": 11},
        100: {"Ia": 36, "I": 32, "II": 28, "III": 23, "IV": 17, "V": 12},
    },
    "Башкортостан (ель)": {
        20:  {"Ia": 11, "I": 9, "II": 7, "III": 5, "IV": 3, "V": 2},
        40:  {"Ia": 19, "I": 16, "II": 13, "III": 10, "IV": 7, "V": 4},
        60:  {"Ia": 25, "I": 21, "II": 17, "III": 13, "IV": 9, "V": 6},
        80:  {"Ia": 29, "I": 25, "II": 20, "III": 16, "IV": 12, "V": 8},
        100: {"Ia": 32, "I": 27, "II": 22, "III": 17, "IV": 13, "V": 9},
    },
    "Башкортостан (сосна)": {
        20:  {"Ia": 13, "I": 11, "II": 9, "III": 7, "IV": 5, "V": 3},
        40:  {"Ia": 23, "I": 20, "II": 17, "III": 13, "IV": 9, "V": 6},
        60:  {"Ia": 29, "I": 26, "II": 22, "III": 18, "IV": 13, "V": 9},
        80:  {"Ia": 33, "I": 29, "II": 25, "III": 20, "IV": 15, "V": 10},
        100: {"Ia": 35, "I": 31, "II": 27, "III": 22, "IV": 16, "V": 11},
    },
}

def determine_bonitet(scale, age, height):
    ages = sorted(scale.keys())
    closest_age = min(ages, key=lambda x: abs(x - age))
    row = scale[closest_age]
    best, best_diff = None, float("inf")
    for bon, h in row.items():
        diff = abs(h - height)
        if diff < best_diff:
            best_diff, best = diff, bon
    return best, closest_age

# ============================================================
# БОКОВАЯ ПАНЕЛЬ
# ============================================================
st.sidebar.header("⚙️ Набор коэффициентов")
preset_name = st.sidebar.selectbox("Выберите набор", list(presets.keys()))
preset = presets[preset_name]

st.sidebar.markdown("### Коэффициенты")
a = st.sidebar.number_input("a (при высоте)", value=float(preset["a"]), step=0.01, format="%.4f")
b = st.sidebar.number_input("b (при диаметре кроны)", value=float(preset["b"]), step=0.01, format="%.4f")
c = st.sidebar.number_input("c (свободный член)", value=float(preset["c"]), step=0.01, format="%.4f")

st.sidebar.markdown("---")
new_preset_name = st.sidebar.text_input("Название нового набора", value="")
if st.sidebar.button("💾 Сохранить как набор"):
    if new_preset_name.strip():
        presets[new_preset_name] = {"a": a, "b": b, "c": c}
        save_presets(presets)
        st.sidebar.success(f"Набор «{new_preset_name}» сохранён")
    else:
        st.sidebar.warning("Введите название набора")

# ============================================================
# ВКЛАДКИ
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 Расчёт", "📈 График", "🤖 Модели", "🌳 Бонитет",
    "💾 База данных", "🗺️ Карта", "🌐 API"
])

# ============================================================
# ВКЛАДКА 1: РАСЧЁТ
# ============================================================
with tab1:
    st.header("📋 Расчёт D1,3")

    uploaded = st.file_uploader("Загрузить Excel или CSV", type=["xlsx", "csv"], key="upload1")
    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                try:
                    df_up = pd.read_csv(uploaded, sep="\t")
                    if df_up.shape[1] < 3:
                        uploaded.seek(0)
                        df_up = pd.read_csv(uploaded, sep=";")
                    if df_up.shape[1] < 3:
                        uploaded.seek(0)
                        df_up = pd.read_csv(uploaded, sep=",")
                except Exception:
                    uploaded.seek(0)
                    df_up = pd.read_csv(uploaded, sep=",")
            else:
                df_up = pd.read_excel(uploaded)

            # Автоматическое распознавание столбцов
            rename = {}
            for col in df_up.columns:
                cl = str(col).strip().lower()
                cl_clean = cl.replace("_", " ").replace("\n", " ").replace('"', '')

                if "id дерев" in cl_clean or cl == "id_дерева":
                    rename[col] = "ID_дерева"
                elif "id выдел" in cl_clean or cl == "id_выдела":
                    rename[col] = "ID_выдела"
                elif "таксационный район" in cl_clean and "под" not in cl_clean:
                    rename[col] = "Лесотаксационный_район"
                elif "подрайон" in cl_clean:
                    rename[col] = "Лесотаксационный_подрайон"
                elif cl_clean == "регион":
                    rename[col] = "Регион"
                elif "лесничество" in cl_clean:
                    rename[col] = "Лесничество"
                elif cl_clean == "квартал":
                    rename[col] = "Квартал"
                elif cl_clean == "выдел":
                    rename[col] = "Выдел"
                elif cl_clean == "участок":
                    rename[col] = "Участок"
                elif "дата" in cl_clean:
                    rename[col] = "Дата_обследования"
                elif cl_clean == "x":
                    rename[col] = "X"
                elif cl_clean == "y":
                    rename[col] = "Y"
                elif cl_clean == "z":
                    rename[col] = "Z"
                elif "пород" in cl_clean:
                    rename[col] = "Порода"
                elif "высот" in cl_clean and "дерев" in cl_clean:
                    rename[col] = "Высота_дерева_м"
                elif "площадь" in cl_clean and "крон" in cl_clean:
                    rename[col] = "Площадь_кроны_м2"
                elif "ступень" in cl_clean and "толщин" in cl_clean:
                    rename[col] = "Диаметр_ствола_см"
                elif "разряд" in cl_clean and "высот" in cl_clean:
                    rename[col] = "Разряд_высот"
                elif "объем" in cl_clean or "объём" in cl_clean:
                    rename[col] = "Объем_ствола_м3"
            df_up = df_up.rename(columns=rename)

            st.session_state["uploaded_df"] = df_up
            st.success(f"Загружено {len(df_up)} строк, распознано столбцов: {len(df_up.columns)}")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    if "uploaded_df" in st.session_state:
        default_data = st.session_state["uploaded_df"]
    else:
        default_data = pd.DataFrame({
            "ID_дерева": [1, 2, 3, 4, 5],
            "ID_выдела": [101, 101, 102, 102, 103],
            "Лесотаксационный_район": ["Средне-Уральский"] * 5,
            "Лесотаксационный_подрайон": ["Южно-таежный"] * 5,
            "Регион": ["Башкортостан"] * 5,
            "Лесничество": ["Уфимское"] * 5,
            "Квартал": [45, 45, 46, 46, 47],
            "Выдел": [3, 3, 5, 5, 2],
            "Участок": [1, 1, 1, 1, 1],
            "Дата_обследования": ["2026-09-01"] * 5,
            "X": [55.9, 56.0, 55.8, 55.7, 56.1],
            "Y": [54.7, 54.8, 54.6, 54.5, 54.9],
            "Z": [120, 125, 118, 115, 130],
            "Порода": ["Ель", "Ель", "Сосна", "Сосна", "Берёза"],
            "Высота_дерева_м": [26, 29, 22, 18, 20],
            "Площадь_кроны_м2": [12.6, 19.6, 9.6, 7.1, 8.0],
            "Диаметр_ствола_см": [38, 50, 30, 22, 26],
            "Разряд_высот": [1, 1, 2, 2, 1],
            "Объем_ствола_м3": [0.85, 1.45, 0.55, 0.30, 0.40],
        })

    edited_df = st.data_editor(default_data, num_rows="dynamic",
                                use_container_width=True, key="data_editor")

    # Расчёт
    if "Высота_дерева_м" in edited_df.columns:
        edited_df["H, м"] = edited_df["Высота_дерева_м"]
    if "Площадь_кроны_м2" in edited_df.columns:
        edited_df["Dкр, м"] = (2 * np.sqrt(edited_df["Площадь_кроны_м2"] / np.pi)).round(2)

    if "H, м" in edited_df.columns and "Dкр, м" in edited_df.columns:
        edited_df["D1,3 расч, см"] = (a * edited_df["H, м"] + b * edited_df["Dкр, м"] + c).round(2)

    if "D1,3 расч, см" in edited_df.columns and "Диаметр_ствола_см" in edited_df.columns:
        edited_df["Ошибка, см"] = (edited_df["D1,3 расч, см"] - edited_df["Диаметр_ствола_см"]).round(2)
        edited_df["Ошибка, %"] = ((edited_df["Ошибка, см"] / edited_df["Диаметр_ствола_см"]) * 100).round(2)

    st.dataframe(edited_df, use_container_width=True)

    if "D1,3 расч, см" in edited_df.columns:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Средний D1,3", f"{edited_df['D1,3 расч, см'].mean():.2f} см")
        col2.metric("Минимум", f"{edited_df['D1,3 расч, см'].min():.2f} см")
        col3.metric("Максимум", f"{edited_df['D1,3 расч, см'].max():.2f} см")
        if "Ошибка, см" in edited_df.columns:
            col4.metric("Средняя ошибка", f"{edited_df['Ошибка, см'].mean():+.2f} см")

    st.session_state["df"] = edited_df

    st.markdown("### Экспорт")
    col1, col2 = st.columns(2)
    with col1:
        csv = edited_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Скачать CSV", data=csv,
                            file_name="d13_results.csv", mime="text/csv")
    with col2:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Результаты")
        st.download_button("📥 Скачать Excel", data=buffer.getvalue(),
                            file_name="d13_results.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================================================
# ВКЛАДКА 2: ГРАФИК (3D + 2D, БЕЗ ОСТАТКОВ)
# ============================================================
with tab2:
    st.header("📈 Графики")

    if "df" not in st.session_state:
        st.warning("Сначала заполните данные на вкладке «Расчёт».")
    elif "Высота_дерева_м" not in st.session_state["df"].columns:
        st.warning("Нет столбца **Высота_дерева_м**.")
    elif "Площадь_кроны_м2" not in st.session_state["df"].columns:
        st.warning("Нет столбца **Площадь_кроны_м2**.")
    else:
        df = st.session_state["df"]

        # Готовим данные
        H_vals = df["Высота_дерева_м"].values
        S_vals = df["Площадь_кроны_м2"].values
        Dkr_vals = 2 * np.sqrt(S_vals / np.pi)  # диаметр кроны из площади
        D13_vals = a * H_vals + b * Dkr_vals + c  # расчётный D1,3

        # ================================================
        # 3D-ГРАФИК: D1,3 от H и ПЛОЩАДИ КРОНЫ
        # ================================================
        st.subheader("3D-график: D1,3 от высоты и площади кроны")

        # Сетка для поверхности
        H_range = np.linspace(max(1, H_vals.min() * 0.7), H_vals.max() * 1.3, 50)
        S_range = np.linspace(max(0.5, S_vals.min() * 0.7), S_vals.max() * 1.3, 50)
        H_grid, S_grid = np.meshgrid(H_range, S_range)

        # Переводим площадь кроны в диаметр кроны
        Dkr_grid = 2 * np.sqrt(S_grid / np.pi)
        # Считаем D1,3 по формуле
        D13_grid = a * H_grid + b * Dkr_grid + c

        fig3d = go.Figure(data=[
            go.Surface(
                x=H_grid, y=S_grid, z=D13_grid,
                colorscale="Viridis",
                colorbar=dict(title="D1,3, см"),
                opacity=0.9,
                name="Поверхность"
            ),
            go.Scatter3d(
                x=H_vals, y=S_vals, z=D13_vals,
                mode="markers",
                marker=dict(size=7, color="red", symbol="circle"),
                name="Расчёт"
            ),
        ])

        # Если есть факт — добавляем
        if "Диаметр_ствола_см" in df.columns:
            mask = ~pd.isna(df["Диаметр_ствола_см"]) & ~pd.isna(df["Высота_дерева_м"]) & ~pd.isna(df["Площадь_кроны_м2"])
            if mask.sum() > 0:
                fig3d.add_trace(go.Scatter3d(
                    x=df.loc[mask, "Высота_дерева_м"],
                    y=df.loc[mask, "Площадь_кроны_м2"],
                    z=df.loc[mask, "Диаметр_ствола_см"],
                    mode="markers",
                    marker=dict(size=9, color="yellow", symbol="diamond"),
                    name="Факт"
                ))

        fig3d.update_layout(
            scene=dict(
                xaxis_title="H, м (высота)",
                yaxis_title="S, м² (площадь кроны)",
                zaxis_title="D1,3, см (диаметр ствола)"
            ),
            height=700
        )
        st.plotly_chart(fig3d, use_container_width=True)

        # ================================================
        # 2D-ГРАФИКИ (для сравнения)
        # ================================================
        st.subheader("Зависимости в 2D")

        fig2d = make_subplots(
            rows=1, cols=2,
            subplot_titles=("D1,3 от высоты H", "D1,3 от площади кроны S")
        )

        # График 1: D1,3 от H
        H_line = np.linspace(H_range.min(), H_range.max(), 100)
        S_avg = S_vals.mean()
        Dkr_avg = 2 * np.sqrt(S_avg / np.pi)
        fig2d.add_trace(go.Scatter(
            x=H_line, y=a * H_line + b * Dkr_avg + c,
            mode="lines", name=f"Линия (S={S_avg:.1f} м²)",
            line=dict(color="blue", width=3)), row=1, col=1)
        fig2d.add_trace(go.Scatter(
            x=H_vals, y=D13_vals,
            mode="markers", name="Расчёт",
            marker=dict(size=10, color="red")), row=1, col=1)
        if "Диаметр_ствола_см" in df.columns:
            mask = ~pd.isna(df["Диаметр_ствола_см"])
            if mask.sum() > 0:
                fig2d.add_trace(go.Scatter(
                    x=df.loc[mask, "Высота_дерева_м"],
                    y=df.loc[mask, "Диаметр_ствола_см"],
                    mode="markers", name="Факт",
                    marker=dict(size=10, color="orange", symbol="diamond")), row=1, col=1)

        # График 2: D1,3 от S
        S_line = np.linspace(S_range.min(), S_range.max(), 100)
        H_avg = H_vals.mean()
        Dkr_S_line = 2 * np.sqrt(S_line / np.pi)
        fig2d.add_trace(go.Scatter(
            x=S_line, y=a * H_avg + b * Dkr_S_line + c,
            mode="lines", name=f"Линия (H={H_avg:.1f} м)",
            line=dict(color="green", width=3)), row=1, col=2)
        fig2d.add_trace(go.Scatter(
            x=S_vals, y=D13_vals,
            mode="markers", name="Расчёт",
            marker=dict(size=10, color="red"),
            showlegend=False), row=1, col=2)
        if "Диаметр_ствола_см" in df.columns:
            mask = ~pd.isna(df["Диаметр_ствола_см"])
            if mask.sum() > 0:
                fig2d.add_trace(go.Scatter(
                    x=df.loc[mask, "Площадь_кроны_м2"],
                    y=df.loc[mask, "Диаметр_ствола_см"],
                    mode="markers", name="Факт",
                    marker=dict(size=10, color="orange", symbol="diamond"),
                    showlegend=False), row=1, col=2)

        fig2d.update_xaxes(title_text="H, м (высота)", row=1, col=1)
        fig2d.update_xaxes(title_text="S, м² (площадь кроны)", row=1, col=2)
        fig2d.update_yaxes(title_text="D1,3, см", row=1, col=1)
        fig2d.update_yaxes(title_text="D1,3, см", row=1, col=2)
        fig2d.update_layout(height=450)
        st.plotly_chart(fig2d, use_container_width=True)

# ============================================================
# ВКЛАДКА 3: МОДЕЛИ
# ============================================================
with tab3:
    st.header("🤖 Сравнение моделей и ML")

    if "df" not in st.session_state:
        st.warning("Сначала заполните данные на вкладке «Расчёт».")
    elif "Диаметр_ствола_см" not in st.session_state["df"].columns:
        st.info("Нужен столбец **Диаметр_ствола_см** (фактический).")
    else:
        df = st.session_state["df"]
        df_fit = df.dropna(subset=["H, м", "Dкр, м", "Диаметр_ствола_см"])

        if len(df_fit) >= 5:
            X = df_fit[["H, м", "Dкр, м"]].values
            y = df_fit["Диаметр_ствола_см"].values

            st.markdown("### Сравнение математических моделей")

            def fit_linear(X_in, y_in):
                Xb = np.column_stack([X_in, np.ones(len(X_in))])
                coeffs, _, _, _ = np.linalg.lstsq(Xb, y_in, rcond=None)
                pred = Xb @ coeffs
                r2 = 1 - np.sum((y_in - pred) ** 2) / np.sum((y_in - np.mean(y_in)) ** 2)
                rmse = np.sqrt(np.mean((y_in - pred) ** 2))
                return coeffs, r2, rmse, pred

            X1 = np.column_stack([df_fit["H, м"].values, df_fit["Dкр, м"].values])
            c1, r2_1, rmse_1, pred1 = fit_linear(X1, y)

            X2 = df_fit["H, м"].values.reshape(-1, 1)
            c2, r2_2, rmse_2, pred2 = fit_linear(X2, y)

            log_H = np.log(df_fit["H, м"].values)
            log_D = np.log(y)
            c3, _, _, _ = np.linalg.lstsq(
                np.column_stack([log_H, np.ones(len(log_H))]), log_D, rcond=None)
            b3, log_a3 = c3
            a3 = np.exp(log_a3)
            pred3 = a3 * df_fit["H, м"].values ** b3
            r2_3 = 1 - np.sum((y - pred3) ** 2) / np.sum((y - np.mean(y)) ** 2)
            rmse_3 = np.sqrt(np.mean((y - pred3) ** 2))

            results = pd.DataFrame({
                "Модель": ["D = aH + bDкр + c", "D = aH + b", "D = a·H^b"],
                "R²": [f"{r2_1:.4f}", f"{r2_2:.4f}", f"{r2_3:.4f}"],
                "RMSE, см": [f"{rmse_1:.2f}", f"{rmse_2:.2f}", f"{rmse_3:.2f}"],
            })
            st.dataframe(results, use_container_width=True)

            st.markdown("**Коэффициенты:**")
            st.write(f"- Модель 1: a = {c1[0]:.4f}, b = {c1[1]:.4f}, c = {c1[2]:.4f}")
            st.write(f"- Модель 2: a = {c2[0]:.4f}, b = {c2[1]:.4f}")
            st.write(f"- Модель 3: a = {a3:.4f}, b = {b3:.4f}")

            st.markdown("### Машинное обучение")
            try:
                from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
                from sklearn.linear_model import LinearRegression
                from sklearn.metrics import r2_score, mean_squared_error

                models_ml = {
                    "Линейная регрессия": LinearRegression(),
                    "Random Forest": RandomForestRegressor(n_estimators=100, random_state=42),
                    "Gradient Boosting": GradientBoostingRegressor(n_estimators=100, random_state=42),
                }
                ml_results = []
                best_r2, best_name = -np.inf, None
                for name, model in models_ml.items():
                    model.fit(X, y)
                    pred = model.predict(X)
                    r2 = r2_score(y, pred)
                    rmse = np.sqrt(mean_squared_error(y, pred))
                    ml_results.append({
                        "Модель": name,
                        "R²": f"{r2:.4f}",
                        "RMSE, см": f"{rmse:.2f}",
                    })
                    if r2 > best_r2:
                        best_r2, best_name = r2, name
                st.dataframe(pd.DataFrame(ml_results), use_container_width=True)
                st.success(f"🏆 Лучшая модель: **{best_name}** (R² = {best_r2:.4f})")
            except ImportError:
                st.warning("Для ML установите: `pip install scikit-learn`")

            st.markdown("### 🔮 Прогноз для нового дерева")
            col1, col2 = st.columns(2)
            with col1:
                H_new = st.number_input("H, м", value=26.0, step=0.5, key="ml_H")
            with col2:
                Dkr_new = st.number_input("Dкр, м", value=4.0, step=0.1, key="ml_Dkr")
            if st.button("Рассчитать"):
                D13 = a * H_new + b * Dkr_new + c
                st.success(f"**D1,3 = {D13:.2f} см**")
        else:
            st.info("Нужно минимум 5 деревьев с заполненным **Диаметр_ствола_см**.")

# ============================================================
# ВКЛАДКА 4: БОНИТЕТ
# ============================================================
with tab4:
    st.header("🌳 Определение бонитета")

    col1, col2, col3 = st.columns(3)
    with col1:
        scale_name = st.selectbox("Порода / Регион", list(BONITET_SCALES.keys()))
    with col2:
        age = st.number_input("Возраст, лет", value=100, step=10, min_value=10)
    with col3:
        height_bon = st.number_input("Высота, м", value=26.0, step=0.5)

    if st.button("🔍 Определить бонитет"):
        bon, closest_age = determine_bonitet(BONITET_SCALES[scale_name], age, height_bon)
        st.success(f"**Бонитет: {bon}** (по шкале «{scale_name}» для возраста {closest_age} лет)")

# ============================================================
# ВКЛАДКА 5: БАЗА ДАННЫХ
# ============================================================
with tab5:
    st.header("💾 База данных")

    col1, col2, col3 = st.columns(3)
    with col1:
        exp_name = st.text_input("Название", value="Эксперимент")
    with col2:
        exp_region = st.text_input("Регион", value="Башкортостан")
    with col3:
        exp_species = st.text_input("Порода", value="Ель")

    if st.button("💾 Сохранить текущие данные"):
        if "df" in st.session_state:
            save_to_db(st.session_state["df"], a, b, c, exp_name, exp_region, exp_species)
            st.success("Сохранено!")
        else:
            st.warning("Нет данных для сохранения.")

    if st.checkbox("📊 Показать сохранённые записи"):
        db_df = load_from_db()
        if len(db_df) > 0:
            st.dataframe(db_df, use_container_width=True)

            st.markdown("### 📄 PDF-отчёт")
            if st.button("📄 Сгенерировать PDF"):
                try:
                    from reportlab.lib.pagesizes import A4
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

                    buffer = BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=A4)
                    styles = getSampleStyleSheet()
                    elements = []

                    title_style = ParagraphStyle("Title", parent=styles["Title"],
                                                  fontSize=18, textColor=colors.darkgreen)
                    elements.append(Paragraph("Отчёт: Калькулятор D1,3", title_style))
                    elements.append(Spacer(1, 20))

                    meta = f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}<br/>Формула: D1,3 = {a}*H + {b}*Dкр + {c}<br/>Записей: {len(db_df)}"
                    elements.append(Paragraph(meta, styles["Normal"]))
                    elements.append(Spacer(1, 20))

                    table_data = [["ID", "Порода", "Регион", "H, м", "Dкр, м", "D1,3 расч"]]
                    for _, row in db_df.head(50).iterrows():
                        table_data.append([
                            str(row.get("id", "")),
                            str(row.get("species", "")),
                            str(row.get("region", "")),
                            f"{row.get('H', 0):.1f}",
                            f"{row.get('Dkr', 0):.1f}",
                            f"{row.get('D13_calc', 0):.2f}",
                        ])
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ]))
                    elements.append(table)
                    doc.build(elements)
                    buffer.seek(0)

                    st.download_button("📥 Скачать PDF", data=buffer.getvalue(),
                                       file_name=f"report_{datetime.now().strftime('%Y%m%d')}.pdf",
                                       mime="application/pdf")
                except ImportError:
                    st.warning("Установите: pip install reportlab")

            csv_db = db_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Скачать всю базу (CSV)", data=csv_db,
                               file_name="trees_db.csv", mime="text/csv")
        else:
            st.info("База пуста.")

# ============================================================
# ВКЛАДКА 6: КАРТА
# ============================================================
with tab6:
    st.header("🗺️ Карта пробных площадей")

    if "df" not in st.session_state:
        st.warning("Сначала заполните данные на вкладке «Расчёт».")
    else:
        df = st.session_state["df"]
        if "X" in df.columns and "Y" in df.columns:
            df_map = df.dropna(subset=["X", "Y"])
            if len(df_map) > 0:
                try:
                    import folium
                    from streamlit_folium import st_folium

                    # X — долгота, Y — широта
                    center = [df_map["Y"].mean(), df_map["X"].mean()]
                    m = folium.Map(location=center, zoom_start=10)

                    for _, row in df_map.iterrows():
                        D13 = row.get("D1,3 расч, см", 0)
                        color = "green" if D13 < 20 else "orange" if D13 < 40 else "red"
                        folium.CircleMarker(
                            location=[row["Y"], row["X"]],
                            radius=7, color=color, fill=True, fill_opacity=0.8,
                            popup=f"ID {row.get('ID_дерева', '')}: H={row.get('Высота_дерева_м', '')} м, D1,3={D13} см"
                        ).add_to(m)

                    st_folium(m, width=1200, height=500)
                except ImportError:
                    st.warning("Установите: pip install folium streamlit-folium")
            else:
                st.info("Нет данных с координатами.")
        else:
            st.info("Нужны столбцы **X** и **Y**.")

# ============================================================
# ВКЛАДКА 7: API
# ============================================================
with tab7:
    st.header("🌐 API для других программ")
    st.markdown("Инструкция, как сделать API для интеграции с другими программами.")

    st.subheader("Что такое API")
    st.markdown("API — это язык, на котором одна программа общается с другой.")
    st.code('POST /calculate\n{"H": 26, "Dkr": 4}', language="json")
    st.markdown("Сервер отвечает:")
    st.code('{"D13": 14.51}', language="json")

    st.subheader("Код API (FastAPI)")
    st.code('''
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class TreeInput(BaseModel):
    H: float
    Dkr: float
    a: float = 0.38
    b: float = 0.52
    c: float = 2.45

@app.post("/calculate")
def calculate(data: TreeInput):
    D13 = data.a * data.H + data.b * data.Dkr + data.c
    return {"D13": round(D13, 2)}
''', language="python")

    st.subheader("Как запустить API")
    st.code('pip install fastapi uvicorn\nuvicorn api:app --reload --port 8000', language="bash")

    st.subheader("Как пользоваться")
    st.code('curl -X POST http://localhost:8000/calculate -H "Content-Type: application/json" -d \'{"H": 26, "Dkr": 4}\'', language="bash")

# ============================================================
# ФУТЕР
# ============================================================
st.markdown("---")
st.caption("🌲 D1,3 PRO MAX | Расчёт + 3D/2D-графики + ML + Бонитет + База + Карта + API")
