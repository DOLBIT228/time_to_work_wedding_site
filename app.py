import requests
import pandas as pd
import time
import streamlit as st
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor

# =========================================================
# AUTH
# =========================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:

    st.title("🔐 Авторизація")

    login = st.text_input("Логін")

    password = st.text_input(
        "Пароль",
        type="password"
    )

    if st.button("Увійти"):

        if (
            login == st.secrets["APP_LOGIN"]
            and
            password == st.secrets["APP_PASSWORD"]
        ):

            st.session_state.authenticated = True

            st.rerun()

        else:

            st.error(
                "Невірний логін або пароль"
            )

    st.stop()

from datetime import (
    datetime,
    timedelta,
    time as dt_time
)

st.set_page_config(
    page_title="SLA Dashboard",
    layout="wide"
)

# =========================================================
# FILTERS
# =========================================================

st.sidebar.header("Фільтри")

col1, col2 = st.sidebar.columns(2)

with col1:

    DATE_FROM = str(
        st.date_input(
            "Від",
            value=datetime.now().date()
        )
    )

with col2:

    DATE_TO = str(
        st.date_input(
            "До",
            value=datetime.now().date()
        )
    )

run = st.sidebar.button(
    "Запустити аналіз",
    use_container_width=True
)

clear_cache = st.sidebar.button(
    "Очистити кеш",
    use_container_width=True
)

st.title("📊 SLA Dashboard")

# =========================================================
# CONFIG
# =========================================================

WEBHOOK_URL = st.secrets["WEBHOOK_URL"]

# Воронка
FUNNEL_ID = st.secrets["FUNNEL_ID"]

# Статуси
TAKEN_STAGE = st.secrets["TAKEN_STAGE"]
CALLED_STAGE = st.secrets["CALLED_STAGE"]

# Хто реально взяв угоду
TAKEN_BY_FIELD = st.secrets["TAKEN_BY_FIELD"]

# Менеджери
MANAGERS = st.secrets["MANAGERS"]

# Робочі години
WORK_START = dt_time(10, 0)
WORK_END = dt_time(19, 0)

# ОБІД
LUNCH_START = dt_time(14, 0)
LUNCH_END = dt_time(15, 0)

# API
API_DELAY = 0.35

# =========================================================
# HELPERS
# =========================================================

def parse_bitrix_datetime(date_string):

    formats = [

        "%Y-%m-%dT%H:%M:%S%z",

        "%Y-%m-%dT%H:%M:%S",

        "%Y-%m-%d %H:%M:%S"
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                date_string,
                fmt
            )

        except:
            pass

    raise Exception(
        f"Не вдалося розпарсити дату: "
        f"{date_string}"
    )


def minutes_to_human(minutes):

    if (
        minutes is None
        or pd.isna(minutes)
    ):
        return "-"

    minutes = round(float(minutes))

    hours = minutes // 60
    mins = minutes % 60

    if hours == 0:
        return f"{mins} хв"

    return f"{hours}г {mins}хв"

# =========================================================
# SLA LOGIC
# =========================================================

def calculate_working_minutes(start_dt, end_dt):

    if start_dt >= end_dt:
        return 1

    total_minutes = 0

    current_day = start_dt.date()

    while current_day <= end_dt.date():

        # =====================================
        # WORK INTERVAL
        # =====================================

        work_start = datetime.combine(
            current_day,
            WORK_START
        )

        work_end = datetime.combine(
            current_day,
            WORK_END
        )

        actual_start = max(
            start_dt.replace(tzinfo=None),
            work_start
        )

        actual_end = min(
            end_dt.replace(tzinfo=None),
            work_end
        )

        if actual_start < actual_end:

            delta = (
                actual_end - actual_start
            )

            total_minutes += (
                delta.total_seconds() / 60
            )

        # =====================================
        # LUNCH EXCLUDE
        # =====================================

        lunch_start = datetime.combine(
            current_day,
            LUNCH_START
        )

        lunch_end = datetime.combine(
            current_day,
            LUNCH_END
        )

        overlap_start = max(
            actual_start,
            lunch_start
        )

        overlap_end = min(
            actual_end,
            lunch_end
        )

        if overlap_start < overlap_end:

            lunch_delta = (
                overlap_end - overlap_start
            )

            total_minutes -= (
                lunch_delta.total_seconds() / 60
            )

        current_day += timedelta(days=1)

    return max(1, round(total_minutes))

