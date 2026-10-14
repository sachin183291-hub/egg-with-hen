from datetime import datetime, timedelta
import random
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.database.models import (
    User, Farm, Shed, Zone, Row, Cage,
    HenPopulation, EggProduction, FinancialRecord,
    Anomaly, Alert, ThermalRecord, AttendanceRecord, Forecast
)

def seed_poultry_data(force: bool = True):
    db = SessionLocal()
    try:
        if not force and db.query(Farm).count() > 0:
            print("[INFO] Poultry farm demo data already present. Skipping.")
            return

        if force:
            print("Purging previous poultry demo data for complete refresh...")
            db.query(Forecast).delete()
            db.query(ThermalRecord).delete()
            db.query(AttendanceRecord).delete()
            db.query(Alert).delete()
            db.query(Anomaly).delete()
            db.query(FinancialRecord).delete()
            db.query(EggProduction).delete()
            db.query(HenPopulation).delete()
            db.query(Cage).delete()
            db.query(Row).delete()
            db.query(Zone).delete()
            db.query(Shed).delete()
            db.query(Farm).delete()
            db.commit()

        print("Seeding rich, realistic enterprise poultry farm data...")
        admin_user = db.query(User).filter(User.role == "SUPER_ADMIN").first()
        if not admin_user:
            admin_user = db.query(User).first()
        admin_id = admin_user.id if admin_user else None

        # ─── 1. Farm Hierarchy ────────────────────────────────────────────────────────
        farm1 = Farm(name="KR Grand Poultry Complex", location="Namakkal Agri Corridor, Tamil Nadu")
        farm2 = Farm(name="KR Green Valley Hatchery", location="Coimbatore Belt, Tamil Nadu")
        db.add_all([farm1, farm2])
        db.commit()

        # Farm 1 Sheds
        shed1 = Shed(farm_id=farm1.id, name="Shed A - Commercial Layers (High Yield)")
        shed2 = Shed(farm_id=farm1.id, name="Shed B - Climate Controlled Aviary")
        shed3 = Shed(farm_id=farm1.id, name="Shed C - Breeder & Pullet Rearing")
        # Farm 2 Sheds
        shed4 = Shed(farm_id=farm2.id, name="Shed 1 - Organic Free-Range Shelter")
        shed5 = Shed(farm_id=farm2.id, name="Shed 2 - Automated Brooding Bay")
        db.add_all([shed1, shed2, shed3, shed4, shed5])
        db.commit()

        # Zones Configuration
        zones_config = [
            (shed1, [("Zone 1 - East Wing (Automated Conveyor)", 2450), ("Zone 2 - West Wing (Precision Nesting)", 2400)]),
            (shed2, [("Zone 3 - North Bay (Micro-Climate Alpha)", 2600), ("Zone 4 - South Bay (Eco-Aviary Grid)", 2550)]),
            (shed3, [("Zone 5 - Brooder Sector Alpha", 1850), ("Zone 6 - Pullet Maturation Sector", 1800)]),
            (shed4, [("Zone 7 - Pasture Indoor Range", 1200)]),
            (shed5, [("Zone 8 - Bio-Secured Nesting", 1200)]),
        ]

        all_zones = []
        for shed_obj, z_list in zones_config:
            for z_name, bird_target in z_list:
                z = Zone(shed_id=shed_obj.id, name=z_name)
                db.add(z)
                db.commit()
                all_zones.append((z, bird_target))

                # Create 3 Rows per Zone with 8 Cages each
                for r_idx in range(1, 4):
                    row = Row(zone_id=z.id, name=f"Row {r_idx}")
                    db.add(row)
                    db.commit()
                    cages = [
                        Cage(row_id=row.id, name=f"Cage Tier-{t}-{c_idx}", capacity=25)
                        for t in (1, 2)
                        for c_idx in range(1, 6)
                    ]
                    db.add_all(cages)
                db.commit()

        # ─── 2. Historical Sensor, Production & Population (Last 30 Days) ─────────────
        now = datetime.utcnow()
        print("Generating 30-day time series for all zones...")
        
        for i in range(30, -1, -1):
            d = now - timedelta(days=i)
            day_ratio = 1.0 + (0.05 * (30 - i) / 30) # slight upward trend

            for zone, base_hens in all_zones:
                # Add natural fluctuation
                variance = random.randint(-20, 20)
                current_hens = int(base_hens * day_ratio) + variance
                visible = current_hens - random.randint(2, 8)
                unique = current_hens
                
                # Laying rate: ~89% - 94%
                laying_efficiency = random.uniform(0.88, 0.94)
                eggs_today = int(current_hens * laying_efficiency)
                eggs_sold = int(eggs_today * random.uniform(0.96, 0.99))

                db.add(HenPopulation(
                    zone_id=zone.id,
                    date=d,
                    total_hens=current_hens,
                    visible_hens=visible,
                    unique_hens=unique,
                    source="AI_CAMERA_YOLOv8"
                ))
                db.add(EggProduction(
                    zone_id=zone.id,
                    date=d,
                    eggs_produced=eggs_today,
                    eggs_sold=eggs_sold
                ))

                # Thermal records: between 22.8°C and 26.2°C (zone 4 slightly warmer)
                base_temp = 25.8 if "Zone 4" in zone.name else 23.8
                temp = round(base_temp + random.uniform(-1.0, 1.4), 1)
                humidity = round(random.uniform(55.0, 68.0), 1)

                db.add(ThermalRecord(
                    zone_id=zone.id,
                    temperature_celsius=temp,
                    humidity_percent=humidity,
                    recorded_at=d
                ))

            # ─── Financial Records (Daily distribution in INR ₹) ───────────────────────────────
            # Revenue items (in INR)
            daily_table_eggs_rev = random.uniform(82000.0, 95000.0)
            daily_premium_rev = random.uniform(18000.0, 26000.0)
            db.add(FinancialRecord(date=d, type="REVENUE", category="Table Egg Commercial Sales", amount=round(daily_table_eggs_rev, 2), description="Direct distributor dispatch", farm_id=farm1.id, created_by=admin_id))
            db.add(FinancialRecord(date=d, type="REVENUE", category="Grade-AA Jumbo Egg Sales", amount=round(daily_premium_rev, 2), description="Premium supermarket batch", farm_id=farm1.id, created_by=admin_id))

            if i % 5 == 0:
                db.add(FinancialRecord(date=d, type="REVENUE", category="Organic Compost Fertilizer", amount=round(random.uniform(8500.0, 14200.0), 2), description="Processed poultry manure to organic tea estates", farm_id=farm1.id, created_by=admin_id))

            if i % 14 == 0:
                db.add(FinancialRecord(date=d, type="REVENUE", category="Spent Hen Cull Processing", amount=round(random.uniform(32000.0, 48000.0), 2), description="End-of-cycle flock rotation", farm_id=farm2.id, created_by=admin_id))

            # Expense items (in INR)
            daily_feed_exp = random.uniform(42000.0, 52000.0)
            daily_power_exp = random.uniform(8000.0, 12000.0)
            db.add(FinancialRecord(date=d, type="EXPENSE", category="Organic Layer Feed Mash", amount=round(daily_feed_exp, 2), description="Soya & Maize fortified diet batch", farm_id=farm1.id, created_by=admin_id))
            db.add(FinancialRecord(date=d, type="EXPENSE", category="Electricity & Automated Conveyors", amount=round(daily_power_exp, 2), description="Power grid & generator backup", farm_id=farm1.id, created_by=admin_id))

            if i % 3 == 0:
                db.add(FinancialRecord(date=d, type="EXPENSE", category="Biosecurity & Veterinary Care", amount=round(random.uniform(5500.0, 9500.0), 2), description="Electrolyte supplements & water sanitizers", farm_id=farm1.id, created_by=admin_id))
            if i % 7 == 0:
                db.add(FinancialRecord(date=d, type="EXPENSE", category="Labor & Farm Technician Wages", amount=round(random.uniform(28000.0, 36000.0), 2), description="Weekly shift payroll", farm_id=farm1.id, created_by=admin_id))
                db.add(FinancialRecord(date=d, type="EXPENSE", category="Packaging & Egg Trays", amount=round(random.uniform(8000.0, 14000.0), 2), description="Biodegradable pulp molded trays", farm_id=farm1.id, created_by=admin_id))

            # Attendance
            if admin_id:
                db.add(AttendanceRecord(date=d, user_id=admin_id, status="PRESENT"))

        db.commit()

        # ─── 3. Action Center: Rich Alerts ────────────────────────────────────────────
        print("Populating actionable enterprise alerts...")
        z_sample1 = all_zones[3][0] # Zone 4
        z_sample2 = all_zones[0][0] # Zone 1
        z_sample3 = all_zones[4][0] # Zone 5
        z_sample4 = all_zones[2][0] # Zone 3

        alerts_data = [
            Alert(
                title="Critical Thermal Excursion Detected",
                message="Zone 4 (South Bay) sensor logged 28.4°C exceeding optimal upper bound (26.5°C). Automated exhaust fan bank #3 was triggered.",
                type="CRITICAL",
                status="NEW",
                created_at=now - timedelta(minutes=14)
            ),
            Alert(
                title="Egg Conveyor Belt Jitter & Speed Deviation",
                message="Shed A conveyor belt motor current draw spiked +18% above nominal. Potential mechanical friction near inspection dock #2.",
                type="CRITICAL",
                status="NEW",
                created_at=now - timedelta(hours=1, minutes=20)
            ),
            Alert(
                title="Water Dispenser Flow Rate Drop",
                message="Zone 5 (Brooder Alpha) nipple drinker line 2 flow rate measured 8.2 L/min (Expected: 12.0 L/min). Pressure regulator check required.",
                type="WARNING",
                status="NEW",
                created_at=now - timedelta(hours=3, minutes=45)
            ),
            Alert(
                title="Feed Hopper Reserve Below 15%",
                message="Shed B automated feed silo level reached 12.4%. Automatic refill schedule queued for 06:00 AM dispatch.",
                type="WARNING",
                status="NEW",
                created_at=now - timedelta(hours=5)
            ),
            Alert(
                title="Ammonia (NH3) Vapor Level Elevation",
                message="Zone 3 sensor registered 18.2 ppm NH3. Pre-emptive intake ventilation boosted to 85% to maintain threshold < 20 ppm.",
                type="WARNING",
                status="ACKNOWLEDGED",
                created_at=now - timedelta(hours=8)
            ),
            Alert(
                title="Automated Thermal Stabilization Completed",
                message="Zone 1 cooling pads rinsed and water circulation restored. Ambient temperature normalized to 23.6°C.",
                type="THERMAL",
                status="RESOLVED",
                created_at=now - timedelta(hours=16),
                resolved_at=now - timedelta(hours=15)
            ),
            Alert(
                title="AI Camera 04 Optical Re-alignment",
                message="Glare filter adjusted and optical lens auto-calibrated for high-accuracy hen comb color detection.",
                type="PRODUCTION",
                status="RESOLVED",
                created_at=now - timedelta(days=1),
                resolved_at=now - timedelta(days=1, hours=-1)
            ),
            Alert(
                title="Biosecurity Spray Gate Auto-Cycle Test",
                message="Vehicle disinfectant gate spray nozzles pressure tested. 100% nozzle integrity verified.",
                type="INFO",
                status="RESOLVED",
                created_at=now - timedelta(days=2),
                resolved_at=now - timedelta(days=2, hours=-1)
            ),
        ]
        db.add_all(alerts_data)
        db.commit()

        # ─── 4. Action Center: AI Operational Anomalies ───────────────────────────────
        print("Populating AI vision & IoT operational anomalies...")
        anomalies_data = [
            Anomaly(
                type="Sudden Laying Velocity Drop",
                zone_id=z_sample1.id,
                date=now - timedelta(hours=2),
                observed_value=412.0,
                expected_value=560.0,
                severity="HIGH",
                status="NEW",
                evidence="Computer vision detected reduced egg roll-out rate between 11:00 AM and 01:00 PM in Cage Row 2."
            ),
            Anomaly(
                type="Abnormal Hen Clustering Pattern",
                zone_id=z_sample2.id,
                date=now - timedelta(hours=4),
                observed_value=64.8,
                expected_value=22.0,
                severity="MEDIUM",
                status="NEW",
                evidence="64.8% of flock converged within East perimeter quadrant. Thermal scan reveals cool air draft from unlatched intake louver."
            ),
            Anomaly(
                type="Flock Feed Consumption Drift",
                zone_id=z_sample4.id,
                date=now - timedelta(hours=9),
                observed_value=108.5,
                expected_value=124.0,
                severity="MEDIUM",
                status="ACKNOWLEDGED",
                evidence="Weigh-feeder telemetry indicates 12.5% decrease in hourly mash intake. Mineral water balance test initiated."
            ),
            Anomaly(
                type="Egg Shell Micro-Crack Acoustic Signature",
                zone_id=z_sample1.id,
                date=now - timedelta(hours=18),
                observed_value=4.6,
                expected_value=1.1,
                severity="LOW",
                status="RESOLVED",
                evidence="Acoustic resonance analyzer identified 4.6% micro-fissure rate. Dietary calcium carbonate concentration adjusted +0.4%."
            ),
            Anomaly(
                type="Nighttime Roosting Vocalization Spike",
                zone_id=z_sample3.id,
                date=now - timedelta(days=1, hours=4),
                observed_value=54.2,
                expected_value=24.0,
                severity="HIGH",
                status="RESOLVED",
                evidence="Acoustic sensor flagged nocturnal noise spike at 02:14 AM. Perimeter infrared patrol confirmed minor rodent intrusion repelled by sonic deterrent."
            )
        ]
        db.add_all(anomalies_data)
        db.commit()

        # ─── 5. AI 7-Day Forecast Projections ─────────────────────────────────────────
        print("Generating 7-day forward predictions...")
        for day_offset in range(1, 8):
            target_d = now + timedelta(days=day_offset)
            predicted_eggs = round(13400 + (day_offset * 65) + random.randint(-80, 80), 0)
            db.add(Forecast(
                metric_type="EGG_PRODUCTION",
                target_date=target_d,
                predicted_value=predicted_eggs,
                confidence_lower=round(predicted_eggs * 0.96, 0),
                confidence_upper=round(predicted_eggs * 1.04, 0),
                created_at=now
            ))
            
            predicted_rev = round(predicted_eggs * 6.50, 2)
            db.add(Forecast(
                metric_type="REVENUE",
                target_date=target_d,
                predicted_value=predicted_rev,
                confidence_lower=round(predicted_rev * 0.95, 2),
                confidence_upper=round(predicted_rev * 1.05, 2),
                created_at=now
            ))

        db.commit()
        print(" Enterprise poultry farm database successfully seeded!")

    except Exception as e:
        print(f"Error seeding poultry data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_poultry_data(force=True)
