
from pathlib import Path

import pandas as pd
import streamlit as st

# -------------------------------
# 1. Dashboard configuration
# -------------------------------
st.set_page_config(
    page_title="Cart2Insights Dashboard",
    page_icon="🛒",
    layout="wide"
)

st.title("🛒 Cart2Insights")
st.subheader("Decoding E-Commerce Performance")
st.caption("E-commerce sales, orders, products and customer reviews")

# -------------------------------
# 2. Load cleaned datasets
# -------------------------------
DATA_PATH = Path(__file__).resolve().parent / "Data" / "cleaned"


@st.cache_data
def load_data():
    files = {
        "orders": "orders.csv",
        "items": "order_items.csv",
        "products": "products.csv",
        "categories": "category_translation.csv",
        "reviews": "reviews.csv",
        "payments": "payments.csv",
        "customers": "customers.csv",
    }

    data = {
        name: pd.read_csv(DATA_PATH / filename)
        for name, filename in files.items()
    }

    data["orders"]["order_purchase_timestamp"] = pd.to_datetime(
        data["orders"]["order_purchase_timestamp"],
        errors="coerce"
    )

    data["orders"]["order_delivered_customer_date"] = pd.to_datetime(
        data["orders"]["order_delivered_customer_date"],
        errors="coerce"
    )

    data["orders"]["order_estimated_delivery_date"] = pd.to_datetime(
        data["orders"]["order_estimated_delivery_date"],
        errors="coerce"
    )

    return data


try:
    data = load_data()
except Exception as e:
    st.error(f"Unable to load the datasets: {e}")
    st.info(
        "Check that the CSV files are inside "
        "Cart2Insights/data/cleaned."
    )
    st.stop()

orders = data["orders"]
items = data["items"]
products = data["products"]
customers = data["customers"]
categories = data["categories"]
reviews = data["reviews"]

# -------------------------------
# 3. Prepare product categories
# -------------------------------
category_column = "product_category_name"

if category_column in products.columns:
    products = products.copy()

    if (
        category_column in categories.columns
        and "product_category_name_english" in categories.columns
    ):
        products = products.merge(
            categories[
                [
                    "product_category_name",
                    "product_category_name_english"
                ]
            ].drop_duplicates("product_category_name"),
            on="product_category_name",
            how="left"
        )

        products["category_display"] = (
            products["product_category_name_english"]
            .fillna(products["product_category_name"])
            .fillna("Unknown")
        )
    else:
        products["category_display"] = (
            products[category_column].fillna("Unknown")
        )
else:
    products["category_display"] = "Unknown"

# -------------------------------
# 4. Sidebar filters
# -------------------------------
st.sidebar.header("Dashboard Filters")

statuses = sorted(orders["order_status"].dropna().unique())
selected_statuses = st.sidebar.multiselect(
    "Order status",
    statuses,
    default=statuses
)

valid_dates = orders["order_purchase_timestamp"].dropna()

