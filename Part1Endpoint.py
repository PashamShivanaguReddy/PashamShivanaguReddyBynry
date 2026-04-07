from decimal import Decimal, InvalidOperation
from flask import request, jsonify
from sqlalchemy.exc import IntegrityError

@app.route("/api/products", methods=["POST"])
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    # Required product fields
    required = ["name", "sku", "price"]
    missing = [f for f in required if data.get(f) in (None, "")]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    name = str(data["name"]).strip()
    sku = str(data["sku"]).strip().upper()

    # Money-safe parsing
    try:
        price = Decimal(str(data["price"]))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "price must be a valid decimal"}), 400
    if price < 0:
        return jsonify({"error": "price must be non-negative"}), 400

    # Optional fields
    warehouse_id = data.get("warehouse_id")
    initial_quantity = data.get("initial_quantity", 0)

    try:
        initial_quantity = int(initial_quantity)
    except (TypeError, ValueError):
        return jsonify({"error": "initial_quantity must be an integer"}), 400
    if initial_quantity < 0:
        return jsonify({"error": "initial_quantity must be non-negative"}), 400

    # If quantity is provided, warehouse is required
    if initial_quantity > 0 and warehouse_id is None:
        return jsonify({"error": "warehouse_id is required when initial_quantity > 0"}), 400

    # Validate warehouse if provided
    if warehouse_id is not None:
        warehouse = Warehouse.query.get(warehouse_id)
        if warehouse is None:
            return jsonify({"error": "warehouse_id does not exist"}), 400

    try:
        # Single atomic transaction
        with db.session.begin():
            # Product is global across warehouses
            product = Product(
                name=name,
                sku=sku,
                price=price
            )
            db.session.add(product)
            db.session.flush()  # product.id available before inventory insert

            # Optional initial stock in one warehouse
            if warehouse_id is not None:
                inventory = Inventory(
                    product_id=product.id,
                    warehouse_id=warehouse_id,
                    quantity=initial_quantity
                )
                db.session.add(inventory)

        return jsonify({
            "message": "Product created",
            "product_id": product.id
        }), 201

    except IntegrityError as exc:
        db.session.rollback()
        err = str(getattr(exc, "orig", exc)).lower()
        if "sku" in err and ("unique" in err or "duplicate" in err):
            return jsonify({"error": "SKU already exists"}), 409
        return jsonify({"error": "Database integrity error"}), 400

    except Exception:
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500
