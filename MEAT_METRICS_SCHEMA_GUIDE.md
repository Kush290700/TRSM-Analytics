# Meat Metrics Schema Configuration Guide

## Quick Start: Adapt to Your Data Schema

This guide helps you configure the meat-specific metrics to match your actual database schema.

---

## 📋 Required Data Columns

### **Minimum Required** (Already in Use)
These columns are likely already in your fact table:

```
✓ Date              - Order/transaction date
✓ OrderId           - Unique order identifier
✓ CustomerId        - Customer identifier
✓ CustomerName      - Customer display name
✓ Revenue           - Revenue amount
✓ revenue_shipped   - Shipped revenue (preferred over Revenue)
✓ ProductName       - Product/SKU name
✓ QuantityShipped   - Units shipped
```

### **Optional for Enhanced Meat Metrics**
Add these columns to unlock full meat industry features:

```
○ ProteinCategory   - Beef, Pork, Chicken, Turkey, etc.
○ CategoryName      - Alternative to ProteinCategory
○ WeightLbs         - Product weight in pounds
○ ShipDate          - Actual ship date (for cold chain)
○ Temperature       - Storage/transport temperature (future)
○ PackSize          - Standard pack size
```

---

## 🔧 Schema Configuration

### **Option 1: Your Schema Matches Exactly**

✅ **No changes needed!** The code will work out of the box.

### **Option 2: Different Column Names**

Edit [`app/services/overview_query.py`](app/services/overview_query.py) line 724:

**Example 1: Your protein column is named `ProductCategory`**
```python
# Change line 724 from:
protein_cols = [c for c in df.columns if 'protein' in c.lower() or 'category' in c.lower()]

# To:
protein_cols = [c for c in df.columns if 'productcategory' in c.lower()]
```

**Example 2: Your weight column is `TotalWeight_Lbs`**
```python
# Change line 750 from:
weight_cols = [c for c in df.columns if 'weight' in c.lower()]

# To:
weight_cols = ['TotalWeight_Lbs']  # Exact column name
```

**Example 3: Multiple possible column names**
```python
# Use the first available column
protein_col = None
for candidate in ['ProteinType', 'MeatCategory', 'ProductCategory']:
    if candidate in df.columns:
        protein_col = candidate
        break
```

---

## 📊 Sample Data Mapping

### **Your Database Schema**
```sql
CREATE TABLE FactSales (
    TransactionDate DATE,              -- → Date
    OrderNumber VARCHAR(50),           -- → OrderId
    AccountID INT,                     -- → CustomerId
    AccountName VARCHAR(255),          -- → CustomerName
    NetRevenue DECIMAL(12,2),          -- → revenue_shipped
    ProductType VARCHAR(50),           -- → ProteinCategory
    UnitsShipped INT,                  -- → QuantityShipped
    WeightPounds DECIMAL(10,2),        -- → WeightLbs
    ShipmentDate DATE                  -- → ShipDate
)
```

### **Column Mapping Configuration**

Edit the `_meat_specific_metrics()` function:

