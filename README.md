# Inventory Management System (Backend)

A robust, production-ready inventory management backend designed with strong data integrity, transactional safety, and scalability in mind.

---

## 🚀 Features

- Product management with global SKU uniqueness
- Multi-warehouse inventory support
- Inventory tracking per warehouse
- Transaction-safe operations
- Decimal-safe pricing (no float issues)
- Strong validation & error handling
- Audit-ready design with extensibility

---

## ⚠️ Issues Identified & Fixes Implemented

### 1. No Request/Body Validation
- **Impact:** Invalid JSON caused 500 errors
- **Fix:** Added validation for JSON structure and required fields

### 2. Unsafe Dictionary Access
- **Impact:** `KeyError` crashes for missing fields
- **Fix:** Safe extraction with validation and defaults

### 3. Incorrect Product-Warehouse Relationship
- **Impact:** Duplicate product entries per warehouse
- **Fix:** 
  - Product is global
  - Inventory handles warehouse-specific stock

### 4. SKU Uniqueness Issues
- **Impact:** Duplicate SKUs or DB crashes
- **Fix:** 
  - DB-level unique constraint
  - Graceful handling with `409 Conflict`

### 5. Unsafe Price Handling (Float)
- **Impact:** Precision errors
- **Fix:** Use `Decimal` + `NUMERIC` DB type

### 6. Non-Atomic DB Operations
- **Impact:** Partial writes (data inconsistency)
- **Fix:** Single transaction with rollback support

### 7. Missing Warehouse Validation
- **Impact:** Invalid foreign key references
- **Fix:** Validate warehouse existence before insert

### 8. Invalid Quantity Handling
- **Impact:** Negative or invalid stock values
- **Fix:** Enforce integer and `>= 0`

### 9. No Rollback Strategy
- **Impact:** Broken DB session on failure
- **Fix:** Try/catch with rollback

### 10. Weak API Responses
- **Impact:** Poor client usability
- **Fix:** Return `201 Created` with resource details

---

## 🧱 Data Model Constraints (Critical)

### Product Table
- `sku` → **UNIQUE**
- `price` → `NUMERIC(12,2)`
- Global entity (not tied to warehouse)

### Inventory Table
- Unique constraint → `(product_id, warehouse_id)`
- Foreign Keys:
  - `product_id → Product`
  - `warehouse_id → Warehouse`

---

## 🗄️ Database Design

### Key Design Decisions

1. **Multi-Tenant Safety**
   - `company_id` added to transactional tables

2. **Inventory Separation**
   - `inventory_balances` → current stock
   - `inventory_ledger` → full history (immutable)

3. **Composite Foreign Keys**
   - Enforces tenant isolation at DB level

4. **Decimal Precision**
   - `NUMERIC(18,4)` for quantities & costs

5. **Flexible Bundles**
   - Self-referencing product relationships

6. **Concurrency Safety**
   - Unique constraints on business keys

7. **Performance Optimization**
   - Time-based indexes for ledger queries

8. **Audit Compliance**
   - Immutable ledger design (no updates/deletes)

---

## ❓ Open Questions (Product Clarifications Needed)

- Is SKU uniqueness global or per company?
- Can inventory go negative?
- Do we support fractional quantities?
- Need batch/lot/expiry tracking?
- Inventory valuation method? (FIFO, Avg, etc.)
- Warehouse transfer model?
- Bundle stock deduction timing?
- Nested bundles allowed?
- Supplier scope (global vs company)?
- Purchase order workflow needed?
- Audit requirements (SOC2, GDPR)?
- Soft delete vs hard delete?
- Multi-currency support?
- Performance SLAs?

---

## ⚙️ API Design

### Assumptions

- Thresholds based on `product_type`
- Recent sales = last 30 days
- Alerts are warehouse-specific
- Supplier selection is deterministic fallback

---

### Edge Cases Handled

- Invalid `company_id` → `400`
- No sales → no alerts
- Missing supplier → null-safe response
- Non-stock products excluded
- Zero demand → no divide-by-zero errors
- Inactive entities ignored

---

### Why This Design Works

- Clear separation of concerns (Product vs Inventory)
- Scales across multiple warehouses
- Strong consistency with transactions
- Audit-ready with full history tracking
- Easy to extend (threshold configs, suppliers, etc.)

---

## 🛠️ Tech Stack

- Backend: Spring Boot / Flask (customizable)
- Database: PostgreSQL
- ORM: SQLAlchemy / JPA
- Data Types: Decimal / Numeric
- Version Control: Git + GitHub

---

## 📦 Setup Instructions

```bash
# Clone repository
git clone https://github.com/your-username/your-repo.git

# Navigate to project
cd your-repo

# Install dependencies
pip install -r requirements.txt   # or mvn install

# Run application
python app.py                     # or mvn spring-boot:run
