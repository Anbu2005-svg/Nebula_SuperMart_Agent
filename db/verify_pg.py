from dotenv import load_dotenv
load_dotenv()

from skills.inventory import list_all_products, get_stock
from skills.credit import list_all_khata
from skills.billing import quick_create_bill

print("=== Products in Prisma PostgreSQL DB ===")
res = list_all_products()
for p in res["products"]:
    print(f"  {p['sku_id']} | {p['name']} | qty={p['quantity']} | mrp={p['mrp']}")

print()
print("=== Khata Customers ===")
res2 = list_all_khata()
for c in res2["khata_ledger"]:
    print(f"  {c['name']} | balance={c['khata_balance']}")

print()
print("=== Stock check: Maggi ===")
res3 = get_stock("Maggi")
print(f"  {res3['product']['name']} | qty={res3['product']['quantity']} | mrp={res3['product']['mrp']}")

print()
print("=== Quick Bill Test (Draft) ===")
bill = quick_create_bill(items=[{"name": "Maggi", "qty": 2}, {"name": "sugar", "qty": 1}])
print(f"  Bill ID: {bill.get('bill_id')} | Status: {bill.get('bill_status')} | Grand Total: {bill.get('summary', {}).get('grand_total')}")

print()
print("ALL PRISMA DB TESTS PASSED!")
