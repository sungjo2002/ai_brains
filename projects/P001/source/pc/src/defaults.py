from __future__ import annotations

ATTENDANCE_SCORE_SETTINGS = {'base_score': 100,
 'early_leave': -5,
 'late': -5,
 'unauthorized_absence': -20,
 'unauthorized_leave': -25,
 'warning': -10}

REJOIN_GRADES = [(90, '양호'), (75, '주의'), (60, '재검토'), (0, '비추천')]

VEHICLE_ALERT_SETTINGS = {'contract_days_threshold': 30, 'remaining_km_threshold': 5000}