if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    selected_dates = st.sidebar.date_input(
        "Purchase date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates
else:
    start_date = end_date = None

filtered_orders = orders[
    orders["order_status"].isin(selected_statuses)
].copy()

if start_date is not None and end_date is not None:
    purchase_dates = filtered_orders["order_purchase_timestamp"].dt.date

    filtered_orders = filtered_orders[
        (purchase_dates >= start_date) &
        (purchase_dates <= end_date)
    ]
# -------------------------------
# 5. Calculate KPIs
# -------------------------------
filtered_items = items[
    items["order_id"].isin(filtered_orders["order_id"])
].copy()

total_orders = filtered_orders["order_id"].nunique()

delivered_orders = filtered_orders.loc[
    filtered_orders["order_status"] == "delivered",
    "order_id"
].nunique()

product_revenue = filtered_items["price"].sum()

avg_order_value = (
    filtered_items.groupby("order_id")["price"].sum().mean()
    if not filtered_items.empty
    else 0
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Orders", f"{total_orders:,}")
col2.metric("Delivered Orders", f"{delivered_orders:,}")
col3.metric("Product Revenue", f"{product_revenue:,.2f}")
col4.metric("Avg. Product Value / Order", f"{avg_order_value:,.2f}")

st.caption(
    "Product revenue uses item prices only; freight is excluded. "
    "The average is calculated from product prices per order."
)

st.divider()

# -------------------------------
# 6. Monthly revenue trend
# -------------------------------
st.subheader("📈 Monthly Revenue Trend")

if not filtered_items.empty:
    monthly_items = filtered_items.merge(
        filtered_orders[["order_id", "order_purchase_timestamp"]],
        on="order_id",
        how="inner"
    )

    monthly_items["month"] = (
        monthly_items["order_purchase_timestamp"].dt.to_period("M").astype(str)
    )

    monthly_revenue = (
        monthly_items.groupby("month", as_index=False)["price"]
        .sum()
        .rename(columns={"price": "Revenue"})
        .sort_values("month")
    )

    st.line_chart(
        monthly_revenue.set_index("month")["Revenue"]
    )
else:
    st.info("No product sales found for these filters.")

# -------------------------------
# 7. Order status distribution
# -------------------------------
left, right = st.columns(2)

with left:
    st.subheader("📦 Order Status Distribution")

    status_counts = (
        filtered_orders["order_status"]
        .value_counts()
        .rename_axis("Status")
        .to_frame("Orders")
    )

    st.bar_chart(status_counts)

with right:
    st.subheader("🏆 Top 10 Product Categories")

    category_items = filtered_items.merge(
        products[["product_id", "category_display"]],
        on="product_id",
        how="left"
    )

    category_revenue = (
        category_items.groupby("category_display")["price"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .sort_values()
    )

    if not category_revenue.empty:
        st.bar_chart(category_revenue)
    else:
        st.info("No category data available.")

# -------------------------------
# 8. Customer review analysis
# -------------------------------
# -------------------------------
# Business Performance KPIs
# -------------------------------
st.subheader("📦 Delivery & Customer Retention")

delivered_data = orders[
    orders["order_status"] == "delivered"
].copy()

delivered_data = delivered_data.dropna(
    subset=[
        "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ]
)

late_deliveries = (
    delivered_data["order_delivered_customer_date"]
    > delivered_data["order_estimated_delivery_date"]
).sum()

total_deliveries = len(delivered_data)

late_delivery_rate = (
    late_deliveries / total_deliveries * 100
    if total_deliveries > 0 else 0
)


orders_with_customers = orders.merge(
    customers[["customer_id", "customer_unique_id"]],
    on="customer_id",
    how="left"
)

customer_orders = (
    orders_with_customers
    .groupby("customer_unique_id")["order_id"]
    .nunique()
)

repeat_customers = (customer_orders > 1).sum()
total_customers = customer_orders.count()

repeat_customer_rate = (
    repeat_customers / total_customers * 100
    if total_customers > 0 else 0
)

kpi1, kpi2 = st.columns(2)

kpi1.metric(
    "Late Delivery Rate",
    f"{late_delivery_rate:.2f}%"
)

kpi2.metric(
    "Repeat Customer Rate",
    f"{repeat_customer_rate:.2f}%"
)

st.divider()

# -------------------------------
# 9. Delivery Performance vs Customer Satisfaction
# -------------------------------
st.divider()
st.subheader("🚚 Delivery Performance vs Customer Satisfaction")

delivery_reviews = orders[
    orders["order_status"] == "delivered"
][[
    "order_id",
    "order_delivered_customer_date",
    "order_estimated_delivery_date"
]].copy()

delivery_reviews = delivery_reviews.dropna(
    subset=[
        "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ]
)

delivery_reviews["delivery_status"] = (
    delivery_reviews["order_delivered_customer_date"]
    <= delivery_reviews["order_estimated_delivery_date"]
).map({
    True: "On Time",
    False: "Late"
})

delivery_reviews = delivery_reviews.merge(
    reviews[["order_id", "review_score"]],
    on="order_id",
    how="inner"
)

delivery_score = (
    delivery_reviews.groupby("delivery_status")["review_score"]
    .mean()
    .reindex(["On Time", "Late"])
    .dropna()
)

if not delivery_score.empty:
    st.bar_chart(
        delivery_score.rename("Average Review Score"),
        y_label="Average score (out of 5)"
    )

    for status, score in delivery_score.items():
        st.write(f"**{status}:** {score:.2f} / 5")

    st.info(
        "Compare the average review scores to understand how delivery "
        "performance is associated with customer satisfaction. "
        "This comparison shows an association, not proof of causation."
    )
else:
    st.warning("No matching delivery and review data was found.")
st.subheader("⭐ Customer Review Scores")

if "review_score" in reviews.columns:
    review_counts = (
        reviews["review_score"]
        .dropna()
        .value_counts()
        .sort_index()
    )

    st.bar_chart(
        review_counts.rename_axis("Rating").to_frame("Reviews")
    )

    average_review = reviews["review_score"].mean()

    review_col1, review_col2 = st.columns(2)
    review_col1.metric(
        "Average Review Score",
        f"{average_review:.2f} / 5"
    )

    positive_reviews = (
        reviews["review_score"].between(4, 5).mean() * 100
    )

    review_col2.metric(
        "4–5 Star Reviews",
        f"{positive_reviews:.1f}%"
    )
else:
    st.info("Review score column was not found.")

st.divider()

# -------------------------------
# Business Insights & Recommendations
# -------------------------------
st.divider()
st.header("💡 Business Insights & Recommendations")

with st.expander("🚚 Delivery Performance", expanded=True):
    st.write(
        "Finding: Late deliveries have an average review score of 2.57/5, "
        "compared with 4.29/5 for on-time deliveries."
    )
    st.write(
        "Recommendation: Investigate delayed orders, review seller dispatch "
        "times, and improve delivery tracking and customer communication."
    )

with st.expander("🔁 Customer Retention"):
    st.write(
        "Finding: The repeat-customer rate is 3.12% in the analyzed dataset."
    )
    st.write(
        "Recommendation: Investigate repeat-purchase behavior and test "
        "loyalty offers or post-purchase engagement campaigns."
    )

with st.expander("🏆 Product Category Performance"):
    st.write(
        "Finding: Health & Beauty is the highest-revenue category in the "
        "current analysis."
    )
    st.write(
        "Recommendation: Review category-level demand, stock availability, "
        "profit margins, and promotional performance before allocating "
        "additional resources."
    )
st.caption("Cart2Insights | E-Commerce Data Analytics Project")
