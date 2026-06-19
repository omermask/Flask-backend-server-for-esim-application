from app.routes.admin_backup import admin_backup_routes
from app.routes.admin_referral import admin_referral_routes
from app.routes.admin_support import admin_support_routes
from app.routes.auth import auth_routes
from app.routes.plans import plan_routes, admin_plan_routes
from app.routes.orders import order_routes
from app.routes.wallet import wallet_routes
from app.routes.payments import payment_routes
from app.routes.admin import admin_routes
from app.routes.esim_callback import esim_callback_routes
from app.routes.otpiq_callback import otpiq_callback_routes
from app.routes.user import user_routes

__all__ = [
    "admin_backup_routes",
    "admin_plan_routes",
    "admin_referral_routes",
    "admin_routes",
    "admin_support_routes",
    "auth_routes",
    "esim_callback_routes",
    "order_routes",
    "otpiq_callback_routes",
    "payment_routes",
    "plan_routes",
    "user_routes",
    "wallet_routes",
]