# =========================================================
# API
# =========================================================

def bitrix_request(method, data=None):

    url = f"{WEBHOOK_URL}{method}.json"

    time.sleep(0.05)

    last_error = None

    for attempt in range(4):

        response = requests.post(
            url,
            json=data,
            timeout=30
        )

        result = response.json()

        if "error" not in result:
            return result

        error_code = result.get("error", "")

        if error_code in {
            "QUERY_LIMIT_EXCEEDED",
            "TOO_MANY_REQUESTS",
            "OPERATION_TIME_LIMIT"
        }:
            time.sleep(2 + attempt)
            last_error = result
            continue

        raise Exception(
            f"{method}: {result}"
        )

    raise Exception(
        f"{method}: {last_error}"
    )

# =========================================================
# DEALS
# =========================================================

def get_all_deals():

    all_deals = []

    start = 0

    while True:

        payload = {

            "filter": {

                "CATEGORY_ID": FUNNEL_ID,

                ">=DATE_CREATE":
                    f"{DATE_FROM}T00:00:00",

                "<=DATE_CREATE":
                    f"{DATE_TO}T23:59:59"
            },

            "select": [

                "ID",

                "TITLE",

                "DATE_CREATE",

                "ASSIGNED_BY_ID",

                "CATEGORY_ID",

                TAKEN_BY_FIELD
            ],

            "start": start
        }

        result = bitrix_request(
            "crm.deal.list",
            payload
        )

        deals = result.get(
            "result",
            []
        )

        if not deals:
            break

        all_deals.extend(deals)

        if "next" not in result:
            break

        start = result["next"]

        time.sleep(API_DELAY)

    return all_deals

# =========================================================
# HISTORY
# =========================================================

@st.cache_data(show_spinner=False)
def get_stage_history(deal_id):

    payload = {

        "entityTypeId": 2,

        "filter": {
            "OWNER_ID": deal_id
        }
    }

    try:
        result = bitrix_request(
            "crm.stagehistory.list",
            payload
        )
    except Exception:
        return []

    items = (
        result.get("result", {})
        .get("items", [])
    )

    return items


def find_stage_datetime(
    stage_history,
    target_stage
):

    for item in stage_history:

        stage_id = (
            item.get("STAGE_ID")
            or item.get("STAGE_ID_TO")
        )

        if stage_id == target_stage:

            created_time = (

                item.get("CREATED_TIME")

                or item.get("MODIFIED_TIME")

                or item.get("DATE_CREATE")
            )

            if created_time:
                return created_time

    return None

# =========================================================
# ANALYSIS
# =========================================================

