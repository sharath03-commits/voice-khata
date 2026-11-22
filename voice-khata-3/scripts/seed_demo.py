"""Fill the ledger with demo customers and entries for a judging demo.

Usage (from the backend folder):  python ../scripts/seed_demo.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ledger import Ledger  # noqa: E402

db = os.getenv("VK_DB", os.path.join(os.path.dirname(__file__), "..", "backend", "voice_khata.db"))
L = Ledger(db)
if L.list_customers():
    print("Ledger already has customers; delete backend/voice_khata.db to reseed."); sys.exit()
ramesh = L.add_customer("Ramesh")
lakshmi = L.add_customer("Lakshmi")
suresh = L.add_customer("Suresh", tag="tea stall")
manju = L.add_customer("ಮಂಜುನಾಥ್")
anil_a = L.add_customer("Anil", tag="doodh wala")
anil_b = L.add_customer("Anil", tag="school teacher")
for c, k, a, t in [
    (lakshmi, "credit", 125000, "Lakshmi 1250 udhaar"),
    (suresh, "credit", 18000, "Suresh ka 180 udhaar"),
    (manju, "credit", 56000, "ಮಂಜುನಾಥ್ 560 ಉದ್ರಿ"),
    (manju, "payment", 20000, "ಮಂಜುನಾಥ್ 200 ಕೊಟ್ಟರು"),
    (anil_a, "credit", 9000, "Anil 90 udhaar"),
    (anil_b, "credit", 41000, "Anil 410 credit"),
]:
    L.add_transaction(c["id"], k, a, transcript=t, source="seed")
print("Seeded", len(L.list_customers()), "customers. Ramesh is left at zero for the live demo.")
