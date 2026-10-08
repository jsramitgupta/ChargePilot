import json
import traceback
from app.services.smartlife_service import SmartLifeService

try:
    res = SmartLifeService.start_login('DaqKFqb')
    print(json.dumps(res, indent=2, default=str))
except Exception as e:
    print('EXCEPTION:', e)
    traceback.print_exc()
