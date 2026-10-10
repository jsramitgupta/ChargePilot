from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import verify_password
s=SessionLocal()
user=s.query(User).filter(User.username=='admin').first()
print('username', user.username)
print('password_hash', user.password_hash[:60])
print('verify change-me ->', verify_password('change-me', user.password_hash))
print('verify secret123 ->', verify_password('secret123', user.password_hash))
s.close()