```python
def _meat_specific_metrics(df: pd.DataFrame, revenue: pd.Series) -> Dict[str, Any]:
    """Calculate meat industry-specific KPIs."""

    # ============================================
    # CONFIGURE YOUR COLUMN NAMES HERE
    # ============================================

    # Protein/Category column (pick one that exists)
    PROTEIN_COLUMN = 'ProductType'  # Change to your column name

    # Weight column (pick one that exists)
    WEIGHT_COLUMN = 'WeightPounds'  # Change to your column name

    # Quantity column (pick one that exists)
    QUANTITY_COLUMN = 'UnitsShipped'  # Change to your column name

    # Product name column (pick one that exists)
    PRODUCT_COLUMN = 'ProductType'  # Change to your column name

    # Ship date column
    SHIP_DATE_COLUMN = 'ShipmentDate'  # Change to your column name

    # ============================================
    # Rest of function uses these constants
    # ============================================

    metrics = {
        "protein_mix": {},
        "pack_analysis": {},
        "yield_metrics": {},
        "cold_chain": {},
        "cut_performance": {},
    }

    if df is None or df.empty:
        return metrics

    # Protein mix breakdown
    if PROTEIN_COLUMN in df.columns:
        protein_revenue = revenue.groupby(df[PROTEIN_COLUMN]).sum()
        total = float(protein_revenue.sum())
        if total > 0:
            metrics["protein_mix"] = {
                str(k): {
                    "revenue": round(float(v), 2),
                    "share": round((float(v) / total) * 100, 1)
                }
                for k, v in protein_revenue.items() if pd.notna(k)
            }

    # Pack size analysis
    if QUANTITY_COLUMN in df.columns and 'OrderId' in df.columns:
        avg_pack_size = df.groupby('OrderId')[QUANTITY_COLUMN].sum().mean()
        metrics["pack_analysis"] = {
            "avg_units_per_order": round(float(avg_pack_size) if pd.notna(avg_pack_size) else 0, 2),
            "total_units": int(df[QUANTITY_COLUMN].sum()),
        }

    # Yield metrics
    if WEIGHT_COLUMN in df.columns and revenue.sum() > 0:
        total_weight = float(df[WEIGHT_COLUMN].sum())
        if total_weight > 0:
            revenue_per_lb = float(revenue.sum()) / total_weight
            metrics["yield_metrics"] = {
                "total_weight_lbs": round(total_weight, 2),
                "revenue_per_lb": round(revenue_per_lb, 2),
            }

    # Cold chain compliance
    if SHIP_DATE_COLUMN in df.columns and 'Date' in df.columns:
        ship_time = (pd.to_datetime(df[SHIP_DATE_COLUMN], errors='coerce') -
                     pd.to_datetime(df['Date'], errors='coerce')).dt.days
        fast_ship = (ship_time <= 2).sum() if not ship_time.isna().all() else 0
        total_tracked = int((~ship_time.isna()).sum())
        metrics["cold_chain"] = {
            "fast_ship_rate": round((fast_ship / total_tracked * 100) if total_tracked > 0 else 0, 1),
            "avg_ship_days": round(float(ship_time.mean()) if not ship_time.isna().all() else 0, 1),
        }

    # Top cuts/products
    if PRODUCT_COLUMN in df.columns:
        top_cuts = revenue.groupby(df[PRODUCT_COLUMN]).sum().nlargest(10)
        total_rev = float(revenue.sum())
        if total_rev > 0:
            metrics["cut_performance"] = {
                "top_cuts": [
                    {
                        "name": str(k),
                        "revenue": round(float(v), 2),
                        "share": round((float(v) / total_rev) * 100, 1)
                    }
                    for k, v in top_cuts.items() if pd.notna(k)
                ][:5]
            }

    return metrics
```

---

## 🎯 Testing Your Configuration

### **Step 1: Check Available Columns**

Run this in your Python console:

```python
import data_loader as loader
df = loader.get_fact_df()
print("Available columns:")
print(df.columns.tolist())
```

### **Step 2: Test Protein Mix**

```python
# Check if protein column exists
protein_cols = [c for c in df.columns if 'protein' in c.lower() or 'category' in c.lower()]
print(f"Protein columns found: {protein_cols}")

# Test grouping
if protein_cols:
    col = protein_cols[0]
    protein_breakdown = df.groupby(col)['revenue_shipped'].sum()
    print(protein_breakdown)
```

### **Step 3: Test Weight Metrics**

```python
# Check weight columns
weight_cols = [c for c in df.columns if 'weight' in c.lower()]
print(f"Weight columns found: {weight_cols}")

if weight_cols:
    total_weight = df[weight_cols[0]].sum()
    print(f"Total weight: {total_weight} lbs")
```

### **Step 4: Test Cold Chain**

```python
# Check date columns
if 'ShipDate' in df.columns:
    df['ship_time'] = (pd.to_datetime(df['ShipDate']) - pd.to_datetime(df['Date'])).dt.days
    fast_ship_pct = (df['ship_time'] <= 2).mean() * 100
    print(f"Fast ship rate: {fast_ship_pct:.1f}%")
```

---

## 🔍 Common Schema Scenarios

### **Scenario 1: No Protein Category Column**

**Solution A: Derive from Product Name**
```python
# Extract protein type from product name
def extract_protein(product_name):
    name_lower = str(product_name).lower()
    if 'beef' in name_lower: return 'Beef'
    elif 'pork' in name_lower: return 'Pork'
    elif 'chicken' in name_lower: return 'Chicken'
    elif 'turkey' in name_lower: return 'Turkey'
    else: return 'Other'

df['ProteinCategory'] = df['ProductName'].apply(extract_protein)
```

**Solution B: Use Existing Category Hierarchy**
```python
# If you have ProductCategory → SubCategory hierarchy
df['ProteinCategory'] = df['ProductCategory']  # Top-level category
```

**Solution C: Hide Protein Mix Section**
```javascript
// In overview.html or overview.js
$('#meatMetricsSection .protein-card').hide();
```

### **Scenario 2: No Weight Data**

**Solution A: Estimate from Quantity**
```python
# Assume average weight per unit
AVG_WEIGHT_PER_UNIT = 2.5  # pounds
df['WeightLbs'] = df['QuantityShipped'] * AVG_WEIGHT_PER_UNIT
```