@st.cache_data(show_spinner=False)
def run_analysis():

    deals = get_all_deals()

    rows = []

    # =====================================
    # LOAD HISTORY PARALLEL
    # =====================================

    history_map = {}

    deal_ids = [
        deal["ID"]
        for deal in deals
    ]

    with ThreadPoolExecutor(max_workers=10) as executor:

        histories = executor.map(
            get_stage_history,
            deal_ids
        )

        for deal_id, history in zip(
            deal_ids,
            histories
        ):

            history_map[deal_id] = history

    progress = st.progress(0)

    status = st.empty()

    for index, deal in enumerate(deals):

        progress.progress(
            (index + 1) / len(deals)
        )

        status.info(
            f"Аналізуємо угоду "
            f"{index + 1}/{len(deals)}"
        )

        try:

            deal_id = deal["ID"]

            # =================================
            # MANAGER
            # =================================

            taken_by_id = str(
                deal.get(
                    TAKEN_BY_FIELD,
                    ""
                )
            ).strip()

            if (
                taken_by_id
                and
                taken_by_id in MANAGERS
            ):

                manager_id = taken_by_id

            else:

                manager_id = str(
                    deal.get(
                        "ASSIGNED_BY_ID",
                        ""
                    )
                ).strip()

            manager = MANAGERS.get(
                manager_id,
                f"USER ID {manager_id}"
            )

            # =================================
            # DATES
            # =================================

            created_dt = parse_bitrix_datetime(
                deal["DATE_CREATE"]
            )

            history = history_map.get(
                deal_id,
                []
            )

            taken_raw = find_stage_datetime(
                history,
                TAKEN_STAGE
            )

            called_raw = find_stage_datetime(
                history,
                CALLED_STAGE
            )

            # =================================
            # TAKEN SLA
            # =================================

            if taken_raw:

                taken_dt = parse_bitrix_datetime(
                    taken_raw
                )

                taken_sla = (
                    calculate_working_minutes(
                        created_dt,
                        taken_dt
                    )
                )

            else:

                taken_dt = None

                taken_sla = None

            # =================================
            # CALLED SLA
            # =================================

            if called_raw:

                called_dt = parse_bitrix_datetime(
                    called_raw
                )

                called_sla = (
                    calculate_working_minutes(
                        created_dt,
                        called_dt
                    )
                )

            else:

                called_dt = None

                called_sla = None

            # =================================
            # RESULT
            # =================================

            rows.append({

                "Deal ID":
                    deal_id,

                "Title":
                    deal.get(
                        "TITLE",
                        ""
                    ),

                "Manager":
                    manager,

                "Created":
                    created_dt.strftime(
                        "%Y-%m-%d %H:%M"
                    ),

                # ============================
                # TAKEN
                # ============================

                "Taken In Work":
                    (
                        taken_dt.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if taken_dt
                        else "NOT TAKEN"
                    ),

                "Taken SLA Minutes":
                    taken_sla,

                "Taken SLA Human":
                    minutes_to_human(
                        taken_sla
                    ),

                # ============================
                # CALLED
                # ============================

                "Called Datetime":
                    (
                        called_dt.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if called_dt
                        else "NOT CALLED"
                    ),

                "Called SLA Minutes":
                    called_sla,

                "Called SLA Human":
                    minutes_to_human(
                        called_sla
                    )
            })

        except Exception as e:
            status.warning(
                f"Помилка обробки угоди "
                f"{deal_id}: {e}"
            )

    progress.empty()

    status.empty()

    return pd.DataFrame(rows)

# =========================================================
# STREAMLIT APP
# =========================================================

if clear_cache:

    st.cache_data.clear()

    st.session_state.pop("df", None)

    st.success("Кеш очищено. Запустіть аналіз повторно.")

if run:

    with st.spinner(
        "Аналізуємо SLA..."
    ):

        df = run_analysis()

        st.session_state["df"] = df

