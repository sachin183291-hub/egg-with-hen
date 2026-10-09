from datetime import datetime, timedelta
import random
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.database.models import (
    User, Farm, Shed, Zone, Row, Cage,
    HenPopulation, EggProduction, FinancialRecord,
    Anomaly, Alert, ThermalRecord, AttendanceRecord
)
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_poultry_data():
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Farm).count() > 0:
            print("Poultry data already seeded.")
            return

        print("Seeding DEMO poultry farm data...")
        admin_user = db.query(User).filter(User.role == "SUPER_ADMIN").first()
        if not admin_user:
            admin_user = db.query(User).first() # Fallback to any user
        if not admin_user:
            print("No users found. Cannot link records to a user.")
            return

        # 1. Farm Structure
        farm = Farm(name="Main Poultry Hub", location="North Valley")
        db.add(farm)
        db.commit()

        shed1 = Shed(farm_id=farm.id, name="Shed A - Layers")
        shed2 = Shed(farm_id=farm.id, name="Shed B - Broilers")
        db.add_all([shed1, shed2])
        db.commit()

        z1 = Zone(shed_id=shed1.id, name="Zone 1 - East")
        z2 = Zone(shed_id=shed1.id, name="Zone 2 - West")
        db.add_all([z1, z2])
        db.commit()

        for z in [z1, z2]:
            r1 = Row(zone_id=z.id, name="Row 1")
            r2 = Row(zone_id=z.id, name="Row 2")
            db.add_all([r1, r2])
            db.commit()
            
            for r in [r1, r2]:
                cages = [Cage(row_id=r.id, name=f"Cage {i}", capacity=10) for i in range(1, 6)]
                db.add_all(cages)
        db.commit()

        # 2. Historical Data (Last 30 days)
        now = datetime.utcnow()
        for i in range(30, -1, -1):
            d = now - timedelta(days=i)
            # Population & Eggs
            for z in [z1, z2]:
                hens = random.randint(480, 500)
                eggs = int(hens * random.uniform(0.85, 0.95))
                db.add(HenPopulation(zone_id=z.id, date=d, total_hens=hens, visible_hens=hens-5, unique_hens=hens, source="DEMO"))
                db.add(EggProduction(zone_id=z.id, date=d, eggs_produced=eggs, eggs_sold=int(eggs * 0.98)))
                
                # Thermal
                temp = random.uniform(22.0, 26.5)
                db.add(ThermalRecord(zone_id=z.id, temperature_celsius=temp, humidity_percent=random.uniform(50, 70), recorded_at=d))
            
            # Financials (Daily)
            db.add(FinancialRecord(date=d, type="EXPENSE", category="Feed", amount=random.uniform(100, 150), farm_id=farm.id, created_by=admin_user.id))
            db.add(FinancialRecord(date=d, type="REVENUE", category="Egg Sales", amount=random.uniform(400, 500), farm_id=farm.id, created_by=admin_user.id))

            # Attendance
            db.add(AttendanceRecord(date=d, user_id=admin_user.id, status="PRESENT"))

        # 3. Anomalies & Alerts
        db.add(Alert(title="Temperature Spike", message="Zone 1 temperature exceeded 27C", type="THERMAL", status="NEW"))
        db.add(Anomaly(type="Production Drop", zone_id=z1.id, observed_value=350, expected_value=450, severity="HIGH"))

        db.commit()
        print("Poultry DEMO data seeded successfully.")

    except Exception as e:
        print(f"Error seeding poultry data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_poultry_data()
