from app.core.database import SessionLocal
from app.models.user import User

s=SessionLocal()
users=s.query(User).all()
print('users:', len(users))
for u in users:
    print(u.id, u.username, u.role, u.tenant_id, getattr(u,'is_admin',None))
s.close()
