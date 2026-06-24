# Cache invalidation signals are defined in each model's home app:
#   accounts/signals.py  — AccountType → role-based user list caches
#   adverts/signals.py   — CreateAd → ad caches
#   banking/signals.py   — WalletModel → wallet/member list caches
#   fmcg/signals.py      — Product, CartItem → product/cart caches
#   gamification/signals.py — StepCampaignModel, StepSessionModel, PointTransaction
#   treasury/signals.py  — TreasuryAccount → treasury list cache
