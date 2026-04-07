from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import Blueprint, jsonify, request
from sqlalchemy import func, and_, case
from sqlalchemy.orm import aliased

# Assumed SQLAlchemy models based on prior schema discussion
# Company(id)
# Warehouse(id, company_id, name, is_active)
# Product(id, company_id, name, sku, product_type, is_active)
# InventoryBalance(company_id, warehouse_id, product_id, quantity_on_hand)
# SalesOrder(id, company_id, warehouse_id, created_at, status)
# SalesOrderItem(id, order_id, product_id, quantity)
# Supplier(id, company_id, name, email, is_active)
# SupplierProduct(company_id, supplier_id, product_id, is_preferred)

api = Blueprint("api", __name__)

# Assumption: thresholds are configurable by product_type.
# In production, this should come from a DB table or feature config service.
LOW_STOCK_THRESHOLDS = {
    "stock_item": Decimal("20"),
    "bundle": Decimal("10"),
    "service": Decimal("0"),  # non-stock product type
}

# Assumption: "recent sales activity" means at least one completed/paid/shipped sale in last 30 days.
RECENT_SALES_DAYS = 30

# Assumption: stockout estimate based on trailing 30-day daily average sales per warehouse+product.
STOCKOUT_WINDOW_DAYS = 30

# Reasonable cap to avoid accidental huge responses.
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def parse_uuid(value: str):
    try:
        return UUID(str(value))
    except Exception:
        return None


def parse_positive_int(value, default_value):
    try:
        if value is None:
            return default_value
        parsed = int(value)
        return parsed if parsed > 0 else default_value
    except Exception:
        return default_value


