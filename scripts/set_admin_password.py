from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

NEW_PW = 'secret123'

s=SessionLocal()
user = s.query(User).filter(User.username=='admin').first()
if not user:
    print('admin user not found')
else:
    user.password_hash = hash_password(NEW_PW)
    s.add(user)
    s.commit()
    print('updated admin password to', NEW_PW)
s.close()
