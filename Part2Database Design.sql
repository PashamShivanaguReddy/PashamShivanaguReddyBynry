
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE warehouses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    address_line1   TEXT,
    address_line2   TEXT,
    city            TEXT,
    state_region    TEXT,
    postal_code     TEXT,
    country_code    CHAR(2),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, code),
    UNIQUE (id, company_id)
);

-- Product catalog per company
CREATE TABLE products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    sku                 TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    product_type        TEXT NOT NULL DEFAULT 'stock_item', -- stock_item | bundle | service
    unit_of_measure     TEXT NOT NULL DEFAULT 'ea',
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, sku),
    UNIQUE (id, company_id),
    CHECK (product_type IN ('stock_item', 'bundle', 'service'))
);

-- Current on-hand quantity by product and warehouse
CREATE TABLE inventory_balances (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    warehouse_id        UUID NOT NULL,
    product_id          UUID NOT NULL,
    quantity_on_hand    NUMERIC(18,4) NOT NULL DEFAULT 0,
    quantity_reserved   NUMERIC(18,4) NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (company_id, warehouse_id, product_id),
    FOREIGN KEY (warehouse_id, company_id)
        REFERENCES warehouses(id, company_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id, company_id)
        REFERENCES products(id, company_id) ON DELETE CASCADE,
    CHECK (quantity_reserved >= 0)
);

-- Immutable audit log of every inventory change
CREATE TABLE inventory_ledger (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    warehouse_id            UUID NOT NULL,
    product_id              UUID NOT NULL,

    change_type             TEXT NOT NULL,  -- receipt | shipment | adjustment | transfer_in | transfer_out | bundle_build | bundle_break
    quantity_delta          NUMERIC(18,4) NOT NULL,  -- positive or negative
    quantity_before         NUMERIC(18,4),
    quantity_after          NUMERIC(18,4),

    reference_type          TEXT,  -- purchase_order | sales_order | transfer | manual_adjustment | bundle_op
    reference_id            UUID,
    reason_code             TEXT,
    note                    TEXT,
    actor_user_id           UUID, -- nullable if system-generated

    FOREIGN KEY (warehouse_id, company_id)
        REFERENCES warehouses(id, company_id) ON DELETE RESTRICT,
    FOREIGN KEY (product_id, company_id)
        REFERENCES products(id, company_id) ON DELETE RESTRICT,
    CHECK (change_type IN ('receipt','shipment','adjustment','transfer_in','transfer_out','bundle_build','bundle_break'))
);

-- Suppliers are typically company-specific relationships
CREATE TABLE suppliers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    supplier_code       TEXT,
    name                TEXT NOT NULL,
    email               TEXT,
    phone               TEXT,
    payment_terms       TEXT,
    lead_time_days      INTEGER,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, name),
    UNIQUE (id, company_id)
);

-- Supplier-product terms
CREATE TABLE supplier_products (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    supplier_id             UUID NOT NULL,
    product_id              UUID NOT NULL,
    supplier_sku            TEXT,
    unit_cost               NUMERIC(18,4),
    currency_code           CHAR(3) DEFAULT 'USD',
    min_order_qty           NUMERIC(18,4),
    lead_time_days          INTEGER,
    is_preferred            BOOLEAN NOT NULL DEFAULT false,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (company_id, supplier_id, product_id),
    FOREIGN KEY (supplier_id, company_id)
        REFERENCES suppliers(id, company_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id, company_id)
        REFERENCES products(id, company_id) ON DELETE CASCADE
);

-- Bundle composition: bundle product contains component products
CREATE TABLE bundle_components (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    bundle_product_id       UUID NOT NULL,
    component_product_id    UUID NOT NULL,
    component_qty           NUMERIC(18,4) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (company_id, bundle_product_id, component_product_id),
    FOREIGN KEY (bundle_product_id, company_id)
        REFERENCES products(id, company_id) ON DELETE CASCADE,
    FOREIGN KEY (component_product_id, company_id)
        REFERENCES products(id, company_id) ON DELETE RESTRICT,
    CHECK (component_qty > 0),
    CHECK (bundle_product_id <> component_product_id)
);

-- Helpful indexes
CREATE INDEX idx_warehouses_company ON warehouses(company_id);
CREATE INDEX idx_products_company ON products(company_id);
CREATE INDEX idx_inventory_balances_product ON inventory_balances(company_id, product_id);
CREATE INDEX idx_inventory_balances_warehouse ON inventory_balances(company_id, warehouse_id);

CREATE INDEX idx_inventory_ledger_company_time
    ON inventory_ledger(company_id, occurred_at DESC);
CREATE INDEX idx_inventory_ledger_product_time
    ON inventory_ledger(company_id, product_id, occurred_at DESC);
CREATE INDEX idx_inventory_ledger_wh_product_time
    ON inventory_ledger(company_id, warehouse_id, product_id, occurred_at DESC);

CREATE INDEX idx_supplier_products_product
    ON supplier_products(company_id, product_id);
CREATE INDEX idx_bundle_components_bundle
    ON bundle_components(company_id, bundle_product_id);