@api.route("/api/companies/<company_id>/alerts/low-stock", methods=["GET"])
def get_low_stock_alerts(company_id):
    # Optional query params for operational flexibility
    limit = min(parse_positive_int(request.args.get("limit"), DEFAULT_LIMIT), MAX_LIMIT)
    offset = max(parse_positive_int(request.args.get("offset"), 0), 0)

    company_uuid = parse_uuid(company_id)
    if not company_uuid:
        return jsonify({"error": "Invalid company_id format"}), 400

    # Optional override to tune "recent sales" lookback without code changes
    recent_days = parse_positive_int(request.args.get("recent_days"), RECENT_SALES_DAYS)
    stockout_window_days = parse_positive_int(request.args.get("stockout_window_days"), STOCKOUT_WINDOW_DAYS)

    now_utc = datetime.now(timezone.utc)
    recent_cutoff = now_utc - timedelta(days=recent_days)
    stockout_cutoff = now_utc - timedelta(days=stockout_window_days)

    try:
        # Subquery A: products with recent sales activity per warehouse+product
        # Filters to real demand signals for the exact warehouse where stock is evaluated.
        recent_sales_subq = (
            db.session.query(
                SalesOrder.company_id.label("company_id"),
                SalesOrder.warehouse_id.label("warehouse_id"),
                SalesOrderItem.product_id.label("product_id"),
                func.sum(SalesOrderItem.quantity).label("qty_sold_recent"),
            )
            .join(SalesOrderItem, SalesOrderItem.order_id == SalesOrder.id)
            .filter(
                SalesOrder.company_id == company_uuid,
                SalesOrder.created_at >= recent_cutoff,
                SalesOrder.status.in_(["paid", "shipped", "completed"]),
            )
            .group_by(
                SalesOrder.company_id,
                SalesOrder.warehouse_id,
                SalesOrderItem.product_id,
            )
            .subquery()
        )

        # Subquery B: best supplier per product
        # Preference order: preferred supplier first, else lowest supplier id as stable fallback.
        supplier_ranked = (
            db.session.query(
                SupplierProduct.company_id.label("company_id"),
                SupplierProduct.product_id.label("product_id"),
                Supplier.id.label("supplier_id"),
                Supplier.name.label("supplier_name"),
                Supplier.email.label("supplier_email"),
                func.row_number()
                .over(
                    partition_by=(SupplierProduct.company_id, SupplierProduct.product_id),
                    order_by=(
                        case((SupplierProduct.is_preferred.is_(True), 0), else_=1),
                        Supplier.id.asc(),
                    ),
                )
                .label("rn"),
            )
            .join(
                Supplier,
                and_(
                    Supplier.id == SupplierProduct.supplier_id,
                    Supplier.company_id == SupplierProduct.company_id,
                ),
            )
            .filter(
                SupplierProduct.company_id == company_uuid,
                Supplier.is_active.is_(True),
            )
            .subquery()
        )

        # Main query:
        # 1) start from inventory balances (warehouse granularity)
        # 2) require recent sales activity
        # 3) compare current stock against dynamic threshold by product_type
        # 4) include warehouse + supplier info
        query = (
            db.session.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                Product.product_type.label("product_type"),
                Warehouse.id.label("warehouse_id"),
                Warehouse.name.label("warehouse_name"),
                InventoryBalance.quantity_on_hand.label("current_stock"),
                recent_sales_subq.c.qty_sold_recent.label("qty_sold_recent"),
                supplier_ranked.c.supplier_id.label("supplier_id"),
                supplier_ranked.c.supplier_name.label("supplier_name"),
                supplier_ranked.c.supplier_email.label("supplier_email"),
            )
            .join(
                InventoryBalance,
                and_(
                    InventoryBalance.company_id == Product.company_id,
                    InventoryBalance.product_id == Product.id,
                ),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.id == InventoryBalance.warehouse_id,
                    Warehouse.company_id == InventoryBalance.company_id,
                ),
            )
            .join(
                recent_sales_subq,
                and_(
                    recent_sales_subq.c.company_id == InventoryBalance.company_id,
                    recent_sales_subq.c.warehouse_id == InventoryBalance.warehouse_id,
                    recent_sales_subq.c.product_id == InventoryBalance.product_id,
                ),
            )
            .outerjoin(
                supplier_ranked,
                and_(
                    supplier_ranked.c.company_id == Product.company_id,
                    supplier_ranked.c.product_id == Product.id,
                    supplier_ranked.c.rn == 1,
                ),
            )
            .filter(
                Product.company_id == company_uuid,
                Product.is_active.is_(True),
                Warehouse.is_active.is_(True),
            )
            .order_by(
                InventoryBalance.quantity_on_hand.asc(),
                Product.id.asc(),
                Warehouse.id.asc(),
            )
        )

        rows = query.all()

        alerts = []
        for row in rows:
            # Map threshold by product type with safe fallback
            threshold = LOW_STOCK_THRESHOLDS.get(row.product_type, Decimal("20"))

            # Ignore non-stock products by threshold policy
            if threshold <= 0:
                continue

            current_stock = Decimal(str(row.current_stock or 0))

            # Low-stock check
            if current_stock >= threshold:
                continue

            qty_sold_recent = Decimal(str(row.qty_sold_recent or 0))

            # Daily run-rate from trailing window.
            # If no recent quantity, stockout cannot be estimated reliably.
            daily_rate = qty_sold_recent / Decimal(str(stockout_window_days)) if qty_sold_recent > 0 else Decimal("0")

            if daily_rate > 0:
                days_until_stockout = int(current_stock / daily_rate)
            else:
                days_until_stockout = None

            alerts.append(
                {
                    "product_id": str(row.product_id),
                    "product_name": row.product_name,
                    "sku": row.sku,
                    "warehouse_id": str(row.warehouse_id),
                    "warehouse_name": row.warehouse_name,
                    "current_stock": float(current_stock),
                    "threshold": float(threshold),
                    "days_until_stockout": days_until_stockout,
                    "supplier": {
                        "id": str(row.supplier_id) if row.supplier_id else None,
                        "name": row.supplier_name,
                        "contact_email": row.supplier_email,
                    },
                }
            )

        # Pagination applied in memory after business-rule filtering.
        # For high volume, move threshold logic into SQL or materialized views.
        paged_alerts = alerts[offset : offset + limit]

        return (
            jsonify(
                {
                    "alerts": paged_alerts,
                    "total_alerts": len(alerts),
                }
            ),
            200,
        )

    except Exception:
        # Avoid leaking internals in API responses; log full exception server-side.
        return jsonify({"error": "Failed to fetch low-stock alerts"}), 500
