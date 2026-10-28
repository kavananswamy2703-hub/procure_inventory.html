from flask import Flask, request, jsonify, send_from_directory, Response
from pathlib import Path
import sqlite3, csv
from io import StringIO
from datetime import date

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "procurement_inventory.db"
FRONTEND_FILE = "FRONTEND_FILE.html"
app = Flask(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS vendors(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
          contact TEXT DEFAULT '', phone TEXT DEFAULT '', gstin TEXT DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS items(
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
          reorder_level INTEGER NOT NULL DEFAULT 5 CHECK(reorder_level>=0),
          unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost>=0), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchase_orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, po_number TEXT NOT NULL UNIQUE,
          vendor_id INTEGER, vendor_name TEXT NOT NULL, order_date TEXT NOT NULL,
          item_name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
          unit_price REAL NOT NULL CHECK(unit_price>=0), gst_rate REAL NOT NULL,
          subtotal REAL NOT NULL, gst_amount REAL NOT NULL, total REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL,
          FOREIGN KEY(vendor_id) REFERENCES vendors(id) ON DELETE SET NULL
        );
        """)

def err(message, status=400):
    return jsonify({"error": message}), status

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, FRONTEND_FILE)

@app.get("/api/health")
def health():
    return jsonify({"status":"ok","message":"Backend is running"})

@app.get("/api/dashboard")
def dashboard():
    with get_db() as c:
        counts = {
          "purchase_order_count": c.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0],
          "item_count": c.execute("SELECT COUNT(*) FROM items").fetchone()[0],
          "vendor_count": c.execute("SELECT COUNT(*) FROM vendors").fetchone()[0],
          "low_stock_count": c.execute("SELECT COUNT(*) FROM items WHERE quantity<=reorder_level").fetchone()[0]
        }
        sums = c.execute("SELECT COALESCE(SUM(subtotal),0) subtotal, COALESCE(SUM(gst_amount),0) gst_amount, COALESCE(SUM(total),0) total FROM purchase_orders").fetchone()
        counts.update({"subtotal":sums["subtotal"],"gst_amount":sums["gst_amount"],"order_total":sums["total"]})
        return jsonify(counts)

@app.get("/api/vendors")
def vendors_list():
    with get_db() as c: rows = c.execute("SELECT * FROM vendors ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/vendors")
def vendors_create():
    p = request.get_json(silent=True) or {}
    name = str(p.get("name","")).strip()
    contact = str(p.get("contact","")).strip()
    phone = str(p.get("phone","")).strip()
    gstin = str(p.get("gstin","")).strip().upper()
    if not name: return err("Vendor name is required.")
    if gstin and (len(gstin) != 15 or not gstin.isalnum()): return err("GSTIN must contain 15 letters and numbers.")
    if phone and (not phone.isdigit() or not 7 <= len(phone) <= 15): return err("Phone must contain 7 to 15 digits.")
    try:
        with get_db() as c:
            cur = c.execute("INSERT INTO vendors(name,contact,phone,gstin,created_at) VALUES(?,?,?,?,?)",
                            (name,contact,phone,gstin,date.today().isoformat()))
            row = c.execute("SELECT * FROM vendors WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError: return err("A vendor with this name already exists.",409)

@app.delete("/api/vendors/<int:rid>")
def vendors_delete(rid):
    with get_db() as c: cur = c.execute("DELETE FROM vendors WHERE id=?", (rid,))
    if not cur.rowcount: return err("Vendor not found.",404)
    return jsonify({"message":"Vendor deleted"})

@app.get("/api/items")
def items_list():
    with get_db() as c: rows = c.execute("SELECT * FROM items ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/items")
def items_create():
    p = request.get_json(silent=True) or {}
    name, code = str(p.get("name","")).strip(), str(p.get("code","")).strip().upper()
    if not name or not code: return err("Item name and code are required.")
    try:
        qty, reorder, price = int(p.get("quantity",0)), int(p.get("reorder_level",5)), float(p.get("unit_cost",0))
        if qty < 0 or reorder < 0 or price < 0: return err("Quantity, reorder level and cost cannot be negative.")
    except (ValueError,TypeError): return err("Quantity, reorder level and cost must be numeric.")
    try:
        with get_db() as c:
            cur = c.execute("INSERT INTO items(code,name,quantity,reorder_level,unit_cost,created_at) VALUES(?,?,?,?,?,?)",
                            (code,name,qty,reorder,price,date.today().isoformat()))
            row = c.execute("SELECT * FROM items WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)),201
    except sqlite3.IntegrityError: return err("That item code already exists.",409)

@app.patch("/api/items/<int:rid>")
def items_update(rid):
    p = request.get_json(silent=True) or {}
    allowed = {"name","code","quantity","reorder_level","unit_cost"}
    updates = {k:p[k] for k in allowed if k in p}
    if not updates: return err("No fields provided.")
    try:
        for key in ("quantity","reorder_level"):
            if key in updates:
                updates[key] = int(updates[key])
                if updates[key] < 0: return err(f"{key} cannot be negative.")
        if "unit_cost" in updates:
            updates["unit_cost"] = float(updates["unit_cost"])
            if updates["unit_cost"] < 0: return err("Unit cost cannot be negative.")
        if "code" in updates: updates["code"] = str(updates["code"]).strip().upper()
        if "name" in updates: updates["name"] = str(updates["name"]).strip()
    except (ValueError,TypeError): return err("Invalid field value.")
    try:
        with get_db() as c:
            c.execute("UPDATE items SET " + ", ".join(f"{k}=?" for k in updates) + " WHERE id=?", (*updates.values(),rid))
            row = c.execute("SELECT * FROM items WHERE id=?", (rid,)).fetchone()
        if row is None: return err("Item not found.",404)
        return jsonify(dict(row))
    except sqlite3.IntegrityError: return err("That item code already exists.",409)

@app.delete("/api/items/<int:rid>")
def items_delete(rid):
    with get_db() as c: cur = c.execute("DELETE FROM items WHERE id=?", (rid,))
    if not cur.rowcount: return err("Item not found.",404)
    return jsonify({"message":"Item deleted"})

@app.get("/api/orders")
def orders_list():
    with get_db() as c: rows = c.execute("SELECT * FROM purchase_orders ORDER BY id DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/orders")
def orders_create():
    p = request.get_json(silent=True) or {}
    vendor = str(p.get("vendor_name","")).strip()
    item = str(p.get("item_name","")).strip()
    order_date = str(p.get("order_date",date.today().isoformat())).strip()
    status = str(p.get("status","Pending")).strip()
    if not vendor or not item: return err("Vendor and item names are required.")
    if status not in {"Pending","Approved","Received"}: return err("Invalid order status.")
    try:
        qty, price, rate = int(p.get("quantity",0)), float(p.get("unit_price",0)), float(p.get("gst_rate",18))
        if qty <= 0 or price < 0 or rate not in {0,5,12,18,28}: return err("Enter a positive quantity, non-negative price and valid GST rate.")
    except (ValueError,TypeError): return err("Quantity, price or GST rate is invalid.")
    subtotal = round(qty*price,2); gst = round(subtotal*rate/100,2); total = round(subtotal+gst,2)
    with get_db() as c:
        vendor_row = c.execute("SELECT id FROM vendors WHERE lower(name)=lower(?)",(vendor,)).fetchone()
        cur = c.execute("""INSERT INTO purchase_orders
          (po_number,vendor_id,vendor_name,order_date,item_name,quantity,unit_price,gst_rate,subtotal,gst_amount,total,status,created_at)
          VALUES('TEMP',?,?,?,?,?,?,?,?,?,?,?,?)""",
          (vendor_row["id"] if vendor_row else None,vendor,order_date,item,qty,price,rate,subtotal,gst,total,status,date.today().isoformat()))
        po_number = f"PO-{date.today():%y%m%d}-{cur.lastrowid:05d}"
        c.execute("UPDATE purchase_orders SET po_number=? WHERE id=?",(po_number,cur.lastrowid))
        if status == "Received":
            stock = c.execute("SELECT id FROM items WHERE lower(name)=lower(?)",(item,)).fetchone()
            if stock: c.execute("UPDATE items SET quantity=quantity+? WHERE id=?",(qty,stock["id"]))
            else: c.execute("INSERT INTO items(code,name,quantity,reorder_level,unit_cost,created_at) VALUES(?,?,?,?,?,?)",
                            (f"AUTO-{cur.lastrowid:05d}",item,qty,5,price,date.today().isoformat()))
        row = c.execute("SELECT * FROM purchase_orders WHERE id=?",(cur.lastrowid,)).fetchone()
    return jsonify(dict(row)),201

@app.patch("/api/orders/<int:rid>")
def orders_update(rid):
    p = request.get_json(silent=True) or {}; status = p.get("status")
    if status not in {"Pending","Approved","Received"}: return err("Invalid order status.")
    with get_db() as c:
        row = c.execute("SELECT * FROM purchase_orders WHERE id=?",(rid,)).fetchone()
        if not row: return err("Order not found.",404)
        if row["status"] != "Received" and status == "Received":
            stock = c.execute("SELECT id FROM items WHERE lower(name)=lower(?)",(row["item_name"],)).fetchone()
            if stock: c.execute("UPDATE items SET quantity=quantity+? WHERE id=?",(row["quantity"],stock["id"]))
            else: c.execute("INSERT INTO items(code,name,quantity,reorder_level,unit_cost,created_at) VALUES(?,?,?,?,?,?)",
                            (f"AUTO-{rid:05d}",row["item_name"],row["quantity"],5,row["unit_price"],date.today().isoformat()))
        c.execute("UPDATE purchase_orders SET status=? WHERE id=?",(status,rid))
        updated = c.execute("SELECT * FROM purchase_orders WHERE id=?",(rid,)).fetchone()
    return jsonify(dict(updated))

@app.delete("/api/orders/<int:rid>")
def orders_delete(rid):
    with get_db() as c: cur = c.execute("DELETE FROM purchase_orders WHERE id=?",(rid,))
    if not cur.rowcount: return err("Order not found.",404)
    return jsonify({"message":"Order deleted"})

@app.get("/api/gst")
def gst_calculate():
    try:
        amount, rate = float(request.args.get("amount","0")), float(request.args.get("rate","18"))
        tx = request.args.get("type","intra")
        if amount < 0 or rate not in {0,5,12,18,28} or tx not in {"intra","inter"}: return err("Invalid amount, GST rate or transaction type.")
    except ValueError: return err("Amount and rate must be numbers.")
    gst = round(amount*rate/100,2)
    result = {"amount_before_gst":round(amount,2),"gst_rate":rate,"gst_amount":gst,"total":round(amount+gst,2)}
    if tx == "intra": result.update({"cgst":round(gst/2,2),"sgst":round(gst/2,2)})
    else: result["igst"] = gst
    return jsonify(result)

@app.get("/api/reports/purchase-orders.csv")
def orders_csv():
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(["PO Number","Vendor","Date","Item","Quantity","Unit Price","Subtotal","GST Rate","GST Amount","Total","Status"])
    with get_db() as c:
        rows = c.execute("SELECT po_number,vendor_name,order_date,item_name,quantity,unit_price,subtotal,gst_rate,gst_amount,total,status FROM purchase_orders ORDER BY id DESC").fetchall()
    writer.writerows([list(r) for r in rows])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=purchase-orders.csv"})



init_db()

if __name__ == "__main__":
    app.run(debug=True)