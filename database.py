import asyncio
import io
import json
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from bson.json_util import dumps as bson_dumps

import dns.resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

from config import MONGO_URI, MONGO_DB_NAME

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Async wrapper for MongoDB-backed data layer."""

    AUTO_ID_COLLECTIONS = (
        "products", "plans", "keys", "purchases",
        "fund_requests", "tickets", "admin_logs",
    )

    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self._init_indexes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_indexes(self):
        try:
            self.db.products.create_index("name", unique=True)
            self.db.keys.create_index("key_value", unique=True)
            self.db.fund_requests.create_index("utr", unique=True, sparse=True)
            self.db.fund_requests.create_index("order_id", unique=True, sparse=True)
            self.db.users.create_index("verified")
            self.db.users.create_index("total_spent")
            self.db.plans.create_index("product_id")
            self.db.keys.create_index([("plan_id", ASCENDING), ("is_sold", ASCENDING)])
            self.db.purchases.create_index("user_id")
            self.db.fund_requests.create_index("status")
            self.db.tickets.create_index("status")
            self.db.redeemed_promos.create_index([("user_id", ASCENDING), ("code", ASCENDING)], unique=True)
        except Exception as e:
            logger.warning(f"Index init warning: {e}")

    async def _next_id(self, name: str) -> int:
        def _op():
            doc = self.db.counters.find_one_and_update(
                {"_id": name},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return doc["seq"]
        return await asyncio.to_thread(_op)

    @staticmethod
    def _wrap(doc: Optional[dict]) -> dict:
        if not doc:
            return {}
        if "_id" in doc and "id" not in doc and isinstance(doc["_id"], int):
            doc["id"] = doc["_id"]
        return doc

    def _wrap_many(self, cursor) -> List[dict]:
        return [self._wrap(d) for d in cursor]

    # ------------------------------------------------------------------
    # Settings (key/value)
    # ------------------------------------------------------------------
    async def seed_default_settings(self, defaults: Dict[str, Any]):
        def _op():
            for k, v in defaults.items():
                if not self.db.settings.find_one({"_id": k}):
                    self.db.settings.insert_one({"_id": k, "value": v})
        await asyncio.to_thread(_op)

    async def get_setting(self, key: str, default: str = "") -> str:
        def _op():
            doc = self.db.settings.find_one({"_id": key})
            return doc["value"] if doc and doc.get("value") is not None else default
        return await asyncio.to_thread(_op)

    async def set_setting(self, key: str, value: Any):
        await asyncio.to_thread(self.db.settings.update_one,
                                {"_id": key}, {"$set": {"value": value}}, True)

    # ------------------------------------------------------------------
    # Admin logs
    # ------------------------------------------------------------------
    async def log_admin_action(self, admin_id: int, action: str, target: str):
        try:
            _id = await self._next_id("admin_logs")
            await asyncio.to_thread(self.db.admin_logs.insert_one, {
                "_id": _id,
                "admin_id": admin_id,
                "action": action,
                "target": target,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def add_user(self, user_id: int, username: str, first_name: str,
                 referrer_id: Optional[int] = None) -> bool:
        def _op():
            existing = self.db.users.find_one({"_id": user_id})
            now_iso = datetime.now().isoformat()
            if not existing:
                self.db.users.insert_one({
                    "_id": user_id,
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "balance": 0,
                    "joined_date": now_iso,
                    "is_banned": 0,
                    "verified": 0,
                    "total_spent": 0,
                    "referrer_id": referrer_id,
                    "total_referrals": 0,
                    "referral_earnings": 0,
                    "last_active": now_iso,
                })
                if referrer_id:
                    self.db.users.update_one(
                        {"_id": referrer_id},
                        {"$inc": {"total_referrals": 1}},
                    )
                return True
            else:
                self.db.users.update_one(
                    {"_id": user_id},
                    {"$set": {
                        "username": username,
                        "first_name": first_name,
                        "last_active": now_iso,
                    }},
                )
                return False
        return await asyncio.to_thread(_op)

    async def get_user(self, user_id: int) -> dict:
        def _op():
            doc = self.db.users.find_one({"_id": user_id})
            if not doc: return {}
            doc.setdefault("user_id", doc["_id"])
            return doc
        return await asyncio.to_thread(_op)

    async def update_balance(self, user_id: int, amount: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$inc": {"balance": amount}})

    async def ban_user(self, user_id: int, state: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$set": {"is_banned": int(state)}})

    async def verify_user(self, user_id: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$set": {"verified": 1}})

    async def get_all_users_count(self) -> int:
        return await asyncio.to_thread(self.db.users.count_documents, {"verified": 1})

    async def get_all_verified_user_ids(self) -> List[int]:
        def _op():
            return [u["_id"] for u in self.db.users.find({"verified": 1}, {"_id": 1})]
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Staff / Sub-Admins
    # ------------------------------------------------------------------
    async def add_staff(self, user_id: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$set": {"is_staff": 1}})

    async def remove_staff(self, user_id: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$set": {"is_staff": 0}})

    async def is_staff(self, user_id: int) -> bool:
        def _op():
            user = self.db.users.find_one({"_id": user_id}, {"is_staff": 1})
            return bool(user and user.get("is_staff", 0))
        return await asyncio.to_thread(_op)

    async def get_all_staff(self) -> List[dict]:
        return await asyncio.to_thread(lambda: list(self.db.users.find({"is_staff": 1})))

    # ------------------------------------------------------------------
    # Resellers
    # ------------------------------------------------------------------
    async def set_reseller(self, user_id: int, days: int, discount: float):
        def _op():
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
            self.db.users.update_one(
                {"_id": user_id},
                {"$set": {
                    "is_reseller": True,
                    "reseller_expiry": expiry,
                    "reseller_discount": float(discount)
                }}
            )
        await asyncio.to_thread(_op)

    async def remove_reseller(self, user_id: int):
        await asyncio.to_thread(self.db.users.update_one,
                                {"_id": user_id}, {"$set": {"is_reseller": False}})

    async def get_resellers(self) -> List[dict]:
        return await asyncio.to_thread(lambda: list(self.db.users.find({"is_reseller": True})))

    async def is_active_reseller(self, user_id: int) -> Tuple[bool, float]:
        def _op():
            user = self.db.users.find_one({"_id": user_id})
            if not user or not user.get("is_reseller"):
                return False, 0.0
            expiry_str = user.get("reseller_expiry")
            if not expiry_str: return False, 0.0
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if datetime.now() < expiry:
                    return True, float(user.get("reseller_discount", 0.0))
            except Exception: pass
            return False, 0.0
        return await asyncio.to_thread(_op)

    async def find_user_by_id_or_username(self, query: str) -> Optional[dict]:
        def _op():
            if not query: return None
            if query.isdigit():
                user = self.db.users.find_one({"_id": int(query)})
                if user: return user
            clean_uname = query.replace("@", "").strip()
            return self.db.users.find_one({"username": {"$regex": f"^{clean_uname}$", "$options": "i"}})
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Promo codes
    # ------------------------------------------------------------------
    async def create_promo(self, code: str, reward_paise: int, max_uses: int) -> bool:
        def _op():
            if self.db.promo_codes.find_one({"_id": code}):
                return False
            self.db.promo_codes.insert_one({
                "_id": code,
                "reward_paise": reward_paise,
                "max_uses": max_uses,
                "current_uses": 0,
                "created_at": datetime.now().isoformat(),
            })
            return True
        return await asyncio.to_thread(_op)

    async def redeem_promo(self, user_id: int, code: str) -> Tuple[bool, str, int]:
        def _op():
            promo = self.db.promo_codes.find_one({"_id": code})
            if not promo: return False, "Invalid Promo Code.", 0
            if promo["current_uses"] >= promo["max_uses"]:
                return False, "Promo Code has reached its maximum uses.", 0
            already = self.db.redeemed_promos.find_one({"user_id": user_id, "code": code})
            if already: return False, "You have already redeemed this code.", 0
            reward = int(promo["reward_paise"])
            self.db.users.update_one({"_id": user_id}, {"$inc": {"balance": reward}})
            self.db.promo_codes.update_one({"_id": code}, {"$inc": {"current_uses": 1}})
            self.db.redeemed_promos.insert_one({
                "user_id": user_id, "code": code,
                "redeemed_at": datetime.now().isoformat(),
            })
            return True, "Success", reward
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------
    async def get_leaderboard(self) -> List[dict]:
        def _op():
            cursor = self.db.users.find(
                {"verified": 1, "total_spent": {"$gt": 0}},
                {"first_name": 1, "total_spent": 1},
            ).sort("total_spent", DESCENDING).limit(10)
            return [{"first_name": d.get("first_name") or "User", "total_spent": d.get("total_spent", 0)} for d in cursor]
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    async def get_active_products(self) -> List[dict]:
        return await asyncio.to_thread(lambda: self._wrap_many(self.db.products.find({"is_active": 1}).sort("name", ASCENDING)))

    async def get_all_products(self) -> List[dict]:
        return await asyncio.to_thread(lambda: self._wrap_many(self.db.products.find({}).sort("name", ASCENDING)))

    async def get_product(self, prod_id: int) -> dict:
        return await asyncio.to_thread(lambda: self._wrap(self.db.products.find_one({"_id": int(prod_id)})))

    async def add_product(self, name: str, desc: str) -> int:
        _id = await self._next_id("products")
        def _op():
            try:
                self.db.products.insert_one({
                    "_id": _id, "name": name, "description": desc,
                    "is_active": 1, "image_url": None, "download_link": "Link not set",
                })
            except DuplicateKeyError: pass
            return _id
        return await asyncio.to_thread(_op)

    async def toggle_product(self, prod_id: int):
        def _op():
            doc = self.db.products.find_one({"_id": int(prod_id)})
            if not doc: return
            new_state = 0 if doc.get("is_active", 1) == 1 else 1
            self.db.products.update_one({"_id": int(prod_id)}, {"$set": {"is_active": new_state}})
        await asyncio.to_thread(_op)

    async def delete_product(self, prod_id: int):
        def _op():
            p_id = int(prod_id)
            plan_ids = [p["_id"] for p in self.db.plans.find({"product_id": p_id}, {"_id": 1})]
            if plan_ids:
                self.db.keys.delete_many({"plan_id": {"$in": plan_ids}})
                self.db.plans.delete_many({"_id": {"$in": plan_ids}})
            self.db.products.delete_one({"_id": p_id})
        await asyncio.to_thread(_op)

    async def update_product_description(self, prod_id: int, new_desc: str):
        await asyncio.to_thread(self.db.products.update_one, {"_id": int(prod_id)}, {"$set": {"description": new_desc}})

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------
    async def get_plans(self, prod_id: int) -> List[dict]:
        return await asyncio.to_thread(lambda: self._wrap_many(self.db.plans.find({"product_id": int(prod_id)}).sort("price", ASCENDING)))

    async def get_plan(self, plan_id: int) -> dict:
        def _op():
            plan = self.db.plans.find_one({"_id": int(plan_id)})
            if not plan: return {}
            plan = self._wrap(plan)
            prod = self.db.products.find_one({"_id": plan.get("product_id")})
            plan["product_name"] = prod["name"] if prod else "Unknown"
            return plan
        return await asyncio.to_thread(_op)

    async def add_plan(self, prod_id: int, duration: str, price: int):
        _id = await self._next_id("plans")
        await asyncio.to_thread(self.db.plans.insert_one, {
            "_id": _id, "product_id": int(prod_id), "duration": duration, "price": int(price),
        })

    async def delete_plan(self, plan_id: int):
        def _op():
            p_id = int(plan_id)
            self.db.keys.delete_many({"plan_id": p_id})
            self.db.plans.delete_one({"_id": p_id})
        await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------
    async def add_keys(self, plan_id: int, keys: List[str]) -> int:
        def _op():
            count = 0
            for k in keys:
                if not k: continue
                try:
                    # Need unique IDs for each key. Calling _next_id in a loop is slow,
                    # but we are in a thread here.
                    # Actually, we can't call await inside a synchronous _op thread.
                    # We should get the next sequence and increment it ourselves or call counters multiple times.
                    # For simplicity, we'll just use a loop with synchronous find_one_and_update.
                    next_id_doc = self.db.counters.find_one_and_update(
                        {"_id": "keys"}, {"$inc": {"seq": 1}},
                        upsert=True, return_document=ReturnDocument.AFTER
                    )
                    _id = next_id_doc["seq"]
                    self.db.keys.insert_one({
                        "_id": _id, "plan_id": int(plan_id), "key_value": k,
                        "is_sold": 0, "sold_to": None, "purchase_date": None, "expiry_date": None,
                    })
                    count += 1
                except DuplicateKeyError: pass
            return count
        return await asyncio.to_thread(_op)

    async def get_stock_summary(self) -> Dict[str, List[Dict[str, Any]]]:
        def _op():
            summary = {}
            for prod in self.db.products.find({"is_active": 1}).sort("name", ASCENDING):
                plans = list(self.db.plans.find({"product_id": prod["_id"]}).sort("price", ASCENDING))
                entries = []
                for plan in plans:
                    count = self.db.keys.count_documents({"plan_id": plan["_id"], "is_sold": 0})
                    entries.append({"duration": plan["duration"], "count": count})
                summary[prod["name"]] = entries
            return summary
        return await asyncio.to_thread(_op)

    async def get_available_key_count(self, plan_id: int) -> int:
        return await asyncio.to_thread(self.db.keys.count_documents, {"plan_id": int(plan_id), "is_sold": 0})

    async def purchase_key_automated(self, user_id: int, plan_id: int) -> Tuple[bool, str, dict]:
        def _op():
            plan = self.db.plans.find_one({"_id": int(plan_id)})
            if not plan: return False, "Plan not found.", {}
            product = self.db.products.find_one({"_id": plan["product_id"]})
            product_name = product["name"] if product else "Unknown"
            key_doc = self.db.keys.find_one({"plan_id": int(plan_id), "is_sold": 0})
            if not key_doc: return False, "Out of stock.", {}
            days = 30
            try:
                digits = "".join(filter(str.isdigit, plan["duration"]))
                if digits: days = int(digits)
            except Exception: pass
            expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
            purchase_date = datetime.now().isoformat()
            self.db.keys.update_one({"_id": key_doc["_id"]}, {"$set": {
                "is_sold": 1, "sold_to": user_id, "purchase_date": purchase_date, "expiry_date": expiry_date,
            }})
            # Get next purchase ID synchronously in this thread
            next_p_doc = self.db.counters.find_one_and_update(
                {"_id": "purchases"}, {"$inc": {"seq": 1}},
                upsert=True, return_document=ReturnDocument.AFTER
            )
            self.db.purchases.insert_one({
                "_id": next_p_doc["seq"], "user_id": user_id, "plan_id": int(plan_id),
                "key_id": key_doc["_id"], "amount": int(plan["price"]), "purchase_date": purchase_date,
            })
            return True, "Success", {
                "key": key_doc["key_value"], "expiry": expiry_date,
                "product": product_name, "duration": plan["duration"]
            }
        return await asyncio.to_thread(_op)

    async def get_user_keys(self, user_id: int, offset: int = 0, limit: int = 5) -> List[dict]:
        def _op():
            cursor = (self.db.keys.find({"sold_to": user_id}).sort("purchase_date", DESCENDING).skip(offset).limit(limit))
            out = []
            for k in cursor:
                plan = self.db.plans.find_one({"_id": k.get("plan_id")})
                prod = self.db.products.find_one({"_id": plan["product_id"]}) if plan else None
                out.append({
                    "name": prod["name"] if prod else "Unknown",
                    "duration": plan["duration"] if plan else "",
                    "key_value": k["key_value"], "expiry_date": k.get("expiry_date") or "",
                })
            return out
        return await asyncio.to_thread(_op)

    async def get_user_keys_count(self, user_id: int) -> int:
        return await asyncio.to_thread(self.db.keys.count_documents, {"sold_to": user_id})

    # ------------------------------------------------------------------
    # Fund requests
    # ------------------------------------------------------------------
    async def create_fund_request(self, user_id: int, utr: str, plan_id: Optional[int] = None) -> bool:
        def _op():
            if self.db.fund_requests.find_one({"utr": utr}): return False
            try:
                next_f_doc = self.db.counters.find_one_and_update(
                    {"_id": "fund_requests"}, {"$inc": {"seq": 1}},
                    upsert=True, return_document=ReturnDocument.AFTER
                )
                self.db.fund_requests.insert_one({
                    "_id": next_f_doc["seq"], "user_id": user_id, "plan_id": plan_id,
                    "amount_requested": 0, "utr": utr, "status": "PENDING",
                    "request_date": datetime.now().isoformat(), "resolved_date": None,
                })
                return True
            except DuplicateKeyError: return False
        return await asyncio.to_thread(_op)

    async def get_pending_fund_requests(self) -> List[dict]:
        def _op():
            out = []
            for r in self.db.fund_requests.find({"status": "PENDING"}).sort("request_date", ASCENDING):
                r = self._wrap(r)
                u = self.db.users.find_one({"_id": r["user_id"]}) if r.get("user_id") else None
                r["username"] = u.get("username") if u else None
                r["first_name"] = u.get("first_name") if u else None
                out.append(r)
            return out
        return await asyncio.to_thread(_op)

    async def update_fund_request(self, req_id: int, status: str, amount: int = 0):
        await asyncio.to_thread(self.db.fund_requests.update_one, {"_id": int(req_id)},
                                {"$set": {"status": status, "amount_requested": int(amount), "resolved_date": datetime.now().isoformat()}})

    async def get_fund_request(self, req_id: int) -> dict:
        return await asyncio.to_thread(lambda: self._wrap(self.db.fund_requests.find_one({"_id": int(req_id)})))

    # ------------------------------------------------------------------
    # Order-id based fund requests (used by the auto-UPI flow)
    # ------------------------------------------------------------------
    async def create_fund_request_with_order(self, user_id: int, order_id: str,
                                       plan_id: int, amount: float) -> bool:
        def _op():
            if self.db.fund_requests.find_one({"order_id": order_id}): return False
            try:
                next_f_doc = self.db.counters.find_one_and_update(
                    {"_id": "fund_requests"}, {"$inc": {"seq": 1}},
                    upsert=True, return_document=ReturnDocument.AFTER
                )
                self.db.fund_requests.insert_one({
                    "_id": next_f_doc["seq"], "user_id": user_id, "order_id": order_id,
                    "plan_id": int(plan_id) if plan_id is not None else None,
                    "amount_requested": float(amount), "utr": None, "transaction_id": None,
                    "sender_name": None, "payment_time": None, "status": "PENDING",
                    "request_date": datetime.now().isoformat(), "resolved_date": None,
                })
                return True
            except DuplicateKeyError: return False
        return await asyncio.to_thread(_op)

    async def get_fund_request_by_order(self, order_id: str) -> dict:
        return await asyncio.to_thread(lambda: self._wrap(self.db.fund_requests.find_one({"order_id": order_id})))

    async def update_fund_request_by_order(self, order_id: str, status: str,
                                     utr: Optional[str] = None,
                                     transaction_id: Optional[str] = None,
                                     sender_name: Optional[str] = None,
                                     payment_time: Optional[str] = None,
                                     key_value: Optional[str] = None) -> bool:
        def _op():
            sets = {"status": status, "resolved_date": datetime.now().isoformat()}
            if transaction_id is not None: sets["transaction_id"] = transaction_id
            if sender_name is not None: sets["sender_name"] = sender_name
            if payment_time is not None: sets["payment_time"] = payment_time
            if key_value is not None: sets["delivered_key"] = key_value
            if utr:
                sets["utr"] = utr
                clash = self.db.fund_requests.find_one({"utr": utr, "order_id": {"$ne": order_id}})
                if clash: return False
            try:
                self.db.fund_requests.update_one({"order_id": order_id}, {"$set": sets})
                return True
            except DuplicateKeyError: return False
        return await asyncio.to_thread(_op)

    async def is_utr_already_used(self, utr: str,
                            except_order_id: Optional[str] = None) -> bool:
        def _op():
            if not utr: return False
            q = {"utr": utr}
            if except_order_id: q["order_id"] = {"$ne": except_order_id}
            return self.db.fund_requests.find_one(q) is not None
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------
    async def create_ticket(self, user_id: int, message: str) -> int:
        _id = await self._next_id("tickets")
        await asyncio.to_thread(self.db.tickets.insert_one, {
            "_id": _id, "user_id": user_id, "message": message, "reply": None,
            "status": "OPEN", "created_at": datetime.now().isoformat(), "resolved_at": None,
        })
        return _id

    async def get_open_tickets(self) -> List[dict]:
        return await asyncio.to_thread(lambda: self._wrap_many(self.db.tickets.find({"status": "OPEN"}).sort("created_at", ASCENDING)))

    async def reply_ticket(self, ticket_id: int, reply: str) -> int:
        def _op():
            ticket = self.db.tickets.find_one({"_id": int(ticket_id)})
            if not ticket: return 0
            self.db.tickets.update_one({"_id": int(ticket_id)}, {"$set": {
                "reply": reply, "status": "CLOSED", "resolved_at": datetime.now().isoformat(),
            }})
            return ticket["user_id"]
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    async def get_global_stats(self) -> Tuple[int, int, int, int]:
        def _op():
            users = self.db.users.count_documents({"verified": 1})
            agg = list(self.db.purchases.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]))
            revenue = int(agg[0]["total"]) if agg else 0
            sold_keys = self.db.keys.count_documents({"is_sold": 1})
            avail_keys = self.db.keys.count_documents({"is_sold": 0})
            return users, revenue, sold_keys, avail_keys
        return await asyncio.to_thread(_op)

    # ------------------------------------------------------------------
    # Backup / Export
    # ------------------------------------------------------------------
    async def export_database(self) -> bytes:
        def _op():
            snapshot = {}
            collections = [
                "users", "products", "plans", "keys", "purchases",
                "fund_requests", "tickets", "admin_logs", "settings",
                "promo_codes", "redeemed_promos", "counters",
            ]
            for col in collections: snapshot[col] = list(self.db[col].find({}))
            return bson_dumps(snapshot, indent=2).encode("utf-8")
        return await asyncio.to_thread(_op)
