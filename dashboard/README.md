# Dashboard

The Tableau Public workbook (`.twbx`) and dashboard screenshots land in
this folder once the dashboard is published. The workbook is built by
hand from the four CSVs in [`exports/`](../exports/) (written by
`make export`); sheets, parameters, axes and quadrant rules are
documented in
[`docs/07_assumptions_limitations.md`](../docs/07_assumptions_limitations.md)
§2.1.

## Logic that lives in Tableau, not dbt

Disclosed because it is not covered by dbt tests:

- Product name labels: a CASE on `hs6_code`.
- The H5 to H6 successor mapping for the supplier and trend sheets: a
  CASE mapping the six HS2022 successors (854141, 854142, 854143, 854149;
  854151, 854159) to their canonical products 854140 and 854150, because
  those two sheets key on `canonical_product_id` while the 2x2 is picked
  by HS6 code.
- The Quadrant calculation (docs/07 §2.1): Distance sensitive when the
  risk-set exposure at 100km and at 300km fall on opposite sides of the
  exposure line; otherwise Buffer stock + second supplier, Qualify second
  supplier, Hold buffer stock or Monitor by HHI and exposure against
  their lines.
