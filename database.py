import io
import json
import logging
import threading
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
    """MongoDB-backed data layer for the Hack Store Telegram bot.

    All documents that previously had auto-increment SQL ids now use a
    monotonically increasing integer (`_id`) generated via the `counters`
    collection. The wrapper also exposes an `id` field on returned
    documents so the rest of the bot code can keep using `doc['id']`.
    """

    AUTO_ID_COLLECTIONS = (
        "products", "plans", "keys", "purchases",
        "fund_requests", "tickets", "admin_logs",
    )

    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self.lock = threading.Lock()
        self._init_indexes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_indexes(self):
        try:
            self.db.products.create_index("name", unique=True)
            self.db.keys.create_index("key_value", unique=True)
            self.db.fund_requests.create_index("utr", unique=True)
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

    def _next_id(self, name: str) -> int:
        doc = self.db.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["seq"]

    @staticmethod
    def _wrap(doc: Optional[dict]) -> dict:
        """Add 'id' alias for '_id' on auto-id docs, leave others alone."""
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
    def seed_default_settings(self, defaults: Dict[str, Any]):
        """Insert defaults only if the key does not already exist."""
        for k, v in defaults.items():
            if not self.db.settings.find_one({"_id": k}):
                self.db.settings.insert_one({"_id": k, "value": v})

    def get_setting(self, key: str, default: str = "") -> str:
        doc = self.db.settings.find_one({"_id": key})
        return doc["value"] if doc and doc.get("value") is not None else default

    def set_setting(self, key: str, value: Any):
        with self.lock:
            self.db.settings.update_one(
                {"_id": key}, {"$set": {"value": value}}, upsert=True
            )

    # ------------------------------------------------------------------
    # Admin logs
    # ------------------------------------------------------------------
    def log_admin_action(self, admin_id: int, action: str, target: str):
        try:
            with self.lock:
                _id = self._next_id("admin_logs")
                self.db.admin_logs.insert_one({
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
    def add_user(self, user_id: int, username: str, first_name: str,
                 referrer_id: Optional[int] = None) -> bool:
        with self.lock:
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

    def get_user(self, user_id: int) -> dict:
        try:
            doc = self.db.users.find_one({"_id": user_id})
            if not doc:
                return {}
            doc.setdefault("user_id", doc["_id"])
            return doc
        except Exception as e:
            logger.error(f"DB Error getting user: {e}")
            return {}

    def update_balance(self, user_id: int, amount: int):
        with self.lock:
            self.db.users.update_one(
                {"_id": user_id}, {"$inc": {"balance": amount}}
            )

    def ban_user(self, user_id: int, state: int):
        with self.lock:
            self.db.users.update_one(
                {"_id": user_id}, {"$set": {"is_banned": int(state)}}
            )

    def verify_user(self, user_id: int):
        with self.lock:
            self.db.users.update_one(
                {"_id": user_id}, {"$set": {"verified": 1}}
            )

    def get_all_users_count(self) -> int:
        return self.db.users.count_documents({"verified": 1})

    def get_all_verified_user_ids(self) -> List[int]:
        return [u["_id"] for u in self.db.users.find({"verified": 1}, {"_id": 1})]

    # ------------------------------------------------------------------
    # Promo codes
    # ------------------------------------------------------------------
    def create_promo(self, code: str, reward_paise: int, max_uses: int) -> bool:
        with self.lock:
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

    def redeem_promo(self, user_id: int, code: str) -> Tuple[bool, str, int]:
        with self.lock:
            promo = self.db.promo_codes.find_one({"_id": code})
            if not promo:
                return False, "Invalid Promo Code.", 0
            if promo["current_uses"] >= promo["max_uses"]:
                return False, "Promo Code has reached its maximum uses.", 0
            already = self.db.redeemed_promos.find_one({"user_id": user_id, "code": code})
            if already:
                return False, "You have already redeemed this code.", 0
            reward = int(promo["reward_paise"])
            self.db.users.update_one({"_id": user_id}, {"$inc": {"balance": reward}})
            self.db.promo_codes.update_one({"_id": code}, {"$inc": {"current_uses": 1}})
            self.db.redeemed_promos.insert_one({
                "user_id": user_id,
                "code": code,
                "redeemed_at": datetime.now().isoformat(),
            })
            return True, "Success", reward

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------
    def get_leaderboard(self) -> List[dict]:
        cursor = self.db.users.find(
            {"verified": 1, "total_spent": {"$gt": 0}},
            {"first_name": 1, "total_spent": 1},
        ).sort("total_spent", DESCENDING).limit(10)
        return [
            {"first_name": d.get("first_name") or "User", "total_spent": d.get("total_spent", 0)}
            for d in cursor
        ]

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    def get_active_products(self) -> List[dict]:
        return self._wrap_many(self.db.products.find({"is_active": 1}).sort("name", ASCENDING))

    def get_all_products(self) -> List[dict]:
        return self._wrap_many(self.db.products.find({}).sort("name", ASCENDING))

    def get_product(self, prod_id: int) -> dict:
        return self._wrap(self.db.products.find_one({"_id": int(prod_id)}))

    def add_product(self, name: str, desc: str) -> int:
        with self.lock:
            _id = self._next_id("products")
            try:
                self.db.products.insert_one({
                    "_id": _id,
                    "name": name,
                    "description": desc,
                    "is_active": 1,
                    "image_url": None,
                    "download_link": "Link not set",
                })
            except DuplicateKeyError:
                pass
            return _id

    def toggle_product(self, prod_id: int):
        with self.lock:
            doc = self.db.products.find_one({"_id": int(prod_id)})
            if not doc:
                return
            new_state = 0 if doc.get("is_active", 1) == 1 else 1
            self.db.products.update_one(
                {"_id": int(prod_id)}, {"$set": {"is_active": new_state}}
            )

    def delete_product(self, prod_id: int):
        with self.lock:
            prod_id = int(prod_id)
            plan_ids = [p["_id"] for p in self.db.plans.find({"product_id": prod_id}, {"_id": 1})]
            if plan_ids:
                self.db.keys.delete_many({"plan_id": {"$in": plan_ids}})
                self.db.plans.delete_many({"_id": {"$in": plan_ids}})
            self.db.products.delete_one({"_id": prod_id})

    def update_product_description(self, prod_id: int, new_desc: str):
        with self.lock:
            self.db.products.update_one(
                {"_id": int(prod_id)}, {"$set": {"description": new_desc}}
            )

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------
    def get_plans(self, prod_id: int) -> List[dict]:
        return self._wrap_many(
            self.db.plans.find({"product_id": int(prod_id)}).sort("price", ASCENDING)
        )

    def get_plan(self, plan_id: int) -> dict:
        plan = self.db.plans.find_one({"_id": int(plan_id)})
        if not plan:
            return {}
        plan = self._wrap(plan)
        prod = self.db.products.find_one({"_id": plan.get("product_id")})
        plan["product_name"] = prod["name"] if prod else "Unknown"
        return plan

    def add_plan(self, prod_id: int, duration: str, price: int):
        with self.lock:
            _id = self._next_id("plans")
            self.db.plans.insert_one({
                "_id": _id,
                "product_id": int(prod_id),
                "duration": duration,
                "price": int(price),
            })

    def delete_plan(self, plan_id: int):
        with self.lock:
            plan_id = int(plan_id)
            self.db.keys.delete_many({"plan_id": plan_id})
            self.db.plans.delete_one({"_id": plan_id})

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------
    def add_keys(self, plan_id: int, keys: List[str]) -> int:
        with self.lock:
            count = 0
            for k in keys:
                if not k:
                    continue
                try:
                    _id = self._next_id("keys")
                    self.db.keys.insert_one({
                        "_id": _id,
                        "plan_id": int(plan_id),
                        "key_value": k,
                        "is_sold": 0,
                        "sold_to": None,
                        "purchase_date": None,
                        "expiry_date": None,
                    })
                    count += 1
                except DuplicateKeyError:
                    pass
            return count

    def get_stock_summary(self) -> Dict[str, List[Dict[str, Any]]]:
        summary: Dict[str, List[Dict[str, Any]]] = {}
        for prod in self.db.products.find({"is_active": 1}).sort("name", ASCENDING):
            plans = list(self.db.plans.find({"product_id": prod["_id"]}).sort("price", ASCENDING))
            entries = []
            for plan in plans:
                count = self.db.keys.count_documents({"plan_id": plan["_id"], "is_sold": 0})
                entries.append({"duration": plan["duration"], "count": count})
            summary[prod["name"]] = entries
        return summary

    def get_available_key_count(self, plan_id: int) -> int:
        return self.db.keys.count_documents({"plan_id": int(plan_id), "is_sold": 0})

    def purchase_key_automated(self, user_id: int, plan_id: int) -> Tuple[bool, str, dict]:
        """Specific version for automated delivery when admin approves a request."""
        with self.lock:
            plan = self.db.plans.find_one({"_id": int(plan_id)})
            if not plan:
                return False, "Plan not found.", {}

            product = self.db.products.find_one({"_id": plan["product_id"]})
            product_name = product["name"] if product else "Unknown"

            key_doc = self.db.keys.find_one({"plan_id": int(plan_id), "is_sold": 0})
            if not key_doc:
                return False, "Out of stock.", {}

            days = 30
            try:
                digits = "".join(filter(str.isdigit, plan["duration"]))
                if digits: days = int(digits)
            except Exception: pass

            expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
            purchase_date = datetime.now().isoformat()

            # Mark key as sold
            self.db.keys.update_one(
                {"_id": key_doc["_id"]},
                {"$set": {
                    "is_sold": 1,
                    "sold_to": user_id,
                    "purchase_date": purchase_date,
                    "expiry_date": expiry_date,
                }},
            )

            # Record purchase
            pid = self._next_id("purchases")
            self.db.purchases.insert_one({
                "_id": pid,
                "user_id": user_id,
                "plan_id": int(plan_id),
                "key_id": key_doc["_id"],
                "amount": int(plan["price"]),
                "purchase_date": purchase_date,
            })

            return True, "Success", {
                "key": key_doc["key_value"],
                "expiry": expiry_date,
                "product": product_name,
                "duration": plan["duration"]
            }

    def get_user_keys(self, user_id: int, offset: int = 0, limit: int = 5) -> List[dict]:
        cursor = (
            self.db.keys.find({"sold_to": user_id})
            .sort("purchase_date", DESCENDING)
            .skip(offset)
            .limit(limit)
        )
        out = []
        for k in cursor:
            plan = self.db.plans.find_one({"_id": k.get("plan_id")})
            prod = self.db.products.find_one({"_id": plan["product_id"]}) if plan else None
            out.append({
                "name": prod["name"] if prod else "Unknown",
                "duration": plan["duration"] if plan else "",
                "key_value": k["key_value"],
                "expiry_date": k.get("expiry_date") or "",
            })
        return out

    def get_user_keys_count(self, user_id: int) -> int:
        return self.db.keys.count_documents({"sold_to": user_id})

    # ------------------------------------------------------------------
    # Fund requests
    # ------------------------------------------------------------------
    def create_fund_request(self, user_id: int, utr: str, plan_id: Optional[int] = None) -> bool:
        with self.lock:
            if self.db.fund_requests.find_one({"utr": utr}):
                return False
            try:
                _id = self._next_id("fund_requests")
                self.db.fund_requests.insert_one({
                    "_id": _id,
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "amount_requested": 0,
                    "utr": utr,
                    "status": "PENDING",
                    "request_date": datetime.now().isoformat(),
                    "resolved_date": None,
                })
                return True
            except DuplicateKeyError:
                return False

    def get_pending_fund_requests(self) -> List[dict]:
        out = []
        for r in self.db.fund_requests.find({"status": "PENDING"}).sort("request_date", ASCENDING):
            r = self._wrap(r)
            u = self.db.users.find_one({"_id": r["user_id"]}) if r.get("user_id") else None
            r["username"] = u.get("username") if u else None
            r["first_name"] = u.get("first_name") if u else None
            out.append(r)
        return out

    def update_fund_request(self, req_id: int, status: str, amount: int = 0):
        with self.lock:
            self.db.fund_requests.update_one(
                {"_id": int(req_id)},
                {"$set": {
                    "status": status,
                    "amount_requested": int(amount),
                    "resolved_date": datetime.now().isoformat(),
                }},
            )

    def get_fund_request(self, req_id: int) -> dict:
        return self._wrap(self.db.fund_requests.find_one({"_id": int(req_id)}))

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------
    def create_ticket(self, user_id: int, message: str) -> int:
        with self.lock:
            _id = self._next_id("tickets")
            self.db.tickets.insert_one({
                "_id": _id,
                "user_id": user_id,
                "message": message,
                "reply": None,
                "status": "OPEN",
                "created_at": datetime.now().isoformat(),
                "resolved_at": None,
            })
            return _id

    def get_open_tickets(self) -> List[dict]:
        return self._wrap_many(
            self.db.tickets.find({"status": "OPEN"}).sort("created_at", ASCENDING)
        )

    def reply_ticket(self, ticket_id: int, reply: str) -> int:
        with self.lock:
            ticket = self.db.tickets.find_one({"_id": int(ticket_id)})
            if not ticket:
                return 0
            self.db.tickets.update_one(
                {"_id": int(ticket_id)},
                {"$set": {
                    "reply": reply,
                    "status": "CLOSED",
                    "resolved_at": datetime.now().isoformat(),
                }},
            )
            return ticket["user_id"]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def get_global_stats(self) -> Tuple[int, int, int, int]:
        users = self.db.users.count_documents({"verified": 1})
        agg = list(self.db.purchases.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]))
        revenue = int(agg[0]["total"]) if agg else 0
        sold_keys = self.db.keys.count_documents({"is_sold": 1})
        avail_keys = self.db.keys.count_documents({"is_sold": 0})
        return users, revenue, sold_keys, avail_keys

    # ------------------------------------------------------------------
    # Backup / Export
    # ------------------------------------------------------------------
    def export_database(self) -> bytes:
        """Return a JSON dump of all collections (BSON-safe)."""
        snapshot = {}
        collections = [
            "users", "products", "plans", "keys", "purchases",
            "fund_requests", "tickets", "admin_logs", "settings",
            "promo_codes", "redeemed_promos", "counters",
        ]
        for col in collections:
            snapshot[col] = list(self.db[col].find({}))
        return bson_dumps(snapshot, indent=2).encode("utf-8")
