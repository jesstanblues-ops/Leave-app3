# Leave App 3 (No prorating)

This is a minimal Flask leave management app (no prorating). Features:
- Apply, Approve, Reject leave
- Email notifications (configurable)
- Admin login (use ADMIN_PASSWORD env var)
- Admin can update entitlement and current balance
- Manual yearly reset (no automatic reset)

Deployment steps:
1. Push this repo to GitHub.
2. Connect to Render (or any Python host).
3. Set environment variables on the host:
   - ADMIN_PASSWORD (e.g. admin123)
   - FLASK_SECRET_KEY (random secret)
   - EMAIL_PASSWORD (if ENABLE_EMAIL=True and using Gmail)
4. Deploy.
