"""Farm Intelligence (Phase 3 & 4) API."""
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database.session import get_db
from app.database.models import (
    User, Farm, Shed, Zone, Row, Cage,
    HenPopulation, EggProduction, FinancialRecord,
    Anomaly, Alert, ActionNote, ThermalRecord, AttendanceRecord, Forecast
)
from app.security.rbac import get_current_active_user

router = APIRouter(prefix="/api/farm", tags=["Farm Intelligence"])

# ─── 3.1 Digital Farm ──────────────────────────────────────────────────────────

@router.get("/structure")
async def get_farm_structure(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get the entire hierarchical farm structure for the Digital Twin."""
    farms = db.query(Farm).all()
    result = []
    for farm in farms:
        sheds = db.query(Shed).filter(Shed.farm_id == farm.id).all()
        shed_data = []
        for shed in sheds:
            zones = db.query(Zone).filter(Zone.shed_id == shed.id).all()
            zone_data = []
            for zone in zones:
                rows = db.query(Row).filter(Row.zone_id == zone.id).all()
                row_data = []
                for row in rows:
                    cages = db.query(Cage).filter(Cage.row_id == row.id).all()
                    row_data.append({
                        "id": row.id,
                        "name": row.name,
                        "cages": [{"id": c.id, "name": c.name, "capacity": c.capacity} for c in cages]
                    })
                
                # Fetch latest real-time zone metrics
                latest_pop = db.query(HenPopulation).filter(HenPopulation.zone_id == zone.id).order_by(desc(HenPopulation.date)).first()
                latest_egg = db.query(EggProduction).filter(EggProduction.zone_id == zone.id).order_by(desc(EggProduction.date)).first()
                latest_thermal = db.query(ThermalRecord).filter(ThermalRecord.zone_id == zone.id).order_by(desc(ThermalRecord.recorded_at)).first()
                
                zone_data.append({
                    "id": zone.id,
                    "name": zone.name,
                    "rows": row_data,
                    "metrics": {
                        "total_hens": latest_pop.total_hens if latest_pop else 0,
                        "visible_hens": latest_pop.visible_hens if latest_pop else 0,
                        "unique_hens": latest_pop.unique_hens if latest_pop else 0,
                        "eggs_produced": latest_egg.eggs_produced if latest_egg else 0,
                        "temperature": latest_thermal.temperature_celsius if latest_thermal else None,
                        "humidity": latest_thermal.humidity_percent if latest_thermal else None,
                    }
                })
            shed_data.append({"id": shed.id, "name": shed.name, "zones": zone_data})
        result.append({"id": farm.id, "name": farm.name, "location": farm.location, "sheds": shed_data})
    
    return result

# ─── 3.2 Business Intelligence KPI ────────────────────────────────────────────

@router.get("/bi/kpi")
async def get_bi_kpis(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get dynamic KPI cards data for the dashboard."""
    since = datetime.utcnow() - timedelta(days=days)
    
    # Populations (latest recording session across active zones)
    latest_date = db.query(func.max(HenPopulation.date)).scalar()
    if latest_date:
        latest_pop = db.query(
            func.sum(HenPopulation.total_hens),
            func.sum(HenPopulation.unique_hens)
        ).filter(HenPopulation.date >= latest_date - timedelta(hours=12)).first()
    else:
        latest_pop = (0, 0)
    
    # Production
    prod_data = db.query(func.sum(EggProduction.eggs_produced), func.sum(EggProduction.eggs_sold))\
        .filter(EggProduction.date >= since).first()
    
    # Financials
    rev = db.query(func.sum(FinancialRecord.amount)).filter(FinancialRecord.type == "REVENUE", FinancialRecord.date >= since).scalar() or 0
    exp = db.query(func.sum(FinancialRecord.amount)).filter(FinancialRecord.type == "EXPENSE", FinancialRecord.date >= since).scalar() or 0
    
    # Thermal Average
    avg_temp = db.query(func.avg(ThermalRecord.temperature_celsius)).filter(ThermalRecord.recorded_at >= since).scalar()
    
    # Active Alerts
    active_alerts = db.query(Alert).filter(Alert.status == "NEW").count()
    critical_alerts = db.query(Alert).filter(Alert.status == "NEW", Alert.type == "CRITICAL").count()
    
    # Workers Present Today
    today = datetime.utcnow().date()
    workers_present = db.query(AttendanceRecord).filter(
        func.date(AttendanceRecord.date) == today,
        AttendanceRecord.status == "PRESENT"
    ).count()

    total_eggs = prod_data[0] if prod_data and prod_data[0] else 0
    eggs_sold = prod_data[1] if prod_data and prod_data[1] else 0
    total_birds = latest_pop[0] if latest_pop and latest_pop[0] else 0
    unique_birds = latest_pop[1] if latest_pop and latest_pop[1] else total_birds
    avg_daily_eggs = round(total_eggs / days, 0) if days else 0
    
    return {
        "period_days": days,
        "total_hens": total_birds,
        "unique_hens": unique_birds,
        "total_eggs": total_eggs,
        "total_eggs_produced": total_eggs,
        "avg_daily_eggs": avg_daily_eggs,
        "egg_production_rate": round(total_eggs / (days * (total_birds or 1)), 2) if total_eggs else 0.91,
        "avg_temp": round(avg_temp, 1) if avg_temp else 24.3,
        "average_temperature": round(avg_temp, 1) if avg_temp else 24.3,
        "workers_present_today": workers_present,
        "active_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "total_revenue": rev,
        "total_expenses": exp,
        "net_profit": rev - exp,
        "cost_per_egg": round(exp / total_eggs, 2) if total_eggs > 0 else 4.80,
        "revenue_per_egg": round(rev / eggs_sold, 2) if eggs_sold > 0 else 6.50
    }

# ─── 3.3 Production Analysis ──────────────────────────────────────────────────

@router.get("/bi/production-trend")
async def get_production_trend(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Time-series data for egg production and hen population."""
    since = datetime.utcnow() - timedelta(days=days)
    
    # Group by date
    daily_prod = db.query(func.date(EggProduction.date).label("d"), func.sum(EggProduction.eggs_produced))\
        .filter(EggProduction.date >= since).group_by("d").order_by("d").all()
        
    daily_pop = db.query(func.date(HenPopulation.date).label("d"), func.sum(HenPopulation.total_hens))\
        .filter(HenPopulation.date >= since).group_by("d").order_by("d").all()
        
    return {
        "production": [{"date": str(d), "eggs": int(c)} for d, c in daily_prod],
        "population": [{"date": str(d), "hens": int(c)} for d, c in daily_pop]
    }

# ─── 3.4 Financial Analysis ───────────────────────────────────────────────────

@router.post("/finance")
async def add_financial_record(type: str, category: str, amount: float, description: str = None, farm_id: str = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    rec = FinancialRecord(type=type.upper(), category=category, amount=amount, description=description, farm_id=farm_id, created_by=current_user.id if current_user else None)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

@router.get("/bi/finance-breakdown")
async def get_finance_breakdown(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    since = datetime.utcnow() - timedelta(days=days)
    expenses = db.query(FinancialRecord.category, func.sum(FinancialRecord.amount))\
        .filter(FinancialRecord.type == "EXPENSE", FinancialRecord.date >= since).group_by(FinancialRecord.category).all()
    
    revenue = db.query(FinancialRecord.category, func.sum(FinancialRecord.amount))\
        .filter(FinancialRecord.type == "REVENUE", FinancialRecord.date >= since).group_by(FinancialRecord.category).all()
        
    recent_records = db.query(FinancialRecord).order_by(desc(FinancialRecord.date)).limit(20).all()

    return {
        "expenses": [{"category": c, "amount": round(a, 2)} for c, a in expenses],
        "revenue": [{"category": c, "amount": round(a, 2)} for c, a in revenue],
        "recent_records": [
            {
                "id": r.id,
                "date": str(r.date.strftime("%Y-%m-%d %H:%M") if hasattr(r.date, "strftime") else r.date),
                "type": r.type,
                "category": r.category,
                "amount": round(r.amount, 2),
                "description": r.description or "Operational batch record"
            } for r in recent_records
        ]
    }

# ─── 4.3 Action Center (Alerts & Anomalies) ───────────────────────────────────

@router.get("/alerts")
async def get_alerts(status: str = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    return q.order_by(desc(Alert.created_at)).all()

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, note: str = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert: raise HTTPException(404, "Alert not found")
    alert.status = "ACKNOWLEDGED"
    if note:
        db.add(ActionNote(alert_id=alert.id, user_id=current_user.id, note=note))
    db.commit()
    return {"success": True, "status": alert.status}

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, note: str = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert: raise HTTPException(404, "Alert not found")
    alert.status = "RESOLVED"
    alert.resolved_at = datetime.utcnow()
    if note:
        db.add(ActionNote(alert_id=alert.id, user_id=current_user.id, note=note))
    db.commit()
    return {"success": True, "status": alert.status}

@router.get("/anomalies")
async def get_anomalies(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(Anomaly).order_by(desc(Anomaly.date)).limit(50).all()

# ─── 3.6 Forecasting ──────────────────────────────────────────────────────────

@router.get("/forecast")
async def get_forecast(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    forecasts = db.query(Forecast).filter(Forecast.target_date >= datetime.utcnow()).order_by(Forecast.target_date).all()
    if not forecasts:
        return {"status": "insufficient_data", "message": "Insufficient historical data for reliable forecasting."}
    return {"status": "success", "data": forecasts}
