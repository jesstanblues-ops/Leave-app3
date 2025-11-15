from datetime import datetime

SYSTEM_START_YEAR = 2026

ADMIN_EMAIL = "jessetan.ba@gmail.com"
ENABLE_EMAIL = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

EMPLOYEES = [
    {
        "name": "YONG YUN CHIN",
        "role": "Staff",
        "join_date": "2008-08-08",
        "entitlement": 18,
        "phone": None,
        "accrual_pattern": {m: 1.5 for m in range(1, 13)}
    },
    {
        "name": "JUBILIN MORIS",
        "role": "Staff",
        "join_date": "2012-01-01",
        "entitlement": 18,
        "phone": None,
        "accrual_pattern": {m: 1.5 for m in range(1, 13)}
    },
    {
        "name": "ABDULLAH BIN ALADDIN",
        "role": "Staff",
        "join_date": "2012-02-01",
        "entitlement": 16,
        "phone": None,
        "accrual_pattern": {
            1:1,2:1,3:1,4:1,
            5:1.5,6:1.5,7:1.5,8:1.5,
            9:1.5,10:1.5,11:1.5,12:1.5
        }
    },
    {
        "name": "MAT SAHAK BIN ABDULLAH",
        "role": "Staff",
        "join_date": "2015-02-02",
        "entitlement": 16,
        "phone": None,
        "accrual_pattern": {
            1:1,2:1,3:1,4:1,
            5:1.5,6:1.5,7:1.5,8:1.5,
            9:1.5,10:1.5,11:1.5,12:1.5
        }
    },
    {
        "name": "VYANESSA STEVEN WONG",
        "role": "Staff",
        "join_date": "2018-03-01",
        "entitlement": 16,
        "phone": None,
        "accrual_pattern": {
            1:1,2:1,3:1,4:1,
            5:1.5,6:1.5,7:1.5,8:1.5,
            9:1.5,10:1.5,11:1.5,12:1.5
        }
    },
    {
        "name": "MARY IMMACULATE",
        "role": "Staff",
        "join_date": "2021-02-01",
        "entitlement": 16,
        "phone": None,
        "accrual_pattern": {
            1:1,2:1,3:1,4:1,
            5:1.5,6:1.5,7:1.5,8:1.5,
            9:1.5,10:1.5,11:1.5,12:1.5
        }
    },
    {
        "name": "RACHEAL GAIL",
        "role": "Staff",
        "join_date": "2023-07-01",
        "entitlement": 14,
        "phone": None,
        "accrual_pattern": {
            1:1,2:1,3:1,4:1,
            5:1,6:1,7:1,8:1,
            9:1.5,10:1.5,11:1.5,12:1.5
        }
    },
    {
        "name": "ABIGAIL",
        "role": "Staff",
        "join_date": "2025-11-03",
        "entitlement": None,
        "phone": None,
        "accrual_pattern": {m: 1 for m in range(1, 13)}
    }
]