**Solution B: Use Revenue as Proxy**
```python
# Revenue per lb metric becomes "Revenue per unit"
metrics["yield_metrics"] = {
    "total_units": int(df['QuantityShipped'].sum()),
    "revenue_per_unit": round(revenue.sum() / df['QuantityShipped'].sum(), 2),
}
```

**Solution C: Hide Yield Section**
```css
/* In overview.html <style> block */
#meatTotalWeight, #meatRevPerLb {
    display: none;
}
```

### **Scenario 3: No Ship Date (Cold Chain Not Tracked)**

**Solution A: Use Alternative Date**
```python
# Use InvoiceDate or ProcessDate as proxy
df['ShipDate'] = df['InvoiceDate']
```

**Solution B: Hide Cold Chain Metrics**
```javascript
// In overview.js
$('.bg-gradient-cold').parent().hide();
```

---

## 📝 Quick Reference: Common Column Names

### **Protein/Category**
- ✓ `ProteinCategory`
- ✓ `CategoryName`
- ✓ `ProductCategory`
- ✓ `ProteinType`
- ✓ `MeatType`
- ✓ `ItemCategory`

### **Weight**
- ✓ `WeightLbs`
- ✓ `WeightPounds`
- ✓ `TotalWeight`
- ✓ `NetWeight`
- ✓ `GrossWeight`
- ✓ `Weight_Lbs`

### **Quantity**
- ✓ `QuantityShipped`
- ✓ `QtyShipped`
- ✓ `UnitsShipped`
- ✓ `ItemCount`
- ✓ `Quantity`
- ✓ `Units`

### **Ship Date**
- ✓ `ShipDate`
- ✓ `ShipmentDate`
- ✓ `DeliveryDate`
- ✓ `FulfillmentDate`
- ✓ `ActualShipDate`

---

## 💡 Pro Tips

### **1. Use SQL Views for Data Preparation**

Create a view that standardizes column names:

```sql
CREATE VIEW vw_FactSales_Standardized AS
SELECT
    TransactionDate AS Date,
    OrderNumber AS OrderId,
    AccountID AS CustomerId,
    AccountName AS CustomerName,
    NetRevenue AS revenue_shipped,
    ProductType AS ProteinCategory,
    UnitsShipped AS QuantityShipped,
    WeightPounds AS WeightLbs,
    ShipmentDate AS ShipDate,
    ProductName
FROM FactSales;
```

Then update `data_loader.py` to query this view instead.

### **2. Add Data Quality Checks**

```python
# In your ETL process
def validate_meat_metrics_schema(df):
    """Ensure required columns exist."""
    required = ['Date', 'OrderId', 'CustomerId', 'revenue_shipped']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    recommended = ['ProteinCategory', 'WeightLbs', 'ShipDate']
    missing_recommended = [col for col in recommended if col not in df.columns]
    if missing_recommended:
        print(f"⚠️  Missing recommended columns: {missing_recommended}")
        print("   Some meat metrics may not be available.")

    return True
```

### **3. Environment Variable Configuration**

Use environment variables for column mapping:

```python
# In .env file
PROTEIN_COLUMN=ProductType
WEIGHT_COLUMN=WeightPounds
QUANTITY_COLUMN=UnitsShipped

# In overview_query.py
PROTEIN_COLUMN = os.getenv('PROTEIN_COLUMN', 'ProteinCategory')
WEIGHT_COLUMN = os.getenv('WEIGHT_COLUMN', 'WeightLbs')
```

---

## 🚨 Troubleshooting

### **Error: KeyError: 'ProteinCategory'**

**Cause**: Column doesn't exist in your data.

**Fix**:
1. Check column names with `df.columns.tolist()`
2. Update line 724 in `overview_query.py` to match your column
3. Or add the column to your data pipeline

### **Error: Protein mix chart shows "No data"**

**Cause**: Column exists but has null values or wrong data type.

**Fix**:
```python
# Check data quality
print(df['ProteinCategory'].value_counts())
print(df['ProteinCategory'].isna().sum())

# Clean data
df['ProteinCategory'] = df['ProteinCategory'].fillna('Unknown')
df['ProteinCategory'] = df['ProteinCategory'].astype(str)
```

### **Error: Division by zero in yield metrics**

**Cause**: Total weight is zero or null.

**Fix**: Add safety check (already in code at line 754):
```python
if total_weight > 0:
    revenue_per_lb = float(revenue.sum()) / total_weight
```

---

## 📞 Getting Help

If you encounter issues:

1. **Check the logs**: Look for `overview.meat_metrics.failed` entries
2. **Print debug info**: Add `print(df.columns.tolist())` in the function
3. **Test with sample data**: Create a small test dataset with known columns
4. **Refer to main docs**: See [OVERVIEW_ENHANCEMENTS.md](OVERVIEW_ENHANCEMENTS.md)

---

**Last Updated**: 2025-01-15
**Version**: 1.0.0