if "df" in st.session_state:

    df = st.session_state["df"]

    # =====================================
    # VALID DATA
    # =====================================

    taken_valid = df[
        df["Taken SLA Minutes"].notna()
    ]

    called_valid = df[
        df["Called SLA Minutes"].notna()
    ]

    # =====================================
    # TABS
    # =====================================

    tab1, tab2, tab3 = st.tabs([

        "📈 Загальна ситуація",

        "👨‍💼 Менеджери",

        "📋 Угоди"
    ])

    # =====================================
    # TAB 1
    # =====================================

    with tab1:

        st.subheader(
            "Загальна ситуація"
        )

        avg_taken = round(
            taken_valid[
                "Taken SLA Minutes"
            ].mean(),
            2
        )

        avg_called = round(
            called_valid[
                "Called SLA Minutes"
            ].mean(),
            2
        )

        median_taken = round(
            taken_valid[
                "Taken SLA Minutes"
            ].median(),
            2
        )

        median_called = round(
            called_valid[
                "Called SLA Minutes"
            ].median(),
            2
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Угод",
            len(df)
        )

        col2.metric(
            "Average TAKEN",
            minutes_to_human(
                avg_taken
            )
        )

        col3.metric(
            "Average CALLED",
            minutes_to_human(
                avg_called
            )
        )

        col4.metric(
            "NOT CALLED",
            len(
                df[
                    df[
                        "Called SLA Minutes"
                    ].isna()
                ]
            )
        )

        st.divider()

        col5, col6 = st.columns(2)

        col5.metric(
            "Median TAKEN",
            minutes_to_human(
                median_taken
            )
        )

        col6.metric(
            "Median CALLED",
            minutes_to_human(
                median_called
            )
        )

        st.divider()

        fig = px.histogram(

            taken_valid,

            x="Taken SLA Minutes",

            nbins=20,

            title="Taken SLA Distribution"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        fig2 = px.histogram(

            called_valid,

            x="Called SLA Minutes",

            nbins=20,

            title="Called SLA Distribution"
        )

        st.plotly_chart(
            fig2,
            use_container_width=True
        )

    # =====================================
    # TAB 2
    # =====================================

    with tab2:

        st.subheader(
            "Менеджери"
        )

        manager_df = (

            df

            .groupby("Manager")

            .agg({

                "Deal ID":
                    "count",

                "Taken SLA Minutes": [
                    "mean",
                    "median",
                    "max"
                ],

                "Called SLA Minutes": [
                    "mean",
                    "median",
                    "max"
                ]
            })

            .reset_index()
        )

        manager_df.columns = [

            "Manager",

            "Deals",

            "Taken Avg",
            "Taken Median",
            "Taken Max",

            "Called Avg",
            "Called Median",
            "Called Max"
        ]

        # =====================================
        # HUMAN FORMAT
        # =====================================

        manager_df["Taken Avg"] = (
            manager_df["Taken Avg"]
            .apply(minutes_to_human)
        )

        manager_df["Taken Median"] = (
            manager_df["Taken Median"]
            .apply(minutes_to_human)
        )

        manager_df["Taken Max"] = (
            manager_df["Taken Max"]
            .apply(minutes_to_human)
        )

        manager_df["Called Avg"] = (
            manager_df["Called Avg"]
            .apply(minutes_to_human)
        )

        manager_df["Called Median"] = (
            manager_df["Called Median"]
            .apply(minutes_to_human)
        )

        manager_df["Called Max"] = (
            manager_df["Called Max"]
            .apply(minutes_to_human)
        )

        st.dataframe(
            manager_df,
            use_container_width=True
        )

        st.divider()

        fig = px.bar(

            manager_df,

            x="Manager",

            y="Called Avg",

            title="Average Called SLA"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # =====================================
    # TAB 3
    # =====================================

    with tab3:

        st.subheader(
            "Угоди"
        )

        sort_option = st.selectbox(

            "Сортування",

            [
                "Найдовші CALLED SLA",
                "Найдовші TAKEN SLA",
                "Найшвидші CALLED SLA",
                "Найшвидші TAKEN SLA"
            ]
        )

        deals_df = df.copy()

        if sort_option == "Найдовші CALLED SLA":

            deals_df = deals_df.sort_values(
                by="Called SLA Minutes",
                ascending=False,
                na_position="last"
            )

        elif sort_option == "Найдовші TAKEN SLA":

            deals_df = deals_df.sort_values(
                by="Taken SLA Minutes",
                ascending=False,
                na_position="last"
            )

        elif sort_option == "Найшвидші CALLED SLA":

            deals_df = deals_df.sort_values(
                by="Called SLA Minutes",
                ascending=True,
                na_position="last"
            )

        else:

            deals_df = deals_df.sort_values(
                by="Taken SLA Minutes",
                ascending=True,
                na_position="last"
            )

        display_df = deals_df.fillna("")

        st.dataframe(
            display_df,
            use_container_width=True,
            height=700
        )

        st.divider()

        long_sla = deals_df[
            deals_df[
                "Called SLA Minutes"
            ] >= 60
        ]

        st.subheader(
            "🔥 Довгі CALLED SLA"
        )

        st.dataframe(
            long_sla,
            use_container_width=True
        )

        csv = deals_df.to_csv(
            index=False
        )

        st.download_button(

            label="📥 Завантажити CSV",

            data=csv,

            file_name="sla_report.csv",

            mime="text/csv"
        )
